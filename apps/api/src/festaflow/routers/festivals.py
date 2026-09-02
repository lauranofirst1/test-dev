"""축제 CRUD."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from festaflow.core import security
from festaflow.core.deps import CanManagePlan, CurrentOrg, DbSession, FestivalAccess
from festaflow.core.errors import not_found, quota_exceeded
from festaflow.models import (
    Booth,
    Diagnosis,
    Festival,
    FestivalPlan,
    FestivalStaff,
    Mission,
    StampBoard,
    StampTile,
)
from festaflow.models.enums import StaffRole
from festaflow.schemas.festival import (
    FestivalCreate,
    FestivalCreated,
    FestivalDetail,
    FestivalList,
    FestivalOut,
    FestivalPlanOut,
    FestivalUpdate,
    StampBoardIn,
)
from festaflow.services import media

router = APIRouter(prefix="/api/festivals", tags=["festivals"])

ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 0·O·1·I 제외


def _access_code(length: int = 6) -> str:
    return "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(length))


def _hash(code: str) -> str:
    """접근 코드는 해시만 저장한다. 평문은 발급 응답에서 1회만 노출."""
    return security.hash_access_code(code)


def _get_owned(db: DbSession, org_id: int, festival_id: int) -> Festival:
    """기관 스코프 안에서만 조회한다.

    타 기관 리소스는 403 이 아니라 **404** — 존재 여부도 노출하지 않는다.
    """
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


@router.get("", response_model=FestivalList)
def list_festivals(
    db: DbSession,
    org: CurrentOrg,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FestivalList:
    """생성 시각 내림차순, 동률이면 ID 내림차순."""
    base = select(Festival).where(
        Festival.organization_id == org.id, Festival.archived_at.is_(None)
    )
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = db.execute(
        base.order_by(Festival.created_at.desc(), Festival.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return FestivalList(items=[FestivalOut.model_validate(r) for r in rows], total=total)


@router.post(
    "",
    response_model=FestivalCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManagePlan],
)
def create_festival(payload: FestivalCreate, db: DbSession, org: CurrentOrg) -> FestivalCreated:
    """축제·기획상세·진단·스탬프보드·운영자 스태프를 **하나의 트랜잭션**으로 만든다.

    하나라도 실패하면 전부 롤백돼 부분 생성 상태가 남지 않는다.
    """
    if org.festival_quota is not None:
        used = db.execute(
            select(func.count(Festival.id)).where(
                Festival.organization_id == org.id, Festival.archived_at.is_(None)
            )
        ).scalar_one()
        if used >= org.festival_quota:
            raise quota_exceeded(org.festival_quota)

    festival = Festival(
        organization_id=org.id, **payload.model_dump(exclude={"plan", "stamp_board"})
    )
    db.add(festival)
    db.flush()

    plan_data = payload.plan.model_dump() if payload.plan else {}
    db.add(FestivalPlan(festival_id=festival.id, **plan_data))

    diagnosis = Diagnosis(festival_id=festival.id)
    db.add(diagnosis)

    # 격자를 3×3 으로 박아두면 부스가 적은 축제는 시작부터 완성이 불가능하다.
    # 요청이 고르지 않으면 스펙 기본값(3×3)을 쓴다.
    cfg = payload.stamp_board or StampBoardIn()
    board = StampBoard(
        festival_id=festival.id,
        rows=cfg.rows,
        cols=cfg.cols,
        reveal_mode=cfg.reveal_mode,
        grant_unit=cfg.grant_unit,
    )
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))

    code = _access_code()
    db.add(
        FestivalStaff(
            festival_id=festival.id,
            role=StaffRole.OPERATOR,
            display_name="운영관리자",
            access_code_hash=_hash(code),
        )
    )
    db.commit()
    db.refresh(festival)
    db.refresh(diagnosis)
    db.refresh(board)

    return FestivalCreated(
        festival=FestivalOut.model_validate(festival),
        diagnosis={"id": diagnosis.id, "status": diagnosis.status.value},
        stamp_board={
            "id": board.id,
            "version": board.version,
            "rows": board.rows,
            "cols": board.cols,
            "total_tiles": board.total_tiles,
        },
        operator_access_code=code,
    )


@router.get(
    "/{festival_id}",
    response_model=FestivalDetail,
    dependencies=[FestivalAccess],
)
def get_festival(festival_id: int, db: DbSession, org: CurrentOrg) -> FestivalDetail:
    f = _get_owned(db, org.id, festival_id)
    plan = db.get(FestivalPlan, f.id)
    booths = db.execute(
        select(func.count(Booth.id)).where(
            Booth.festival_id == f.id, Booth.archived_at.is_(None)
        )
    ).scalar_one()
    missions = db.execute(
        select(func.count(Mission.id)).where(
            Mission.festival_id == f.id, Mission.archived_at.is_(None)
        )
    ).scalar_one()

    return FestivalDetail(
        **FestivalOut.model_validate(f).model_dump(),
        plan=FestivalPlanOut.model_validate(plan) if plan else None,
        duration_days=f.duration_days,
        booth_count=booths,
        mission_count=missions,
    )


@router.put(
    "/{festival_id}",
    response_model=FestivalDetail,
    dependencies=[FestivalAccess, CanManagePlan],
)
def update_festival(
    festival_id: int, payload: FestivalUpdate, db: DbSession, org: CurrentOrg
) -> FestivalDetail:
    """`updated_at` 만 갱신한다.

    진단 이력·부스·미션·참여 기록·캠페인·스탬프 보드에는 손대지 않는다.
    """
    f = _get_owned(db, org.id, festival_id)
    for key, value in payload.model_dump(exclude={"plan"}).items():
        setattr(f, key, value)

    if payload.plan is not None:
        plan = db.get(FestivalPlan, f.id) or FestivalPlan(festival_id=f.id)
        for key, value in payload.plan.model_dump().items():
            setattr(plan, key, value)
        db.add(plan)

    db.commit()
    return get_festival(festival_id, db, org)


@router.post(
    "/{festival_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FestivalAccess, CanManagePlan],
)
def archive_festival(festival_id: int, db: DbSession, org: CurrentOrg) -> None:
    """보관. 참여 이력과 리포트는 지우지 않는다 — 목록에서만 사라진다."""
    f = _get_owned(db, org.id, festival_id)
    f.archived_at = datetime.now(UTC)
    db.commit()


@router.delete(
    "/{festival_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FestivalAccess, CanManagePlan],
)
def delete_festival(festival_id: int, db: DbSession, org: CurrentOrg) -> None:
    """축제와 모든 연관 기록을 영구 삭제한다. 복구할 수 없다."""
    f = _get_owned(db, org.id, festival_id)
    db.delete(f)
    db.commit()
    media.delete_festival_media(festival_id)
