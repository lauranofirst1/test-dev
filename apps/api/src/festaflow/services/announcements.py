"""현장 공지 — 지금 알려야 하는 것.

**보상 캠페인과 다릅니다.** 캠페인은 포인트를 바꾸는 *개입*이고, 공지는 아무것도
바꾸지 않는 *전달*입니다. 우천으로 야외 부스가 멈췄다는 사실은 포인트와 무관하게
전달돼야 합니다.

이 모듈이 지키는 것은 둘입니다.

**1. 스태프 공지가 관객에게 새지 않는다.** 관객용 조회는 채널을 인자로 받지
않습니다. 받는 순간 그 값은 요청자가 정하는 값이 되고, 경계는 문서에만 남습니다.

**2. 긴급은 확인을 받는다.** 배너로 흘려보내면 스크롤 한 번에 사라지고, 그건
안내하지 않은 것과 같습니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError, not_found
from festaflow.models import Announcement, AnnouncementAck
from festaflow.models.enums import AnnouncementChannel, AnnouncementLevel

#: 관객에게 나갈 수 있는 채널. 이 집합 밖의 값은 어떤 경로로도 관객에게 닿지 않는다.
AUDIENCE_CHANNELS = (AnnouncementChannel.AUDIENCE, AnnouncementChannel.BOTH)
STAFF_CHANNELS = (AnnouncementChannel.STAFF, AnnouncementChannel.BOTH)


@dataclass
class Live:
    """지금 떠 있어야 하는 공지."""

    announcement: Announcement
    #: 이 사람이 이미 확인했는가. 긴급 덮개를 다시 씌울지 정한다.
    acked: bool


def get(db: Session, festival_id: int, announcement_id: int) -> Announcement:
    a = db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.festival_id == festival_id,
        )
    ).scalar_one_or_none()
    if a is None:
        raise not_found("공지")
    return a


def listing(db: Session, festival_id: int) -> list[Announcement]:
    """운영자용 전체 목록. 끝난 것도 보인다 — 무엇을 언제 띄웠는지가 기록이다."""
    return list(
        db.execute(
            select(Announcement)
            .where(Announcement.festival_id == festival_id)
            .order_by(Announcement.starts_at.desc(), Announcement.id.desc())
        ).scalars()
    )


def _live_query(festival_id: int, channels: tuple[AnnouncementChannel, ...], at: datetime):
    return select(Announcement).where(
        Announcement.festival_id == festival_id,
        Announcement.channel.in_(channels),
        Announcement.is_active.is_(True),
        Announcement.starts_at <= at,
        # 종료 시각이 없으면 운영자가 끌 때까지 살아 있다.
        or_(Announcement.ends_at.is_(None), Announcement.ends_at > at),
    )


def live_for_audience(
    db: Session,
    festival_id: int,
    *,
    participant_id: int | None = None,
    now: datetime | None = None,
) -> list[Live]:
    """관객이 지금 봐야 하는 공지.

    **채널을 인자로 받지 않습니다.** 받으면 그 값은 요청자가 정하는 값이 되고,
    `channel=staff` 한 번으로 내부 전달이 관객 화면에 뜹니다. 경계는 코드가
    쥐고 있어야 합니다.
    """
    at = now or datetime.now(UTC)
    rows = list(
        db.execute(
            _live_query(festival_id, AUDIENCE_CHANNELS, at).order_by(
                # 긴급을 먼저. 화면이 다시 정렬하지 않아도 첫 건이 덮개 후보다.
                Announcement.level.desc(),
                Announcement.starts_at.desc(),
            )
        ).scalars()
    )
    acked = _acked_ids(db, [a.id for a in rows], participant_id=participant_id)
    return [Live(announcement=a, acked=a.id in acked) for a in rows]


def live_for_staff(
    db: Session, festival_id: int, *, staff_id: int | None = None, now: datetime | None = None
) -> list[Live]:
    at = now or datetime.now(UTC)
    rows = list(
        db.execute(
            _live_query(festival_id, STAFF_CHANNELS, at).order_by(
                Announcement.level.desc(), Announcement.starts_at.desc()
            )
        ).scalars()
    )
    acked = _acked_ids(db, [a.id for a in rows], staff_id=staff_id)
    return [Live(announcement=a, acked=a.id in acked) for a in rows]


def _acked_ids(
    db: Session,
    announcement_ids: list[int],
    *,
    participant_id: int | None = None,
    staff_id: int | None = None,
) -> set[int]:
    if not announcement_ids or (participant_id is None and staff_id is None):
        return set()
    where = [AnnouncementAck.announcement_id.in_(announcement_ids)]
    if participant_id is not None:
        where.append(AnnouncementAck.participant_id == participant_id)
    else:
        where.append(AnnouncementAck.staff_id == staff_id)
    return {
        int(x)
        for x in db.execute(select(AnnouncementAck.announcement_id).where(*where)).scalars()
    }


def create(
    db: Session,
    festival_id: int,
    *,
    channel: AnnouncementChannel,
    level: AnnouncementLevel,
    title: str,
    body: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    staff_id: int | None = None,
) -> Announcement:
    starts = _aware(starts_at) if starts_at else datetime.now(UTC)
    ends = _aware(ends_at) if ends_at else None
    _validate(starts, ends)

    a = Announcement(
        festival_id=festival_id,
        channel=channel,
        level=level,
        title=title.strip(),
        body=body.strip(),
        starts_at=starts,
        ends_at=ends,
        created_by_staff_id=staff_id,
    )
    db.add(a)
    db.flush()
    return a


def update(db: Session, announcement: Announcement, **fields) -> Announcement:
    """문구를 고치면 **확인 기록을 지웁니다.**

    "야외 부스 중단" 을 확인한 사람에게 "행사 전체 종료" 로 바뀐 같은 공지가 다시
    안 뜨면, 그 사람은 바뀐 내용을 영영 못 봅니다. 같은 행을 재사용하는 이상
    확인은 그 문구에 대한 확인이지 그 행에 대한 확인이 아닙니다.

    등급이나 채널만 바뀌어도 마찬가지입니다 — 일반이던 것이 긴급이 됐다면 그건
    다시 봐야 하는 것입니다.
    """
    if "starts_at" in fields and fields["starts_at"] is not None:
        fields["starts_at"] = _aware(fields["starts_at"])
    if fields.get("ends_at") is not None:
        fields["ends_at"] = _aware(fields["ends_at"])

    watched = ("title", "body", "level", "channel")
    changed = any(
        key in fields and fields[key] is not None and fields[key] != getattr(announcement, key)
        for key in watched
    )

    for key, value in fields.items():
        setattr(announcement, key, value.strip() if isinstance(value, str) else value)

    _validate(announcement.starts_at, announcement.ends_at)

    if changed:
        db.query(AnnouncementAck).filter(
            AnnouncementAck.announcement_id == announcement.id
        ).delete(synchronize_session=False)

    db.flush()
    return announcement


def stop(db: Session, announcement: Announcement) -> Announcement:
    """공지를 내린다. **행을 지우지 않습니다.**

    무엇을 언제 띄웠고 몇 명이 봤는지가 사후에 답해야 하는 질문입니다 —
    특히 안전 공지에서요.
    """
    announcement.is_active = False
    db.flush()
    return announcement


def acknowledge(
    db: Session,
    announcement: Announcement,
    *,
    participant_id: int | None = None,
    staff_id: int | None = None,
) -> AnnouncementAck:
    """긴급 공지를 확인했다고 기록한다."""
    if announcement.level != AnnouncementLevel.URGENT:
        # 일반 공지는 배너라 확인이라는 개념이 없다. 조용히 받아 주면
        # 확인 수가 의미 없이 부풀어 긴급 공지의 도달률을 읽을 수 없게 된다.
        raise ApiError(
            409,
            "NOT_URGENT",
            "일반 공지는 확인을 기록하지 않습니다.",
            {"level": announcement.level.value},
        )
    if (participant_id is None) == (staff_id is None):
        raise ApiError(400, "IDENTITY_REQUIRED", "누가 확인했는지 알 수 없습니다.")

    ack = AnnouncementAck(
        announcement_id=announcement.id, participant_id=participant_id, staff_id=staff_id
    )
    try:
        with db.begin_nested():
            db.add(ack)
            db.flush()
    except IntegrityError:
        # 덮개를 두 번 눌렀다. 두 번째는 아무 일도 아니다.
        if ack in db:
            db.expunge(ack)
        where = [AnnouncementAck.announcement_id == announcement.id]
        where.append(
            AnnouncementAck.participant_id == participant_id
            if participant_id is not None
            else AnnouncementAck.staff_id == staff_id
        )
        return db.execute(select(AnnouncementAck).where(*where)).scalar_one()
    return ack


def ack_counts(db: Session, announcement_ids: list[int]) -> dict[int, int]:
    """공지별 확인 인원. 띄운 것과 전달된 것은 다르다."""
    if not announcement_ids:
        return {}
    rows = db.execute(
        select(AnnouncementAck.announcement_id, func.count(AnnouncementAck.id))
        .where(AnnouncementAck.announcement_id.in_(announcement_ids))
        .group_by(AnnouncementAck.announcement_id)
    ).all()
    return {int(a): int(n) for a, n in rows}


def _aware(value: datetime) -> datetime:
    """타임존 없는 시각을 UTC 로 본다. DB 컬럼이 aware 라 naive 와 비교하면 터진다."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _validate(starts_at: datetime, ends_at: datetime | None) -> None:
    if ends_at is not None and ends_at <= starts_at:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "종료 시각이 시작 시각보다 뒤여야 합니다.",
            {"field": "ends_at"},
        )
