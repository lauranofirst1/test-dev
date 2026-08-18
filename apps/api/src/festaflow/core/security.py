"""접근 코드 해시와 세션 토큰.

접근 코드는 32자 알파벳에서 뽑은 6자리 — 조합이 약 10억뿐입니다. 해시가 유출되면
평범한 장비로 전수 대입이 됩니다. 그래서 sha256 이 아니라 **bcrypt** 로 늦춥니다.
온라인 대입은 로그인 잠금(5회 연속 실패 → 10분)이 막습니다.

passlib 은 쓰지 않습니다 — 1.7.4 의 bcrypt 백엔드가 bcrypt 5.x 와 맞지 않아
내부 호환성 probe 가 `ValueError: password cannot be longer than 72 bytes` 로
죽습니다. `bcrypt` 를 직접 부릅니다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from festaflow.core.config import settings
from festaflow.core.errors import ApiError

ALGORITHM = "HS256"

#: 배포에서 이 값이 그대로면 토큰을 누구나 위조할 수 있다.
INSECURE_SECRETS = frozenset({"dev-only-change-me", "dev-only-change-me-0123456789abcdef"})

#: 스태프가 없을 때도 해시 검증에 준하는 시간을 쓰기 위한 더미.
#: 없는 staff_id 는 즉시 실패하고 있는 staff_id 는 늦게 실패하면,
#: 응답 시간만 재도 계정 존재 여부가 드러난다.
_DUMMY_HASH = "$2b$12$eImiTXuWVxfM37uY4JANjQ.C4TT2Bp2gPHmFTIYQTBGvwUb0zSyXO"


def hash_access_code(code: str) -> str:
    """접근 코드를 bcrypt 로 해시한다. 평문은 어디에도 저장하지 않는다."""
    return bcrypt.hashpw(
        code.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode()


def verify_access_code(code: str, hashed: str) -> bool:
    """틀린 코드든 못 읽는 해시든 똑같이 False. 예외를 밖으로 흘리지 않는다."""
    try:
        return bcrypt.checkpw(code.encode(), hashed.encode())
    except (ValueError, TypeError):
        # bcrypt 형식이 아닌 해시(구 sha256 등)는 검증 불가 → 실패로 본다.
        return False


def waste_verify_time() -> None:
    """스태프를 못 찾았을 때도 해시 한 번 값의 시간을 쓴다."""
    verify_access_code("timing", _DUMMY_HASH)


@dataclass(frozen=True)
class StaffClaims:
    """세션 토큰이 실어 나르는 것 — docs/03-api-contract.md §1."""

    staff_id: int
    festival_id: int
    role: str
    booth_id: int | None


def issue_staff_token(
    *, staff_id: int, festival_id: int, role: str, booth_id: int | None
) -> tuple[str, int]:
    """세션 토큰과 만료까지 남은 초를 돌려준다."""
    ttl = timedelta(hours=settings.jwt_ttl_hours)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(staff_id),
        "staff_id": staff_id,
        "festival_id": festival_id,
        "role": role,
        "booth_id": booth_id,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), int(
        ttl.total_seconds()
    )


def decode_staff_token(token: str) -> StaffClaims:
    """서명·만료를 검증하고 클레임을 꺼낸다. 실패는 전부 401 로 합친다."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ApiError(
            401, "INVALID_TOKEN", "세션이 만료되었거나 올바르지 않습니다. 다시 로그인하세요."
        ) from exc

    try:
        return StaffClaims(
            staff_id=int(payload["staff_id"]),
            festival_id=int(payload["festival_id"]),
            role=str(payload["role"]),
            booth_id=(None if payload.get("booth_id") is None else int(payload["booth_id"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            401, "INVALID_TOKEN", "세션이 만료되었거나 올바르지 않습니다. 다시 로그인하세요."
        ) from exc


def assert_secret_is_safe() -> None:
    """개발용 기본 시크릿으로 로컬 밖에서 뜨는 것을 막는다.

    이걸 막지 않으면 시크릿이 저장소에 공개된 상태로 배포되고,
    토큰을 누구나 위조할 수 있다. 부팅을 실패시키는 게 낫다.
    """
    if settings.app_env == "local":
        return
    if settings.jwt_secret in INSECURE_SECRETS or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            f"APP_ENV={settings.app_env} 에서 JWT_SECRET 이 개발 기본값이거나 너무 짧습니다. "
            "openssl rand -hex 32 으로 새로 만들어 넣으세요."
        )


# ── 참여자 ──────────────────────────────────────────────────────────────────

#: 사람이 부스에서 소리내어 읽고 손으로 옮겨 적는 코드다.
#: 0/O, 1/I 처럼 헷갈리는 글자를 빼야 현장에서 오타 문의가 줄어든다.
PARTICIPANT_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_participant_code() -> str:
    """`FF-XXXXXXXX`. participants.code 의 CHECK 제약과 같은 모양이어야 한다."""
    body = "".join(secrets.choice(PARTICIPANT_ALPHABET) for _ in range(8))
    return f"FF-{body}"


def generate_participant_secret() -> str:
    """조회 인증용 비밀. 코드는 부스에서 노출되므로 반드시 분리한다."""
    return f"s_{secrets.token_urlsafe(24)}"


def hash_participant_secret(secret: str) -> str:
    """참여자 비밀은 sha256 으로 해시한다 — 접근 코드와 달리 bcrypt 가 아니다.

    6자리 접근 코드는 사람이 외우는 저엔트로피 값이라 느린 해시가 필요하지만,
    이 비밀은 서버가 만든 24바이트 난수라 전수 대입이 애초에 불가능하다.
    관객 화면은 보드를 자주 폴링하므로, 요청마다 180ms 를 쓰는 쪽이 오히려 위험하다.
    """
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_participant_secret(secret: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_participant_secret(secret), hashed)


# ── 부스 회전 QR ────────────────────────────────────────────────────────────


def current_window(now: datetime | None = None) -> int:
    """`floor(unix_seconds / window)` — docs/02-data-model.md §7."""
    ts = (now or datetime.now(UTC)).timestamp()
    return int(ts // settings.scan_token_window_seconds)


def booth_scan_token(qr_secret: bytes, booth_id: int, window_index: int) -> str:
    """부스 QR 토큰. 별도 테이블 없이 HMAC 으로 만든다.

    `base64url(HMAC_SHA256(qr_secret, booth_id || window_index))[0:12]`
    """
    msg = f"{booth_id}|{window_index}".encode()
    digest = hmac.new(qr_secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:12]


def match_scan_window(
    qr_secret: bytes, booth_id: int, token: str, now: datetime | None = None
) -> int | None:
    """토큰이 맞는 window 를 돌려준다. 현재와 **직전** 둘 다 인정한다.

    갱신 직전에 스캔한 참여자를 실패시키지 않기 위한 것이고, 기기 시계 오차도 함께
    흡수한다. 실질 유효기간이 30~60초라 QR 사진이 돌아도 현장 밖에서는 못 쓴다.
    """
    now_window = current_window(now)
    for candidate in (now_window, now_window - 1):
        if hmac.compare_digest(booth_scan_token(qr_secret, booth_id, candidate), token):
            return candidate
    return None


def window_expires_at(window_index: int) -> datetime:
    """이 window 가 끝나는 시각. 부스 화면이 QR 갱신 시점을 잡는 데 쓴다."""
    return datetime.fromtimestamp(
        (window_index + 1) * settings.scan_token_window_seconds, tz=UTC
    )
