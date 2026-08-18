"""접근 코드 해시와 세션 토큰.

접근 코드는 32자 알파벳에서 뽑은 6자리 — 조합이 약 10억뿐입니다. 해시가 유출되면
평범한 장비로 전수 대입이 됩니다. 그래서 sha256 이 아니라 **bcrypt** 로 늦춥니다.
온라인 대입은 로그인 잠금(5회 연속 실패 → 10분)이 막습니다.

passlib 은 쓰지 않습니다 — 1.7.4 의 bcrypt 백엔드가 bcrypt 5.x 와 맞지 않아
내부 호환성 probe 가 `ValueError: password cannot be longer than 72 bytes` 로
죽습니다. `bcrypt` 를 직접 부릅니다.
"""

from __future__ import annotations

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
