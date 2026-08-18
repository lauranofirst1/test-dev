"""부스 · 미션 · 스태프 지급 — docs/03-api-contract.md §4, §8.1, §8.2, §8.4."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    DbSession,
    FestivalAccess,
    OptionalStaff,
    require_booth_scope,
)
from festaflow.core.errors import ApiError, not_found, validation_failed
from festaflow.models import Booth, Festival, Mission, Participant, Participation
from festaflow.models.enums import BoothVerifyMode
from festaflow.schemas.booth import (
    BoothCreate,
    BoothCreated,
    BoothDetail,
    BoothIn,
    BoothList,
    BoothOut,
    MissionCreate,
    MissionIn,
    MissionList,
    MissionOut,
    ScanToken,
)
from festaflow.schemas.participation import (
    BoardProgress,
    GrantResult,
    ParticipationOut,
    RecentGrant,
    RevealedTile,
    StaffGrantIn,
)
from festaflow.services import grants as svc

router = APIRouter(
    prefix="/api/festivals/{festival_id}",
    tags=["booths"],
    dependencies=[FestivalAccess],
)


def _festival(db: Session, org_id: int, festival_id: int) -> Festival:
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


def _booth(db: Session, festival_id: int, booth_id: int) -> Booth:
    b = db.execute(
        select(Booth).where(
            Booth.id == booth_id,
            Booth.festival_id == festival_id,
            Booth.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if b is None:
        raise not_found("부스")
    return b


def _missions_of(db: Session, booth_id: int) -> list[Mission]:
    return list(
        db.execute(
            select(Mission)
            .where(Mission.booth_id == booth_id, Mission.archived_at.is_(None))
            .order_by(Mission.id)
        ).scalars()
    )


def _detail(db: Session, booth: Booth) -> BoothDetail:
    return BoothDetail(
        **BoothOut.model_validate(booth).model_dump(),
        missions=[MissionOut.model_validate(m) for m in _missions_of(db, booth.id)],
    )


def _duplicate_name(exc: IntegrityError) -> bool:
    return "uq_booths_festival_name" in str(exc.orig)


# ── 부스 ────────────────────────────────────────────────────────────────────


@router.get("/booths", response_model=BoothList)
def list_booths(
    festival_id: int,
    db: DbSession,
    org: CurrentOrg,
    include_inactive: bool = Query(True),
) -> BoothList:
    _festival(db, org.id, festival_id)
    stmt = select(Booth).where(Booth.festival_id == festival_id, Booth.archived_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(Booth.is_active.is_(True))
    rows = list(db.execute(stmt.order_by(Booth.id)).scalars())
    return BoothList(items=[_detail(db, b) for b in rows], total=len(rows))


@router.post(
    "/booths",
    response_model=BoothCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanOperate],
)
def create_booth(
    festival_id: int, payload: BoothCreate, db: DbSession, org: CurrentOrg
) -> BoothCreated:
    """부스와 첫 미션을 **한 트랜잭션**으로 만든다.

    미션의 `booth_id` 는 요청 값을 쓰지 않고 방금 만든 부스 ID 로 **강제 설정**한다.
    다른 부스 ID 가 들어와도 무시한다 — 계약 §4.
    """
    festival = _festival(db, org.id, festival_id)

    booth = Booth(festival_id=festival.id, **payload.model_dump(exclude={"first_mission"}))
    try:
        # savepoint 로 감싸고 **add 도 그 안에서** 한다. db.rollback() 을 부르면
        # 트랜잭션 전체가 날아가고, add 를 savepoint 밖에서 하면 flush 실패가
        # 바깥 트랜잭션까지 무효화해 이후 쿼리가 PendingRollbackError 로 죽는다.
        with db.begin_nested():
            db.add(booth)
            db.flush()
    except IntegrityError as exc:
        if booth in db:
            db.expunge(booth)
        if _duplicate_name(exc):
            raise validation_failed("같은 이름의 부스가 이미 있습니다.", "name") from exc
        raise

    mission: Mission | None = None
    if payload.first_mission is not None:
        mission = Mission(
            festival_id=festival.id,
            booth_id=booth.id,  # 요청 값이 아니라 방금 만든 부스
            **payload.first_mission.model_dump(),
        )
        db.add(mission)
        db.flush()

    db.commit()
    db.refresh(booth)
    if mission is not None:
        db.refresh(mission)

    return BoothCreated(
        booth=BoothOut.model_validate(booth),
        first_mission=MissionOut.model_validate(mission) if mission else None,
    )


@router.put("/booths/{booth_id}", response_model=BoothDetail, dependencies=[CanOperate])
def update_booth(
    festival_id: int, booth_id: int, payload: BoothIn, db: DbSession, org: CurrentOrg
) -> BoothDetail:
    _festival(db, org.id, festival_id)
    booth = _booth(db, festival_id, booth_id)
    try:
        with db.begin_nested():
            for k, v in payload.model_dump().items():
                setattr(booth, k, v)
            db.flush()
    except IntegrityError as exc:
        # savepoint 는 DB 를 되돌리지만 메모리의 인스턴스는 새 값을 들고 있다.
        db.expire(booth)
        if _duplicate_name(exc):
            raise validation_failed("같은 이름의 부스가 이미 있습니다.", "name") from exc
        raise
    db.commit()
    db.refresh(booth)
    return _detail(db, booth)


@router.post(
    "/booths/{booth_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanOperate],
)
def archive_booth(festival_id: int, booth_id: int, db: DbSession, org: CurrentOrg) -> None:
    """보관. 소속 미션은 미배정으로, 보드 타일 배정은 해제한다 — 데이터모델 §6.

    지급 이력(`participations.booth_id`)은 건드리지 않는다. 과거 집계가 이동하면
    운영 인사이트와 사후 리포트의 숫자가 소급해서 바뀐다.
    """
    from datetime import UTC, datetime

    from festaflow.models import StampTile

    _festival(db, org.id, festival_id)
    booth = _booth(db, festival_id, booth_id)

    booth.archived_at = datetime.now(UTC)
    booth.is_active = False
    for m in _missions_of(db, booth.id):
        m.booth_id = None
    for tile in db.execute(
        select(StampTile).where(StampTile.assigned_booth_id == booth.id)
    ).scalars():
        tile.assigned_booth_id = None
    db.commit()


# ── 미션 ────────────────────────────────────────────────────────────────────


@router.get("/missions", response_model=MissionList)
def list_missions(festival_id: int, db: DbSession, org: CurrentOrg) -> MissionList:
    _festival(db, org.id, festival_id)
    rows = list(
        db.execute(
            select(Mission)
            .where(Mission.festival_id == festival_id, Mission.archived_at.is_(None))
            .order_by(Mission.id)
        ).scalars()
    )
    return MissionList(items=[MissionOut.model_validate(m) for m in rows], total=len(rows))


@router.post(
    "/missions",
    response_model=MissionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanOperate],
)
def create_mission(
    festival_id: int, payload: MissionCreate, db: DbSession, org: CurrentOrg
) -> MissionOut:
    festival = _festival(db, org.id, festival_id)

    if payload.booth_id is not None:
        # 타 축제 부스에 미션을 붙이면 지급 화면이 축제 경계를 넘는다.
        booth = db.get(Booth, payload.booth_id)
        if booth is None or booth.festival_id != festival.id or booth.archived_at is not None:
            raise ApiError(
                400,
                "MISSION_BOOTH_FESTIVAL_MISMATCH",
                "이 축제의 부스가 아닙니다.",
                {"booth_id": payload.booth_id},
            )

    mission = Mission(festival_id=festival.id, **payload.model_dump())
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return MissionOut.model_validate(mission)


@router.put("/missions/{mission_id}", response_model=MissionOut, dependencies=[CanOperate])
def update_mission(
    festival_id: int, mission_id: int, payload: MissionIn, db: DbSession, org: CurrentOrg
) -> MissionOut:
    _festival(db, org.id, festival_id)
    mission = db.execute(
        select(Mission).where(
            Mission.id == mission_id,
            Mission.festival_id == festival_id,
            Mission.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if mission is None:
        raise not_found("미션")
    for k, v in payload.model_dump().items():
        setattr(mission, k, v)
    db.commit()
    db.refresh(mission)
    return MissionOut.model_validate(mission)


@router.post(
    "/missions/{mission_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanOperate],
)
def archive_mission(festival_id: int, mission_id: int, db: DbSession, org: CurrentOrg) -> None:
    from datetime import UTC, datetime

    _festival(db, org.id, festival_id)
    mission = db.execute(
        select(Mission).where(Mission.id == mission_id, Mission.festival_id == festival_id)
    ).scalar_one_or_none()
    if mission is None:
        raise not_found("미션")
    mission.archived_at = datetime.now(UTC)
    mission.is_active = False
    db.commit()


# ── 부스 QR 토큰 (§8.2) ─────────────────────────────────────────────────────


@router.get("/booths/{booth_id}/scan-token", response_model=ScanToken)
def scan_token(
    festival_id: int, booth_id: int, request: Request, db: DbSession, org: CurrentOrg,
    staff: OptionalStaff,
) -> ScanToken:
    """부스 화면용 회전 토큰. `qr_secret` 은 내려주지 않는다."""
    _festival(db, org.id, festival_id)
    booth = _booth(db, festival_id, booth_id)
    require_booth_scope(staff, booth.id)

    if booth.verify_mode != BoothVerifyMode.PARTICIPANT_SCAN:
        raise ApiError(
            409,
            "BOOTH_MODE_MISMATCH",
            "이 부스는 스태프가 참여자 QR 을 스캔하는 방식입니다. 회전 QR 을 쓰지 않습니다.",
            {"verify_mode": booth.verify_mode.value},
        )

    window = security.current_window()
    token = security.booth_scan_token(booth.qr_secret, booth.id, window)
    base = str(request.base_url).rstrip("/")
    return ScanToken(
        booth_id=booth.id,
        scan_url=f"{base}/join/{festival_id}/scan?b={booth.id}&t={token}",
        window_index=window,
        expires_at=security.window_expires_at(window),
        refresh_after_seconds=settings.scan_token_window_seconds,
    )


# ── 스태프 지급 (§8.1) ──────────────────────────────────────────────────────


@router.post("/booths/{booth_id}/grants", response_model=GrantResult)
def staff_grant(
    festival_id: int,
    booth_id: int,
    payload: StaffGrantIn,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> GrantResult:
    """스태프가 참여자 QR 을 스캔해 지급한다.

    `booth_manager` 는 자기 부스만, `operator` 는 축제 전체를 지급할 수 있다.
    """
    festival = _festival(db, org.id, festival_id)
    booth = _booth(db, festival_id, booth_id)
    require_booth_scope(staff, booth.id)

    if booth.verify_mode != BoothVerifyMode.STAFF_SCAN:
        raise ApiError(
            409,
            "BOOTH_MODE_MISMATCH",
            "이 부스는 참여자가 부스 QR 을 스캔하는 방식입니다.",
            {"verify_mode": booth.verify_mode.value},
        )

    participant = svc.find_participant(db, festival_id, payload.participant_code)
    mission = db.get(Mission, payload.mission_id)
    if mission is None or mission.festival_id != festival_id:
        raise not_found("미션")

    outcome = svc.grant(
        db,
        festival=festival,
        booth=booth,
        mission=mission,
        participant=participant,
        verified_via=BoothVerifyMode.STAFF_SCAN,
        granted_by_staff_id=staff.id if staff else None,
        client_request_id=payload.client_request_id,
    )
    db.commit()
    return _result(outcome)


def _result(outcome: svc.GrantOutcome) -> GrantResult:
    return GrantResult(
        was_already_granted=outcome.was_already_granted,
        participation=ParticipationOut.model_validate(outcome.participation),
        revealed_tile=(
            RevealedTile(
                tile_index=outcome.revealed_tile.tile_index,
                board_version=outcome.revealed_tile.board_version,
            )
            if outcome.revealed_tile is not None
            else None
        ),
        board_progress=BoardProgress(
            revealed_count=outcome.progress.revealed_count,
            total_tiles=outcome.progress.total_tiles,
            is_complete=outcome.progress.is_complete,
        ),
    )


# ── 최근 지급 (§8.4) ────────────────────────────────────────────────────────


@router.get("/booths/{booth_id}/grants/recent", response_model=list[RecentGrant])
def recent_grants(
    festival_id: int,
    booth_id: int,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
    limit: int = Query(8, ge=1, le=50),
) -> list[RecentGrant]:
    """부스 화면의 "방금 지급됨" 목록. 참여자 코드는 부스 스태프에게만 보인다."""
    _festival(db, org.id, festival_id)
    booth = _booth(db, festival_id, booth_id)
    require_booth_scope(staff, booth.id)

    rows = db.execute(
        select(Participation, Participant.code, Mission.title)
        .join(Participant, Participant.id == Participation.participant_id)
        .outerjoin(Mission, Mission.id == Participation.mission_id)
        .where(Participation.booth_id == booth.id, Participation.completed_at.is_not(None))
        .order_by(Participation.completed_at.desc(), Participation.id.desc())
        .limit(limit)
    ).all()

    return [
        RecentGrant(
            participation_id=p.id,
            participant_code=code,
            mission_title=title,
            granted_points=p.granted_points,
            completed_at=p.completed_at,
        )
        for p, code, title in rows
    ]
