"""참여자 · 공개 정보 · 참여자 스캔 지급 — docs/03-api-contract.md §8.3, §9.

이 라우터는 **기관 스코프를 쓰지 않습니다.** 관객은 로그인하지 않고 축제 링크로
들어옵니다. 대신 조회 범위를 축제 하나로 못 박고, 본인 데이터는
`X-Participant-Secret` 으로만 열어 줍니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.deps import CurrentParticipant, DbSession
from festaflow.core.errors import ApiError, not_found
from festaflow.models import Booth, Festival, Mission, Participation
from festaflow.models.enums import BoothVerifyMode
from festaflow.schemas.participation import (
    ActiveCampaign,
    GrantResult,
    MissionStatus,
    ParticipantIssued,
    ParticipantMe,
    PublicBooth,
    PublicFestival,
    PublicMission,
    ScanContext,
    ScanContextMission,
    ScanGrantIn,
)
from festaflow.services import grants as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["participants"])


def _live_festival(db: Session, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _active_booths(db: Session, festival_id: int) -> list[Booth]:
    return list(
        db.execute(
            select(Booth)
            .where(
                Booth.festival_id == festival_id,
                Booth.archived_at.is_(None),
                Booth.is_active.is_(True),
            )
            .order_by(Booth.id)
        ).scalars()
    )


def _active_missions(db: Session, festival_id: int) -> list[Mission]:
    return list(
        db.execute(
            select(Mission)
            .where(
                Mission.festival_id == festival_id,
                Mission.archived_at.is_(None),
                Mission.is_active.is_(True),
                Mission.booth_id.is_not(None),
            )
            .order_by(Mission.id)
        ).scalars()
    )


# ── 공개 정보 ───────────────────────────────────────────────────────────────


@router.get("/public", response_model=PublicFestival)
def public_festival(festival_id: int, db: DbSession) -> PublicFestival:
    """참여 전 관객이 보는 화면. 인증이 없으므로 운영 정보는 담지 않는다."""
    festival = _live_festival(db, festival_id)
    missions = _active_missions(db, festival_id)
    by_booth: dict[int, list[Mission]] = {}
    for m in missions:
        by_booth.setdefault(m.booth_id, []).append(m)

    return PublicFestival(
        id=festival.id,
        name=festival.name,
        region=festival.region,
        venue=festival.venue,
        starts_on=festival.starts_on.isoformat(),
        ends_on=festival.ends_on.isoformat(),
        booths=[
            PublicBooth(
                id=b.id,
                name=b.name,
                booth_type=b.booth_type,
                type_label=b.type_label,
                location=b.location,
                verify_mode=b.verify_mode,
                missions=[PublicMission.model_validate(m) for m in by_booth.get(b.id, [])],
            )
            for b in _active_booths(db, festival_id)
        ],
    )


# ── 발급 · 본인 조회 ────────────────────────────────────────────────────────


@router.post(
    "/participants", response_model=ParticipantIssued, status_code=status.HTTP_201_CREATED
)
def issue_participant(festival_id: int, db: DbSession) -> ParticipantIssued:
    """참여 코드를 발급한다. 이름·연락처를 받지 않는다 — 익명 참여가 기본이다."""
    festival = _live_festival(db, festival_id)
    participant, secret = svc.issue_participant(db, festival)
    db.commit()
    db.refresh(participant)
    return ParticipantIssued(
        code=participant.code, secret=secret, festival_id=festival.id
    )


@router.get("/participants/me", response_model=ParticipantMe)
def participant_me(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> ParticipantMe:
    """미션별 지급 상태와 포인트 합계. 활성 캠페인 안내를 함께 싣는다."""
    _live_festival(db, festival_id)

    granted = {
        p.mission_id: p
        for p in db.execute(
            select(Participation).where(
                Participation.participant_id == participant.id,
                Participation.mission_id.is_not(None),
            )
        ).scalars()
    }
    booth_names = {
        b.id: b.name for b in _active_booths(db, festival_id)
    }

    statuses: list[MissionStatus] = []
    for m in _active_missions(db, festival_id):
        p = granted.get(m.id)
        statuses.append(
            MissionStatus(
                mission_id=m.id,
                booth_id=m.booth_id,
                booth_name=booth_names.get(m.booth_id),
                title=m.title,
                points=m.points,
                status="granted" if p else "pending",
                granted_points=p.granted_points if p else None,
                completed_at=p.completed_at if p else None,
            )
        )

    total = db.execute(
        select(func.coalesce(func.sum(Participation.granted_points), 0)).where(
            Participation.participant_id == participant.id
        )
    ).scalar_one()

    participant.last_seen_at = datetime.now(UTC)
    db.commit()

    return ParticipantMe(
        code=participant.code,
        festival_id=festival_id,
        total_points=int(total),
        completed_count=len(granted),
        missions=statuses,
        active_campaigns=[
            ActiveCampaign(
                id=c.id,
                booth_id=c.booth_id,
                mission_id=c.mission_id,
                title=c.title,
                message=c.message,
                bonus_points=c.bonus_points,
                ends_at=c.ends_at,
            )
            for c in svc.active_campaigns(db, festival_id)
        ],
    )


# ── 부스 QR 스캔 (§8.3) ─────────────────────────────────────────────────────


def _scan_booth(db: Session, festival_id: int, booth_id: int) -> Booth:
    booth = db.execute(
        select(Booth).where(
            Booth.id == booth_id,
            Booth.festival_id == festival_id,
            Booth.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if booth is None:
        raise not_found("부스")
    if booth.verify_mode != BoothVerifyMode.PARTICIPANT_SCAN:
        raise ApiError(
            409,
            "BOOTH_MODE_MISMATCH",
            "이 부스는 스태프가 확인해 지급합니다. 스태프에게 참여 코드를 보여주세요.",
            {"verify_mode": booth.verify_mode.value},
        )
    return booth


@router.get("/scan", response_model=ScanContext)
def scan_context(
    festival_id: int,
    db: DbSession,
    participant: CurrentParticipant,
    booth_id: int = Query(...),
    token: str = Query(...),
) -> ScanContext:
    """스캔 직후 미션 선택 화면에 필요한 것만 돌려준다.

    `experience_config` 는 내려가지 않는다 — quiz 의 `answer_index` 가 거기 있고,
    채점은 서버에서만 한다.
    """
    _live_festival(db, festival_id)
    booth = _scan_booth(db, festival_id, booth_id)
    window = svc.verify_scan_token(booth, token)

    from festaflow.core import security

    expires_at = security.window_expires_at(window)
    granted = {
        p.mission_id
        for p in db.execute(
            select(Participation).where(
                Participation.participant_id == participant.id,
                Participation.mission_id.is_not(None),
            )
        ).scalars()
    }

    missions = [m for m in _active_missions(db, festival_id) if m.booth_id == booth.id]
    return ScanContext(
        booth_id=booth.id,
        booth_name=booth.name,
        type_label=booth.type_label,
        location=booth.location,
        window_index=window,
        expires_at=expires_at,
        seconds_remaining=max(0, int((expires_at - datetime.now(UTC)).total_seconds())),
        missions=[
            ScanContextMission(
                mission_id=m.id,
                title=m.title,
                description=m.description,
                points=m.points,
                already_granted=m.id in granted,
            )
            for m in missions
        ],
        scan_already_used=svc.scan_used_in_window(
            db, booth_id=booth.id, window_index=window, participant_id=participant.id
        ),
    )


@router.post("/scan-grants", response_model=GrantResult)
def scan_grant(
    festival_id: int,
    payload: ScanGrantIn,
    db: DbSession,
    participant: CurrentParticipant,
) -> GrantResult:
    """참여자가 부스 QR 을 스캔해 지급받는다. 1 스캔 = 1 미션."""
    festival = _live_festival(db, festival_id)
    booth = _scan_booth(db, festival_id, payload.booth_id)
    window = svc.verify_scan_token(booth, payload.token)

    mission = db.get(Mission, payload.mission_id)
    if mission is None or mission.festival_id != festival_id:
        raise not_found("미션")

    outcome = svc.grant(
        db,
        festival=festival,
        booth=booth,
        mission=mission,
        participant=participant,
        verified_via=BoothVerifyMode.PARTICIPANT_SCAN,
        scan_window_index=window,
        client_request_id=payload.client_request_id,
    )
    db.commit()

    from festaflow.routers.booths import _result

    return _result(outcome)
