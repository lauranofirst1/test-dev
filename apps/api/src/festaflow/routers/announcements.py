"""현장 공지.

**관객 경로와 스태프 경로가 나뉘어 있습니다.** 하나의 경로에 `channel` 파라미터를
두면 그 값은 요청자가 정하는 값이 되고, `?channel=staff` 한 번으로 내부 전달이
관객 화면에 뜹니다. 경계를 파라미터가 아니라 **경로**로 만든 이유입니다.

관객 경로는 인증을 요구하지 않습니다 — 참여 코드를 아직 못 받은 사람도 우천
공지는 봐야 합니다. 참여자 secret 이 실려 오면 확인 여부까지 함께 내려줍니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    CurrentParticipant,
    CurrentStaff,
    DbSession,
    FestivalAccess,
    OptionalParticipant,
    OptionalStaff,
)
from festaflow.core.errors import not_found
from festaflow.models import Announcement, Festival
from festaflow.schemas.announcement import (
    AckOut,
    AnnouncementIn,
    AnnouncementList,
    AnnouncementOut,
    AnnouncementUpdate,
    LiveAnnouncement,
    LiveAnnouncementList,
)
from festaflow.services import announcements as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["announcements"])

OPERATOR = [FestivalAccess, CanOperate]


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


def _live(db: Session, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _out(a: Announcement, *, now: datetime, ack_count: int) -> AnnouncementOut:
    live = (
        a.is_active and a.starts_at <= now and (a.ends_at is None or a.ends_at > now)
    )
    return AnnouncementOut(
        id=a.id,
        channel=a.channel,
        level=a.level,
        title=a.title,
        body=a.body,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        is_active=a.is_active,
        is_live=live,
        ack_count=ack_count,
    )


# ── 관객 ────────────────────────────────────────────────────────────────────


@router.get("/announcements/live", response_model=LiveAnnouncementList)
def live_for_audience(
    festival_id: int, db: DbSession, participant: OptionalParticipant
) -> LiveAnnouncementList:
    """관객이 지금 봐야 하는 공지.

    **채널 파라미터가 없습니다.** 서버가 관객 채널로 고정합니다.
    """
    _live(db, festival_id)
    rows = svc.live_for_audience(
        db, festival_id, participant_id=participant.id if participant else None
    )
    return LiveAnnouncementList(
        items=[
            LiveAnnouncement(
                id=x.announcement.id,
                level=x.announcement.level,
                title=x.announcement.title,
                body=x.announcement.body,
                starts_at=x.announcement.starts_at,
                acked=x.acked,
            )
            for x in rows
        ]
    )


@router.post(
    "/announcements/{announcement_id}/ack",
    response_model=AckOut,
    status_code=status.HTTP_201_CREATED,
)
def ack_as_participant(
    festival_id: int,
    announcement_id: int,
    db: DbSession,
    participant: CurrentParticipant,
) -> AckOut:
    """관객이 긴급 공지를 확인했다."""
    a = svc.get(db, festival_id, announcement_id)
    # 스태프 전용 공지를 관객이 확인할 수는 없다. id 를 찍어 보는 것만으로
    # 존재 여부가 새면 안 되므로 404 로 답한다.
    if a.channel not in svc.AUDIENCE_CHANNELS:
        raise not_found("공지")
    ack = svc.acknowledge(db, a, participant_id=participant.id)
    db.commit()
    return AckOut(announcement_id=a.id, acked_at=ack.acked_at)


# ── 스태프 ──────────────────────────────────────────────────────────────────


@router.get("/announcements/staff-live", response_model=LiveAnnouncementList)
def live_for_staff(
    festival_id: int, db: DbSession, staff: CurrentStaff
) -> LiveAnnouncementList:
    """스태프가 지금 봐야 하는 공지. **스태프 토큰이 필요합니다.**"""
    _live(db, festival_id)
    if staff.festival_id != festival_id:
        raise not_found("축제")
    rows = svc.live_for_staff(db, festival_id, staff_id=staff.id)
    return LiveAnnouncementList(
        items=[
            LiveAnnouncement(
                id=x.announcement.id,
                level=x.announcement.level,
                title=x.announcement.title,
                body=x.announcement.body,
                starts_at=x.announcement.starts_at,
                acked=x.acked,
            )
            for x in rows
        ]
    )


@router.post(
    "/announcements/{announcement_id}/staff-ack",
    response_model=AckOut,
    status_code=status.HTTP_201_CREATED,
)
def ack_as_staff(
    festival_id: int, announcement_id: int, db: DbSession, staff: CurrentStaff
) -> AckOut:
    a = svc.get(db, festival_id, announcement_id)
    if a.channel not in svc.STAFF_CHANNELS or staff.festival_id != festival_id:
        raise not_found("공지")
    ack = svc.acknowledge(db, a, staff_id=staff.id)
    db.commit()
    return AckOut(announcement_id=a.id, acked_at=ack.acked_at)


# ── 운영자 ──────────────────────────────────────────────────────────────────


@router.get("/announcements", response_model=AnnouncementList, dependencies=OPERATOR)
def list_announcements(
    festival_id: int, db: DbSession, org: CurrentOrg
) -> AnnouncementList:
    """끝난 공지도 보인다 — 무엇을 언제 띄웠는지가 기록이다."""
    _owned(db, org.id, festival_id)
    items = svc.listing(db, festival_id)
    counts = svc.ack_counts(db, [a.id for a in items])
    now = datetime.now(UTC)
    return AnnouncementList(
        items=[_out(a, now=now, ack_count=counts.get(a.id, 0)) for a in items],
        total=len(items),
    )


@router.post(
    "/announcements",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=OPERATOR,
)
def create_announcement(
    festival_id: int,
    body: AnnouncementIn,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> AnnouncementOut:
    _owned(db, org.id, festival_id)
    a = svc.create(
        db,
        festival_id,
        channel=body.channel,
        level=body.level,
        title=body.title,
        body=body.body,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        staff_id=staff.id if staff is not None else None,
    )
    db.commit()
    db.refresh(a)
    return _out(a, now=datetime.now(UTC), ack_count=0)


@router.put(
    "/announcements/{announcement_id}",
    response_model=AnnouncementOut,
    dependencies=OPERATOR,
)
def update_announcement(
    festival_id: int,
    announcement_id: int,
    body: AnnouncementUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> AnnouncementOut:
    """문구를 고치면 확인 기록이 지워진다 — 바뀐 내용을 다시 봐야 한다."""
    _owned(db, org.id, festival_id)
    a = svc.get(db, festival_id, announcement_id)
    svc.update(db, a, **body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(a)
    counts = svc.ack_counts(db, [a.id])
    return _out(a, now=datetime.now(UTC), ack_count=counts.get(a.id, 0))


@router.delete(
    "/announcements/{announcement_id}",
    response_model=AnnouncementOut,
    dependencies=OPERATOR,
)
def stop_announcement(
    festival_id: int, announcement_id: int, db: DbSession, org: CurrentOrg
) -> AnnouncementOut:
    """내리는 것이지 지우는 것이 아니다 — 무엇을 언제 띄웠는지가 기록이다."""
    _owned(db, org.id, festival_id)
    a = svc.get(db, festival_id, announcement_id)
    svc.stop(db, a)
    db.commit()
    db.refresh(a)
    counts = svc.ack_counts(db, [a.id])
    return _out(a, now=datetime.now(UTC), ack_count=counts.get(a.id, 0))
