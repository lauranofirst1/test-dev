"""스태프 인증 — docs/03-api-contract.md §1.

**2단계 로그인.** 초대 QR 은 `/staff/login?f={festival_id}&s={staff_id}` 를 담고
거기엔 비밀이 없습니다. 세션은 6자리 접근 코드를 맞혀야 발급됩니다.
QR 사진이 유출돼도 코드 없이는 들어올 수 없습니다.

실패 응답은 무엇이 틀렸는지 알려주지 않습니다 — 축제가 없는 것과 스태프가 없는 것과
코드가 틀린 것을 구분해주면, 응답만 보고 유효한 staff_id 를 찾아낼 수 있습니다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.deps import CurrentAccount, CurrentStaff, DbSession
from festaflow.core.errors import ApiError
from festaflow.models import Festival, FestivalStaff, Organization
from festaflow.schemas.auth import (
    AccountInfo,
    AccountSession,
    LogIn,
    PasswordChange,
    PasswordResetAccepted,
    PasswordResetConfirm,
    PasswordResetRequest,
    SignUp,
    StaffInfo,
    StaffLogin,
    StaffSession,
)
from festaflow.services import accounts as svc
from festaflow.services import mailer

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _invalid() -> ApiError:
    """축제·스태프·코드 중 무엇이 틀렸는지 밝히지 않는 하나의 실패."""
    return ApiError(
        401,
        "INVALID_CREDENTIALS",
        "축제·스태프·접근 코드가 맞지 않습니다. 초대 QR 을 다시 확인하세요.",
    )


@router.get("/staff/me", response_model=StaffInfo)
def staff_me(staff: CurrentStaff) -> StaffInfo:
    """지금 로그인한 스태프가 누구인가.

    세션은 httpOnly 쿠키라 화면이 토큰 내용을 읽을 수 없습니다. 새로고침하면
    "나는 누구이고 어느 부스를 맡았는가" 를 잃어버리는데, 부스 지급 화면은
    그걸 모르면 배정되지 않은 부스를 고를 수 있게 열어 줍니다.

    **토큰을 다시 내려주지 않습니다.** 조회에 토큰이 실려 나가면 XSS 한 번에
    세션이 통째로 새고, httpOnly 로 둔 이유가 사라집니다.
    """
    return StaffInfo.model_validate(staff)


@router.post("/staff/login", response_model=StaffSession)
def staff_login(payload: StaffLogin, response: Response, db: DbSession) -> StaffSession:
    """접근 코드를 검증하고 세션 토큰을 발급한다.

    연속 실패가 `login_max_attempts` 회에 닿으면 `login_lock_minutes` 분 잠근다.
    6자리 코드는 조합이 약 10억뿐이라 잠금이 없으면 온라인 대입이 실제로 통한다.
    """
    now = datetime.now(UTC)

    staff = db.execute(
        select(FestivalStaff).where(FestivalStaff.id == payload.staff_id)
    ).scalar_one_or_none()

    # 잠금은 코드 검증보다 먼저 본다 — 잠긴 동안은 맞는 코드도 받지 않는다.
    if staff is not None and staff.locked_until is not None:
        if staff.locked_until > now:
            retry_after = int((staff.locked_until - now).total_seconds())
            minutes = retry_after // 60 + 1
            raise ApiError(
                429,
                "ACCOUNT_LOCKED",
                f"접근 코드를 여러 번 틀려 잠겼습니다. {minutes}분 뒤 다시 시도하세요.",
                {"retry_after_seconds": retry_after},
            )
        # 잠금이 풀렸다 — 카운터를 비우고 새로 센다.
        staff.locked_until = None
        staff.failed_attempts = 0

    festival_ok = False
    if staff is not None and staff.festival_id == payload.festival_id:
        festival_ok = (
            db.execute(
                select(Festival.id).where(
                    Festival.id == payload.festival_id, Festival.archived_at.is_(None)
                )
            ).scalar_one_or_none()
            is not None
        )

    ok = (
        staff is not None
        and staff.is_active
        and festival_ok
        and security.verify_access_code(payload.access_code, staff.access_code_hash)
    )

    if not ok:
        if staff is None:
            # 존재하지 않는 staff_id 가 눈에 띄게 빨리 실패하면 응답 시간만으로
            # 유효한 ID 를 훑을 수 있다. 해시 한 번 값의 시간을 쓴다.
            security.waste_verify_time()
        else:
            staff.failed_attempts += 1
            if staff.failed_attempts >= settings.login_max_attempts:
                staff.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            db.commit()
        raise _invalid()

    if staff is None:  # 방어적 실패: 최적화(-O)에서도 assert처럼 사라지지 않는다.
        raise _invalid()
    staff.failed_attempts = 0
    staff.locked_until = None
    staff.last_login_at = now
    db.commit()
    db.refresh(staff)

    token, expires_in = security.issue_staff_token(
        staff_id=staff.id,
        festival_id=staff.festival_id,
        role=staff.role.value,
        booth_id=staff.booth_id,
    )
    # 브라우저용으로 httpOnly 쿠키에도 싣는다. 화면이 토큰을 손에 쥐지 않아야
    # XSS 로도 새지 않는다. 본문의 `access_token` 은 브라우저가 아닌
    # 클라이언트(부스 태블릿 앱·스크립트·테스트)를 위해 남긴다.
    _set_session(response, token, expires_in, name=settings.staff_cookie_name)
    return StaffSession(
        access_token=token,
        expires_in=expires_in,
        staff=StaffInfo.model_validate(staff),
    )


# ── 세션 쿠키 ───────────────────────────────────────────────────────────────


def _set_session(response: Response, token: str, max_age: int, *, name: str) -> None:
    """세션을 **httpOnly 쿠키로** 내보낸다.

    `name` 으로 기관 계정 세션과 스태프 세션을 가른다. 한 이름을 같이 쓰면
    나중에 로그인한 쪽이 앞의 세션을 덮어쓴다.

    - `httponly` — 스크립트가 읽을 수 없다. XSS 가 나도 토큰이 새지 않는다.
      localStorage 에 두면 XSS 한 번에 전부 털린다.
    - `samesite=strict` — 외부 사이트에서 온 요청에는 쿠키가 실리지 않는다.
      우리 요청은 전부 같은 사이트라 CSRF 가 구조적으로 막힌다. 별도 CSRF
      토큰을 두지 않는 근거가 이것이다.
    - `secure` — 배포에서 반드시 켠다. 로컬은 http 라 켜면 브라우저가 저장조차
      하지 않으므로 설정으로 뺐다.
    - `path="/"` — API 와 화면이 같은 오리진이므로 전체에 실린다.
    """
    response.set_cookie(
        name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _clear_session(response: Response) -> None:
    """이 브라우저의 세션을 **둘 다** 지운다.

    로그아웃 버튼은 콘솔에도 심사표에도 같은 것 하나뿐이다. 한쪽만 지우면
    공용 태블릿에서 "로그아웃했는데 아직 들어가진다" 가 된다 — 로그아웃이
    보장해야 하는 단 하나가 그것이다.
    """
    for name in (settings.session_cookie_name, settings.staff_cookie_name):
        response.delete_cookie(
            name,
            path="/",
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
        )


# ── 기관 계정 ───────────────────────────────────────────────────────────────


def _session_body(db, account) -> AccountSession:
    org = db.get(Organization, account.organization_id)
    return AccountSession(
        account=AccountInfo.model_validate(account),
        organization_name=org.name if org else "",
        expires_in=settings.jwt_ttl_hours * 3600,
    )


@router.post("/signup", response_model=AccountSession, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUp, response: Response, db: DbSession) -> AccountSession:
    """기관과 첫 계정을 만들고 바로 로그인시킨다."""
    account = svc.sign_up(
        db,
        organization_name=payload.organization_name,
        display_name=payload.display_name,
        email=payload.email,
        password=payload.password,
    )
    db.commit()
    db.refresh(account)

    token, ttl = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )
    _set_session(response, token, ttl, name=settings.session_cookie_name)
    return _session_body(db, account)


@router.post("/login", response_model=AccountSession)
def log_in(payload: LogIn, response: Response, db: DbSession) -> AccountSession:
    account = svc.log_in(db, email=payload.email, password=payload.password)
    token, ttl = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )
    _set_session(response, token, ttl, name=settings.session_cookie_name)
    return _session_body(db, account)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(response: Response) -> None:
    """쿠키를 지운다. 토큰 자체는 만료까지 유효하므로 **쿠키를 비우는 것이
    로그아웃**이다 — 화면이 토큰을 들고 있지 않으니 그것으로 충분하다."""
    _clear_session(response)


@router.get("/me", response_model=AccountSession)
def me(db: DbSession, account: CurrentAccount) -> AccountSession:
    """새로고침 뒤에도 로그인 상태를 복원하는 자리. 쿠키가 유일한 근거다."""
    return _session_body(db, account)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange, response: Response, db: DbSession, account: CurrentAccount
) -> None:
    """비밀번호 변경. **기존 세션이 전부 끊긴다.**"""
    svc.change_password(
        db, account, current=payload.current_password, new=payload.new_password
    )
    # 지금 쓰던 세션도 끊긴다. 다시 로그인하게 만드는 것이 맞다 —
    # 바꾼 이유가 유출이면 이 브라우저도 남의 것일 수 있다.
    _clear_session(response)


# ── 비밀번호 재설정 ─────────────────────────────────────────────────────────


@router.post("/password/reset-request", response_model=PasswordResetAccepted)
def request_reset(
    payload: PasswordResetRequest, request: Request, db: DbSession
) -> PasswordResetAccepted:
    """재설정 링크를 요청한다.

    **가입 여부와 무관하게 같은 응답을 냅니다.** 응답이 갈리면 이 화면이 곧
    "이 이메일이 가입돼 있나" 를 확인해 주는 도구가 됩니다.

    링크를 응답으로 돌려주지 않습니다 — 남의 이메일을 넣은 사람에게 링크가
    나가면 계정 탈취가 요청 한 번으로 끝납니다.
    """
    issued = svc.request_password_reset(db, email=payload.email)

    note: str | None = None
    if issued is not None:
        token, to = issued
        base = (settings.public_web_origin or str(request.base_url)).rstrip("/")
        mailer.send_password_reset(to=to, reset_url=f"{base}/reset-password?t={token}")

    # 메일 발송기가 없다는 사실은 **가입 여부와 무관하게** 알린다.
    # 이 문구가 계정 존재를 드러내지 않도록 조건을 붙이지 않는다.
    if settings.app_env == "local" or settings.demo_mode:
        note = (
            "메일 발송기가 아직 설정되지 않았습니다. 개발 환경에서는 링크가 "
            "서버 로그에 남습니다."
        )

    return PasswordResetAccepted(delivery_note=note)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def confirm_reset(payload: PasswordResetConfirm, response: Response, db: DbSession) -> None:
    """표를 쓰고 비밀번호를 바꾼다. 표는 한 번 쓰면 죽는다."""
    svc.reset_password(db, token=payload.token, new_password=payload.new_password)
    # 재설정하는 이유가 탈취면 이 브라우저도 남의 것일 수 있다. 다시 로그인하게 한다.
    _clear_session(response)
