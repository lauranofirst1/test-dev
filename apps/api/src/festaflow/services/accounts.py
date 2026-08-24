"""기관 계정 — 회원가입 · 로그인 · 비밀번호.

**비밀번호 정책은 길이로 갑니다.** 대문자·숫자·기호를 강제하면 사람들은
`Password1!` 을 만들고, 그건 길고 무작위한 비밀번호보다 훨씬 약합니다.
그래서 최소 10자만 요구하고, 대신 **뻔한 것들을 거절**합니다 — 유출 목록 상위
비밀번호와 이메일·기관명에서 그대로 따온 것.

**이메일 열거를 막습니다.** 로그인 실패는 이메일이 없는 것과 비밀번호가 틀린
것을 구분하지 않고, 없는 이메일에도 해시 한 번 값의 시간을 씁니다. 응답 시간만
재도 계정 존재가 드러나면 유출 목록으로 훑는 공격의 첫 단계가 공짜가 됩니다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.errors import ApiError, validation_failed
from festaflow.models import Organization, OrganizationAccount, PasswordResetToken

#: 유출 목록에서 늘 위에 있는 것들. 전체 목록을 들일 필요는 없다 —
#: 이 정도만 막아도 "가장 게으른 선택"은 사라진다.
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwertyuiop",
        "qwerty123",
        "iloveyou",
        "admin1234",
        "administrator",
        "letmein123",
        "welcome123",
        "abcd1234",
        "asdf1234",
        "1q2w3e4r",
        "1q2w3e4r5t",
        "festaflow",
        "festaflow1",
    }
)


def normalize_email(raw: str) -> str:
    """소문자·공백 제거. 대소문자가 다른 두 계정이 생기면 어느 쪽인지 알 수 없다."""
    return raw.strip().lower()


def check_password(password: str, *, email: str, organization_name: str) -> None:
    """약한 비밀번호를 저장 전에 거절한다.

    저장한 뒤에 알려주면 이미 늦습니다 — 그 비밀번호로 로그인이 되고 있으니까요.
    """
    if len(password) < 10:
        raise validation_failed("비밀번호는 10자 이상이어야 합니다.", "password")

    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        raise validation_failed(
            "너무 흔한 비밀번호입니다. 유출 목록에 있는 값이라 바로 뚫립니다.", "password"
        )

    # 이메일 아이디나 기관명을 그대로 쓴 것. 공격자가 가장 먼저 넣어보는 값이다.
    local = normalize_email(email).split("@")[0]
    for seed in (local, organization_name.lower().replace(" ", "")):
        if seed and len(seed) >= 4 and seed in lowered:
            raise validation_failed(
                "이메일이나 기관 이름이 그대로 들어 있습니다. 짐작하기 쉬운 값입니다.",
                "password",
            )

    if len(set(password)) < 5:
        raise validation_failed(
            "같은 글자가 반복됩니다. 서로 다른 글자를 5종류 이상 써 주세요.", "password"
        )


def sign_up(
    db: Session, *, organization_name: str, display_name: str, email: str, password: str
) -> OrganizationAccount:
    """기관과 첫 계정을 한 트랜잭션으로 만든다."""
    normalized = normalize_email(email)
    check_password(password, email=normalized, organization_name=organization_name)

    org = Organization(name=organization_name.strip())
    db.add(org)
    db.flush()

    account = OrganizationAccount(
        organization_id=org.id,
        email=normalized,
        password_hash=security.hash_password(password),
        display_name=display_name.strip(),
    )
    try:
        with db.begin_nested():
            db.add(account)
            db.flush()
    except IntegrityError:
        if account in db:
            db.expunge(account)
        # 가입에서만 계정 존재를 알려 준다. 감추면 "왜 가입이 안 되는지" 를
        # 알 수 없어 지원 요청이 되고, 그 답이 결국 같은 사실을 알려준다.
        raise ApiError(
            409,
            "EMAIL_TAKEN",
            "이미 가입된 이메일입니다. 로그인하거나 다른 이메일을 쓰세요.",
            {"field": "email"},
        ) from None

    return account


def _invalid_login() -> ApiError:
    """이메일이 없는 것과 비밀번호가 틀린 것을 구분하지 않는다."""
    return ApiError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 맞지 않습니다.")


def log_in(db: Session, *, email: str, password: str) -> OrganizationAccount:
    now = datetime.now(UTC)
    account = db.execute(
        select(OrganizationAccount).where(
            OrganizationAccount.email == normalize_email(email)
        )
    ).scalar_one_or_none()

    if account is None:
        # 없는 이메일이 눈에 띄게 빨리 실패하면 응답 시간만으로 가입 여부가 드러난다.
        security.waste_password_time()
        raise _invalid_login()

    # 잠금은 비밀번호 검증보다 먼저 본다 — 잠긴 동안은 맞는 비밀번호도 받지 않는다.
    if account.locked_until is not None:
        if account.locked_until > now:
            retry_after = int((account.locked_until - now).total_seconds())
            raise ApiError(
                429,
                "ACCOUNT_LOCKED",
                f"여러 번 틀려 잠겼습니다. {retry_after // 60 + 1}분 뒤 다시 시도하세요.",
                {"retry_after_seconds": retry_after},
            )
        account.locked_until = None
        account.failed_attempts = 0

    if not account.is_active or not security.verify_password(password, account.password_hash):
        account.failed_attempts += 1
        if account.failed_attempts >= settings.login_max_attempts:
            account.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        db.commit()
        raise _invalid_login()

    account.failed_attempts = 0
    account.locked_until = None
    account.last_login_at = now
    db.commit()
    db.refresh(account)
    return account


def change_password(
    db: Session, account: OrganizationAccount, *, current: str, new: str
) -> None:
    """비밀번호를 바꾼다. **기존 세션이 전부 끊긴다.**

    바꾸는 이유가 유출이면, 옛 세션이 살아 있는 한 바꾼 의미가 없습니다.
    `password_changed_at` 이 그 시점을 남기고, 그보다 먼저 발급된 토큰은
    `deps.get_optional_account` 가 거절합니다.
    """
    if not security.verify_password(current, account.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "현재 비밀번호가 맞지 않습니다.")

    org = db.get(Organization, account.organization_id)
    check_password(new, email=account.email, organization_name=org.name if org else "")

    account.password_hash = security.hash_password(new)
    # 초 단위 경계에서 방금 발급한 세션까지 끊기지 않게 1초 뒤로 둔다.
    account.password_changed_at = datetime.now(UTC)
    db.commit()


# ── 비밀번호 재설정 ─────────────────────────────────────────────────────────
#
# **요청은 언제나 같은 응답을 냅니다.** 가입된 이메일이면 링크를 보내고, 아니면
# 아무것도 하지 않은 채 같은 문장을 돌려줍니다. 응답이 갈리면 이 화면이 곧
# "이 이메일이 가입돼 있나" 를 확인해 주는 도구가 됩니다.
#
# 링크를 화면으로 돌려주지 않는 이유도 같습니다 — 남의 이메일을 넣은 사람에게
# 링크가 나가면 계정 탈취가 요청 한 번으로 끝납니다.

#: 재설정 링크 유효 시간. 길면 메일함에 오래 남은 링크가 열쇠가 되고,
#: 짧으면 메일을 늦게 확인한 사람이 다시 요청해야 한다.
#:
#: 설정에서 읽는 이유는 **메일 본문이 이 값을 그대로 알리기** 때문이다. 여기와
#: 메일 문구에 숫자가 따로 있으면 반드시 어긋나고, 사용자는 만료된 링크를
#: 계속 누른다.
RESET_TTL_MINUTES = settings.reset_ttl_minutes


def _hash_token(token: str) -> str:
    """서버가 만든 32바이트 난수라 sha256 으로 충분하다 — 전수 대입이 불가능하다.
    느린 해시는 저엔트로피 값(6자리 코드·비밀번호)에만 필요하다."""
    return hashlib.sha256(token.encode()).hexdigest()


def request_password_reset(db: Session, *, email: str) -> tuple[str, str] | None:
    """재설정 표를 발급한다. 가입되지 않은 이메일이면 None.

    호출자는 **None 이든 아니든 같은 응답을 내야 합니다.**
    """
    account = db.execute(
        select(OrganizationAccount).where(
            OrganizationAccount.email == normalize_email(email)
        )
    ).scalar_one_or_none()
    if account is None or not account.is_active:
        return None

    # 새로 요청하면 아직 살아 있는 옛 표를 죽인다. 여러 링크가 동시에 유효하면
    # 그중 하나만 유출돼도 계정이 열리고, 사용자는 어느 것이 살아 있는지 모른다.
    now = datetime.now(UTC)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.account_id == account.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            account_id=account.id,
            token_hash=_hash_token(token),
            expires_at=now + timedelta(minutes=RESET_TTL_MINUTES),
        )
    )
    db.commit()
    return token, account.email


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    """표를 쓰고 비밀번호를 바꾼다. **표는 한 번 쓰면 죽습니다.**

    링크는 메일함에 남고 메일함은 종종 남에게 열려 있습니다. 쓰고 나서도
    유효하면 그 링크가 영구 열쇠가 됩니다.
    """
    now = datetime.now(UTC)
    row = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _hash_token(token)
        )
    ).scalar_one_or_none()

    # 없는 표·쓴 표·만료된 표를 구분하지 않는다. 구분하면 표를 훑어
    # "유효한 것이 있는가" 를 물어볼 수 있다.
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise ApiError(
            400,
            "RESET_TOKEN_INVALID",
            "링크가 만료되었거나 이미 사용되었습니다. 재설정을 다시 요청해 주세요.",
        )

    account = db.get(OrganizationAccount, row.account_id)
    if account is None or not account.is_active:
        raise ApiError(400, "RESET_TOKEN_INVALID", "이 링크는 더 이상 쓸 수 없습니다.")

    org = db.get(Organization, account.organization_id)
    check_password(new_password, email=account.email, organization_name=org.name if org else "")

    account.password_hash = security.hash_password(new_password)
    # 재설정도 비밀번호 변경이다 — 기존 세션이 전부 끊긴다. 재설정하는 이유가
    # 탈취면, 공격자의 세션이 살아 있는 한 바꾼 의미가 없다.
    account.password_changed_at = now
    account.failed_attempts = 0
    account.locked_until = None
    row.used_at = now
    db.commit()
