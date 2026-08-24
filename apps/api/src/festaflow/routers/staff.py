"""스태프 발급 · 목록 · 재발급 · 비활성화 — 계약 §1.

**평문 접근 코드는 발급·재발급 응답에서만 나옵니다.** 저장하는 것은 bcrypt
해시뿐이라 서버도 다시 알아낼 수 없습니다. 잃어버리면 재발급이 유일한 길이며,
그게 맞습니다 — 서버가 되읽을 수 있다면 유출됐을 때 전부 함께 나갑니다.

**삭제하지 않고 비활성화합니다.** 스태프 행을 지우면 그가 지급한 참여 이력의
`granted_by_staff_id` 가 끊기고, 사후에 "누가 줬는지" 를 말할 수 없게 됩니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    DbSession,
    FestivalAccess,
)
from festaflow.core.errors import ApiError, not_found, validation_failed
from festaflow.models import Booth, Festival, FestivalStaff
from festaflow.models.enums import StaffRole
from festaflow.schemas.auth import (
    StaffInfo,
    StaffIssue,
    StaffIssued,
    StaffList,
    StaffRow,
)

router = APIRouter(
    prefix="/api/festivals/{festival_id}",
    tags=["staff"],
    dependencies=[FestivalAccess],
)


def _owned(db: Session, org_id: int, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(
            Festival.id == festival_id,
            Festival.organization_id == org_id,
            Festival.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _staff(db: Session, festival_id: int, staff_id: int) -> FestivalStaff:
    s = db.execute(
        select(FestivalStaff).where(
            FestivalStaff.id == staff_id, FestivalStaff.festival_id == festival_id
        )
    ).scalar_one_or_none()
    if s is None:
        raise not_found("스태프")
    return s


def _invite(request: Request, festival_id: int, staff_id: int) -> tuple[str, str]:
    """초대 링크의 (경로, 전체 주소). **비밀이 담기지 않습니다** — 접근 코드는
    따로 전달합니다. 링크 사진이 유출돼도 코드 없이는 들어올 수 없는 것이
    2단계 로그인의 요점입니다.

    경로를 따로 주는 이유는 부스 QR 과 같습니다 — `request.base_url` 은 **API
    서버** 주소라, 프런트가 따로 뜬 환경에서는 `/staff/login` 이 없는 곳을
    가리킵니다. 브라우저는 자기 오리진을 붙여 쓰면 언제나 맞습니다.
    """
    path = f"/staff/login?f={festival_id}&s={staff_id}"
    base = (settings.public_web_origin or str(request.base_url)).rstrip("/")
    return path, f"{base}{path}"


def _check_booth(db: Session, festival: Festival, payload: StaffIssue) -> None:
    """`booth_manager` 는 부스가 있어야 의미가 있다.

    부스를 안 정하면 그 스태프는 **어느 부스에도 지급할 수 없습니다** —
    `require_booth_scope` 가 `staff.booth_id != booth_id` 로 전부 막습니다.
    발급은 성공했는데 현장에서 아무것도 못 하는 상태가 되므로 여기서 막습니다.
    """
    if payload.role != StaffRole.BOOTH_MANAGER:
        return
    if payload.booth_id is None:
        raise validation_failed(
            "부스 관리자는 담당 부스를 정해야 합니다. 부스 없이 발급하면 "
            "현장에서 아무 미션도 지급할 수 없습니다.",
            "booth_id",
        )
    booth = db.get(Booth, payload.booth_id)
    if booth is None or booth.festival_id != festival.id or booth.archived_at is not None:
        raise validation_failed("이 축제의 부스가 아닙니다.", "booth_id")


@router.get("/staff", response_model=StaffList)
def list_staff(festival_id: int, db: DbSession, org: CurrentOrg) -> StaffList:
    """스태프 목록. **코드 해시는 나가지 않습니다.**"""
    _owned(db, org.id, festival_id)
    rows = list(
        db.execute(
            select(FestivalStaff)
            .where(FestivalStaff.festival_id == festival_id)
            .order_by(FestivalStaff.is_active.desc(), FestivalStaff.id)
        ).scalars()
    )
    return StaffList(items=[StaffRow.model_validate(s) for s in rows], total=len(rows))


@router.post(
    "/staff",
    response_model=StaffIssued,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanOperate],
)
def issue_staff(
    festival_id: int,
    payload: StaffIssue,
    request: Request,
    db: DbSession,
    org: CurrentOrg,
) -> StaffIssued:
    """스태프를 발급한다. 평문 코드는 이 응답에서만 나온다."""
    festival = _owned(db, org.id, festival_id)
    _check_booth(db, festival, payload)

    code = security.generate_access_code()
    staff = FestivalStaff(
        festival_id=festival.id,
        display_name=payload.display_name.strip(),
        role=payload.role,
        booth_id=payload.booth_id if payload.role == StaffRole.BOOTH_MANAGER else None,
        access_code_hash=security.hash_access_code(code),
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)

    path, url = _invite(request, festival.id, staff.id)
    return StaffIssued(
        staff=StaffInfo.model_validate(staff),
        invite_path=path,
        invite_url=url,
        access_code=code,
    )


@router.post("/staff/{staff_id}/rotate", response_model=StaffIssued, dependencies=[CanOperate])
def rotate_access_code(
    festival_id: int, staff_id: int, request: Request, db: DbSession, org: CurrentOrg
) -> StaffIssued:
    """접근 코드를 다시 발급한다. **옛 코드는 그 순간 죽습니다.**

    코드를 잃어버렸을 때와, 코드가 돌고 있다는 걸 알았을 때 쓰는 같은 버튼입니다.
    잠금도 함께 풉니다 — 재발급했는데 잠긴 채로 두면 새 코드로도 못 들어옵니다.
    """
    _owned(db, org.id, festival_id)
    staff = _staff(db, festival_id, staff_id)

    code = security.generate_access_code()
    staff.access_code_hash = security.hash_access_code(code)
    staff.failed_attempts = 0
    staff.locked_until = None
    db.commit()
    db.refresh(staff)

    path, url = _invite(request, festival_id, staff.id)
    return StaffIssued(
        staff=StaffInfo.model_validate(staff),
        invite_path=path,
        invite_url=url,
        access_code=code,
    )


@router.delete(
    "/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CanOperate]
)
def deactivate_staff(
    festival_id: int, staff_id: int, db: DbSession, org: CurrentOrg
) -> None:
    """비활성화. **행을 지우지 않습니다** — 지급 이력의 "누가 줬는지" 가 끊긴다."""
    _owned(db, org.id, festival_id)
    staff = _staff(db, festival_id, staff_id)
    staff.is_active = False
    db.commit()


@router.post(
    "/staff/{staff_id}/reactivate", response_model=StaffRow, dependencies=[CanOperate]
)
def reactivate_staff(
    festival_id: int, staff_id: int, db: DbSession, org: CurrentOrg
) -> StaffRow:
    """다시 활성화. 잠금도 함께 푼다.

    코드는 그대로다 — 비활성화가 코드 유출을 뜻하는 것은 아니므로, 바꿀지 말지는
    운영자가 재발급 버튼으로 따로 고른다.
    """
    _owned(db, org.id, festival_id)
    staff = _staff(db, festival_id, staff_id)
    staff.is_active = True
    staff.failed_attempts = 0
    staff.locked_until = None
    db.commit()
    db.refresh(staff)
    return StaffRow.model_validate(staff)


@router.post("/staff/{staff_id}/unlock", response_model=StaffRow, dependencies=[CanOperate])
def unlock_staff(festival_id: int, staff_id: int, db: DbSession, org: CurrentOrg) -> StaffRow:
    """잠금만 푼다. 코드를 아는 사람이 오타를 반복한 경우에 쓴다."""
    _owned(db, org.id, festival_id)
    staff = _staff(db, festival_id, staff_id)
    if staff.locked_until is None and staff.failed_attempts == 0:
        raise ApiError(409, "NOT_LOCKED", "잠겨 있지 않습니다.")
    staff.failed_attempts = 0
    staff.locked_until = None
    db.commit()
    db.refresh(staff)
    return StaffRow.model_validate(staff)
