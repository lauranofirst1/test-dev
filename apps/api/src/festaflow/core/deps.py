"""요청 의존성 — 인증과 기관 스코프.

`Authorization: Bearer <token>` 이 있으면 그것이 진실입니다. 토큰이 스태프를,
스태프가 축제를, 축제가 기관을 정합니다. 클라이언트가 기관을 고를 수 없습니다.

⚠ 아직 남은 구멍 — **기획자(planner) 자격증명이 스펙에 없습니다.**
   계약(§1)의 로그인은 축제별 스태프용이라 `festival_id` 가 필요한데,
   축제 목록·생성은 축제가 생기기 전에 호출됩니다. 기관 단위 계정 모델이
   정해지지 않아, 이 두 엔드포인트만 `X-Organization-Id` 헤더 폴백을 씁니다.

   폴백은 `APP_ENV=local` 또는 `DEMO_MODE=true` 에서만 삽니다. 그 밖의 환경에서는
   401 로 닫힙니다 — 헤더 폴백이 배포에 실려 나가면 헤더만 바꿔서 남의 기관
   데이터를 볼 수 있기 때문입니다. 기관 계정이 정해지면 폴백을 지우면 됩니다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.errors import ApiError
from festaflow.db.session import get_db
from festaflow.models import Festival, FestivalStaff, Organization, Participant
from festaflow.models.enums import StaffRole

DbSession = Annotated[Session, Depends(get_db)]

#: 기관 스코프를 클라이언트가 고를 수 있는 환경. 로컬 개발과 데모뿐이다.
def _fallback_allowed() -> bool:
    return settings.app_env == "local" or settings.demo_mode


def _auth_required() -> ApiError:
    return ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")


def get_optional_staff(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> FestivalStaff | None:
    """토큰이 있으면 스태프를, 없으면 None. 토큰이 있는데 틀리면 401."""
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(
            401, "INVALID_TOKEN", "Authorization 헤더는 `Bearer <토큰>` 형식이어야 합니다."
        )

    claims = security.decode_staff_token(token.strip())
    staff = db.execute(
        select(FestivalStaff).where(FestivalStaff.id == claims.staff_id)
    ).scalar_one_or_none()

    # 토큰은 발급 시점의 사실을 담는다. 그 뒤 비활성화되거나 축제가 옮겨졌으면
    # 서명이 맞아도 받지 않는다 — 해지가 즉시 듣지 않으면 해지가 아니다.
    if staff is None or not staff.is_active or staff.festival_id != claims.festival_id:
        raise ApiError(401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요.")
    return staff


OptionalStaff = Annotated[FestivalStaff | None, Depends(get_optional_staff)]


def require_staff(staff: OptionalStaff) -> FestivalStaff:
    """스태프 세션을 반드시 요구하는 엔드포인트용."""
    if staff is None:
        raise _auth_required()
    return staff


CurrentStaff = Annotated[FestivalStaff, Depends(require_staff)]


def get_current_org(
    db: DbSession,
    staff: OptionalStaff,
    x_organization_id: Annotated[int | None, Header(alias="X-Organization-Id")] = None,
) -> Organization:
    """요청의 기관 스코프. 토큰이 있으면 토큰이 정하고, 헤더는 보지 않는다."""
    if staff is not None:
        org = db.execute(
            select(Organization)
            .join(Festival, Festival.organization_id == Organization.id)
            .where(Festival.id == staff.festival_id)
        ).scalar_one_or_none()
        if org is None or not org.is_active:
            raise ApiError(
                401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요."
            )
        return org

    if not _fallback_allowed():
        raise _auth_required()

    if x_organization_id is not None:
        org = db.get(Organization, x_organization_id)
        if org is None or not org.is_active:
            raise ApiError(404, "NOT_FOUND", "기관을 찾을 수 없습니다.")
        return org

    # 헤더도 없으면 단일 기관 환경으로 본다(로컬 개발·데모).
    org = db.execute(
        select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.id)
    ).scalars().first()
    if org is None:
        raise ApiError(
            409,
            "NO_ORGANIZATION",
            "기관이 없습니다. 먼저 기관을 만들어 주세요.",
        )
    return org


CurrentOrg = Annotated[Organization, Depends(get_current_org)]


def require_festival_access(festival_id: int, staff: OptionalStaff) -> None:
    """스태프 토큰은 **자기 축제만** 만질 수 있다.

    기관 스코프만으로는 막히지 않는다 — 같은 기관에 축제가 여럿이면
    A 축제 운영자 토큰으로 B 축제를 읽을 수 있다.
    """
    if staff is not None and staff.festival_id != festival_id:
        raise ApiError(403, "FORBIDDEN", "이 축제에 대한 권한이 없습니다.")


def require_role(*roles: StaffRole):
    """역할 제한. 토큰이 없는 폴백 환경에서는 검사할 역할이 없어 통과시킨다."""
    allowed = {r.value for r in roles}

    def _check(staff: OptionalStaff) -> None:
        if staff is not None and staff.role.value not in allowed:
            raise ApiError(
                403,
                "FORBIDDEN",
                f"이 작업은 {', '.join(sorted(allowed))} 역할만 할 수 있습니다.",
                {"required_roles": sorted(allowed)},
            )

    return _check


#: 기획을 고치고 진단을 돌리는 쪽. 부스 관리자는 읽기만 한다.
CanManagePlan = Depends(require_role(StaffRole.PLANNER, StaffRole.OPERATOR))
FestivalAccess = Depends(require_festival_access)


# ── 참여자 ──────────────────────────────────────────────────────────────────


def get_participant(
    festival_id: int,
    db: DbSession,
    x_participant_secret: Annotated[str | None, Header(alias="X-Participant-Secret")] = None,
) -> Participant:
    """참여자 본인 조회용. 코드가 아니라 **비밀**로 인증한다.

    코드는 부스에서 스태프에게 보여주는 값이라 옆 사람도 볼 수 있다. 코드로 조회를
    허용하면 남의 수집 현황과 포인트가 들여다보인다.
    """
    if not x_participant_secret:
        raise ApiError(
            401,
            "PARTICIPANT_AUTH_REQUIRED",
            "참여자 인증이 필요합니다. 참여 코드를 다시 발급받으세요.",
        )

    hashed = security.hash_participant_secret(x_participant_secret)
    participant = db.execute(
        select(Participant).where(
            Participant.festival_id == festival_id,
            Participant.secret_hash == hashed,
        )
    ).scalar_one_or_none()
    if participant is None:
        raise ApiError(401, "PARTICIPANT_AUTH_FAILED", "참여자 정보를 확인할 수 없습니다.")
    return participant


CurrentParticipant = Annotated[Participant, Depends(get_participant)]


def require_booth_scope(staff: FestivalStaff | None, booth_id: int) -> None:
    """`booth_manager` 는 **자기 부스의 미션만** 지급할 수 있다 — 계약 §1.

    역할 검사만으로는 부족하다. booth_manager 토큰이면 부스까지 봐야 한다.
    """
    if staff is None:
        return
    if staff.role != StaffRole.BOOTH_MANAGER:
        return
    if staff.booth_id != booth_id:
        raise ApiError(
            403,
            "FORBIDDEN",
            "담당 부스의 미션만 지급할 수 있습니다.",
            {"assigned_booth_id": staff.booth_id},
        )


#: 부스·미션·보드를 고치는 쪽. 부스 관리자는 조회와 자기 부스 지급만 한다.
CanOperate = Depends(require_role(StaffRole.PLANNER, StaffRole.OPERATOR))
