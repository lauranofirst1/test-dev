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
from urllib.parse import urlsplit

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from festaflow.core.config import settings
from festaflow.core.errors import ApiError

ALGORITHM = "HS256"

#: 배포에서 이 값이 그대로면 토큰을 누구나 위조할 수 있다.
INSECURE_SECRETS = frozenset({"dev-only-change-me", "dev-only-change-me-0123456789abcdef"})

#: 스태프가 없을 때도 해시 검증에 준하는 시간을 쓰기 위한 더미.
#: 없는 staff_id 는 즉시 실패하고 있는 staff_id 는 늦게 실패하면,
#: 응답 시간만 재도 계정 존재 여부가 드러난다.
_DUMMY_HASH = "$2b$12$eImiTXuWVxfM37uY4JANjQ.C4TT2Bp2gPHmFTIYQTBGvwUb0zSyXO"


#: 접근 코드 알파벳. 참여 코드와 같은 이유로 0·O·1·I 를 뺀다 — 사람이 종이에서
#: 읽어 폰에 옮겨 적고, 헷갈리는 글자는 그대로 "안 되는데요" 문의가 된다.
ACCESS_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ACCESS_CODE_LENGTH = 6


def generate_access_code() -> str:
    """스태프 접근 코드. `secrets` 로 뽑는다 — 예측 가능하면 초대 URL 만으로 들어온다."""
    return "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_LENGTH))


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


# ── 비밀번호 ────────────────────────────────────────────────────────────────
#
# 접근 코드와 달리 비밀번호는 길이 제한이 없습니다. 그런데 **bcrypt 는 72바이트를
# 넘는 입력을 조용히 잘라 버립니다.** UTF-8 한글은 글자당 3바이트라 24자면 한계에
# 닿습니다. 자르면 긴 비밀번호가 짧은 것과 같은 해시를 갖게 되고, 사용자는 자기
# 비밀번호가 뒤쪽부터 무시되고 있다는 사실을 영원히 모릅니다.
#
# 그래서 bcrypt 에 넣기 전에 sha256 으로 한 번 줄입니다(bcrypt-sha256). 길이가
# 어떻든 항상 44바이트가 되어 잘릴 일이 없고, bcrypt 의 느린 성질은 그대로입니다.
#
# base64 로 감싸는 이유는 sha256 원시 바이트에 NUL 이 들어갈 수 있기 때문입니다 —
# bcrypt 는 NUL 에서 문자열을 끊습니다.


def _prehash(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _prehash(password), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode()


def verify_password(password: str, hashed: str) -> bool:
    """틀린 비밀번호든 못 읽는 해시든 똑같이 False."""
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode())
    except (ValueError, TypeError):
        return False


def waste_password_time() -> None:
    """없는 이메일도 해시 한 번 값의 시간을 쓴다 — 응답 시간으로 계정 존재가
    드러나면 이메일 열거가 그대로 가능해진다."""
    verify_password("timing", _DUMMY_HASH)


@dataclass(frozen=True)
class OrgClaims:
    """기관 계정 세션이 실어 나르는 것.

    **축제가 아니라 기관에 묶입니다.** 계약(§1)의 스태프 로그인은 축제별이라
    `festival_id` 가 필요한데, 축제 목록·생성은 축제가 생기기 전에 호출됩니다.
    그래서 그 경로들이 지금까지 `X-Organization-Id` 헤더 폴백에 기대고 있었고,
    그 폴백은 헤더만 바꾸면 남의 기관이 열리는 구멍입니다.
    """

    account_id: int
    organization_id: int
    #: 발급 시각. 비밀번호를 바꾼 뒤에 발급된 세션인지 가린다.
    issued_at: datetime


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
        # 기관 토큰과 같은 키로 서명되므로 종류를 박아 서로를 대신하지 못하게 한다.
        "typ": "staff",
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
    """서명·만료를 검증하고 클레임을 꺼낸다. 실패는 전부 401 로 합친다.

    `typ` 이 `staff` 가 아니면 거절한다 — 기관 토큰은 축제 범위를 담지 않으므로
    스태프 자리에 들어오면 `festival_id` 검사가 통째로 무너진다.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise ApiError(
            401, "INVALID_TOKEN", "세션이 만료되었거나 올바르지 않습니다. 다시 로그인하세요."
        ) from exc

    # 예전에 발급된 토큰에는 typ 이 없다. 없으면 스태프로 본다 — 기관 토큰은
    # 이번에 생겼으므로 typ 이 반드시 있다.
    if payload.get("typ", "staff") != "staff":
        raise ApiError(401, "INVALID_TOKEN", "이 세션으로는 접근할 수 없습니다.")

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


def _is_https_origin(value: str | None) -> bool:
    """경로·쿼리·자격증명이 없는 HTTPS origin인지 확인한다."""
    if not value:
        return False
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def assert_deployment_is_safe() -> None:
    """운영 배포가 보안 필수값 없이 시작되는 것을 막는다.

    로컬은 휴대폰 LAN 테스트 때문에 HTTP와 비-Secure 쿠키를 허용한다. 그 예외가
    운영까지 번지면 세션 탈취와 Host 헤더 기반 재설정 링크 변조로 이어지므로,
    로컬이 아닌 환경은 실패-폐쇄(fail closed)한다.
    """
    assert_secret_is_safe()
    if settings.app_env == "local":
        return

    if settings.demo_mode:
        raise RuntimeError(
            "DEMO_MODE=true 는 로컬 전용입니다. 배포에서는 헤더 기반 기관 폴백을 "
            "다시 열 수 있으므로 DEMO_MODE=false 로 두세요."
        )
    if not settings.session_cookie_secure:
        raise RuntimeError(
            f"APP_ENV={settings.app_env} 에서는 SESSION_COOKIE_SECURE=true 가 필요합니다."
        )
    if not _is_https_origin(settings.public_web_origin):
        raise RuntimeError(
            f"APP_ENV={settings.app_env} 에서는 PUBLIC_WEB_ORIGIN을 경로 없는 HTTPS "
            "주소(예: https://festaflow.example.com)로 설정해야 합니다."
        )

    if not settings.trusted_host_list or "*" in settings.trusted_host_list:
        raise RuntimeError(
            f"APP_ENV={settings.app_env} 에서는 TRUSTED_HOSTS에 API가 실제로 받는 "
            "호스트만 적어야 하며 *는 허용되지 않습니다."
        )

    invalid_cors = [
        origin for origin in settings.cors_origin_list if not _is_https_origin(origin)
    ]
    if not settings.cors_origin_list or invalid_cors:
        raise RuntimeError(
            f"APP_ENV={settings.app_env} 에서는 CORS_ORIGINS를 HTTPS origin만으로 "
            "설정해야 합니다."
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


def booth_print_signature(qr_secret: bytes, booth_id: int) -> str:
    """인쇄 QR 의 **고정 서명** — 계약 §14.4, 기획서 E4.

    지역 축제 천막 부스에는 태블릿도 상시 전원도 없는 경우가 대부분입니다.
    보안을 이유로 장비를 강요하면 그 기능은 안 쓰이고, **안 쓰이는 보안은
    보안이 아닙니다.** 그래서 인쇄가 기본이고 회전 QR 이 상위 옵션입니다.

    회전 토큰과 **메시지 접두어가 다릅니다.** 같은 키로 만들더라도 서로를
    대신 쓸 수 없어야 합니다 — 회전 부스의 지나간 토큰이 인쇄 서명으로
    통과하거나 그 반대가 되면, 모드를 나눈 의미가 사라집니다.

    서명은 `qr_secret` 이 바뀔 때까지 유효합니다. 재발행하면 이미 붙여 둔
    인쇄물이 그 순간 무효가 됩니다.
    """
    msg = f"print|{booth_id}".encode()
    digest = hmac.new(qr_secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:16]


def match_print_signature(qr_secret: bytes, booth_id: int, signature: str) -> bool:
    return hmac.compare_digest(booth_print_signature(qr_secret, booth_id), signature)


def attendance_certificate_code(qr_secret: bytes, session_id: int, participant_id: int) -> str:
    """공결 확인서 코드 — 학생이 교수에게 보여주는 값.

    **테이블을 쓰지 않고 HMAC 으로 파생합니다.** 확인서를 스냅샷으로 저장하면
    나중에 출결이 정정됐을 때 종이만 옛 사실을 말합니다. 이 코드는 기록이 아니라
    **가리키는 손가락**이라, 확인 페이지가 언제나 지금의 출결을 읽습니다.
    정정되면 확인 결과도 함께 바뀌고, 폐기 절차가 필요 없습니다.

    부스 토큰·체크인 토큰과 **메시지 접두어가 다릅니다.** 같은 키로 만들더라도
    서로를 대신 쓸 수 없어야 합니다.

    16자를 쓰는 이유는 이 값이 사실상 **비밀번호**이기 때문입니다. 코드를 아는
    사람은 누구나 그 학생의 출결을 봅니다 — 12자(72비트)로도 충분하지만, 학번을
    다루는 값이라 여유를 둡니다. 학번이나 이름에서 유도되지 않으므로 남의 것을
    추측할 수 없습니다.
    """
    msg = f"cert|{session_id}|{participant_id}".encode()
    digest = hmac.new(qr_secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:16]


def match_certificate_code(
    qr_secret: bytes, session_id: int, participant_id: int, code: str
) -> bool:
    return hmac.compare_digest(
        attendance_certificate_code(qr_secret, session_id, participant_id), code
    )


#: 기본 인정 window 수 — 현재와 직전. 도착 확인처럼 즉시 끝나는 지급용이다.
DEFAULT_ACCEPTED_WINDOWS = 2


def match_scan_window(
    qr_secret: bytes,
    booth_id: int,
    token: str,
    now: datetime | None = None,
    *,
    windows: int = DEFAULT_ACCEPTED_WINDOWS,
) -> int | None:
    """토큰이 맞는 window 를 돌려준다. 현재부터 `windows` 개 전까지 인정한다.

    기본값 2(현재와 직전)는 갱신 직전에 스캔한 참여자를 실패시키지 않기 위한 것이고,
    기기 시계 오차도 함께 흡수한다. 실질 유효기간이 30~60초라 QR 사진이 돌아도
    현장 밖에서는 못 쓴다.

    **퀴즈처럼 시간이 걸리는 체험은 이 예산으로 끝낼 수 없다.** 문제를 읽고 보기를
    고르고, 틀리면 힌트를 보고 다시 푼다. 그래서 체험이 붙은 부스는 호출자가 더 넉넉한
    값을 넘긴다(services/experience.py). 늘어난 뒤에도 몇 분 단위라 현장 밖 재사용을
    막는다는 성질은 그대로다.
    """
    now_window = current_window(now)
    for back in range(windows):
        candidate = now_window - back
        if hmac.compare_digest(booth_scan_token(qr_secret, booth_id, candidate), token):
            return candidate
    return None


def window_expires_at(window_index: int) -> datetime:
    """이 window 가 끝나는 시각. 부스 화면이 QR 갱신 시점을 잡는 데 쓴다."""
    return datetime.fromtimestamp(
        (window_index + 1) * settings.scan_token_window_seconds, tz=UTC
    )


# ── 기관 계정 세션 ──────────────────────────────────────────────────────────


def issue_org_token(*, account_id: int, organization_id: int) -> tuple[str, int]:
    """기관 계정 세션 토큰과 만료까지 남은 초.

    `typ` 을 넣어 **스태프 토큰과 섞이지 않게** 합니다. 두 토큰은 같은 키로
    서명되므로, 종류를 구분하지 않으면 기관 토큰을 스태프 자리에 넣거나 그
    반대가 통합니다.
    """
    ttl = timedelta(hours=settings.jwt_ttl_hours)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "typ": "org",
        "sub": str(account_id),
        "account_id": account_id,
        "organization_id": organization_id,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), int(
        ttl.total_seconds()
    )


def decode_org_token(token: str) -> OrgClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise ApiError(401, "INVALID_TOKEN", "세션이 만료됐습니다. 다시 로그인하세요.") from exc

    if payload.get("typ") != "org":
        # 스태프 토큰을 기관 자리에 넣은 경우. 서명은 맞지만 쓸 수 없다.
        raise ApiError(401, "INVALID_TOKEN", "이 세션으로는 접근할 수 없습니다.")

    try:
        return OrgClaims(
            account_id=int(payload["account_id"]),
            organization_id=int(payload["organization_id"]),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(401, "INVALID_TOKEN", "세션 정보를 읽을 수 없습니다.") from exc
