"""스태프 인증 — docs/03-api-contract.md §1.

**2단계 로그인.** 초대 QR 은 `/staff/login?f={festival_id}&s={staff_id}` 를 담고
거기엔 비밀이 없습니다. 세션은 6자리 접근 코드를 맞혀야 발급됩니다.
QR 사진이 유출돼도 코드 없이는 들어올 수 없습니다.

실패 응답은 무엇이 틀렸는지 알려주지 않습니다 — 축제가 없는 것과 스태프가 없는 것과
코드가 틀린 것을 구분해주면, 응답만 보고 유효한 staff_id 를 찾아낼 수 있습니다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.deps import DbSession
from festaflow.core.errors import ApiError
from festaflow.models import Festival, FestivalStaff
from festaflow.schemas.auth import StaffInfo, StaffLogin, StaffSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _invalid() -> ApiError:
    """축제·스태프·코드 중 무엇이 틀렸는지 밝히지 않는 하나의 실패."""
    return ApiError(
        401,
        "INVALID_CREDENTIALS",
        "축제·스태프·접근 코드가 맞지 않습니다. 초대 QR 을 다시 확인하세요.",
    )


@router.post("/staff/login", response_model=StaffSession)
def staff_login(payload: StaffLogin, db: DbSession) -> StaffSession:
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

    assert staff is not None  # 위 조건이 참이면 staff 는 있다 (타입 좁히기)
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
    return StaffSession(
        access_token=token,
        expires_in=expires_in,
        staff=StaffInfo.model_validate(staff),
    )
