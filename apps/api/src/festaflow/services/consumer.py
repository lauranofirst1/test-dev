"""Consumer source ownership helpers.

The source models stay independent. This module is the single boundary that resolves
their polymorphic ids and proves they belong to the festival in the URL.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError
from festaflow.models import (
    AudienceVote,
    Exhibit,
    ExperienceOpen,
    FavoriteMemory,
    LectureSession,
    Mission,
    Participation,
    SessionAttendance,
)
from festaflow.models.enums import ParticipationStatus

SOURCE_MODELS = {
    "mission": Mission,
    "lecture": LectureSession,
    "exhibit": Exhibit,
}


def resolve_source(
    db: Session,
    *,
    festival_id: int,
    source_type: str,
    source_id: int,
    active_only: bool,
):
    model = SOURCE_MODELS.get(source_type)
    if model is None:
        raise ApiError(422, "EXPERIENCE_SOURCE_INVALID", "지원하지 않는 Experience 유형입니다.")

    query = select(model).where(model.id == source_id, model.festival_id == festival_id)
    if active_only:
        query = query.where(model.archived_at.is_(None), model.is_active.is_(True))
    source = db.execute(query).scalar_one_or_none()
    if source is None:
        raise ApiError(
            404,
            "EXPERIENCE_NOT_FOUND",
            "이 행사에서 해당 Experience를 찾을 수 없습니다.",
        )
    return source


def source_title(source_type: str, source) -> str:
    if source_type == "exhibit":
        return source.title
    return source.title


@dataclass
class ExperienceInsight:
    source_type: str
    source_id: int
    title: str
    opens: int = 0
    unique_openers: int = 0
    discovery_contexts: dict[str, int] = field(default_factory=dict)
    verified_participants: int = 0
    completed_participants: int | None = None
    verification_kind: str = "none"
    favorites: int = 0
    favorite_reasons: dict[str, int] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)


def build_experience_insights(db: Session, festival_id: int) -> list[ExperienceInsight]:
    """Build descriptive consumer signals without inventing conversion or causality."""
    sources: dict[tuple[str, int], ExperienceInsight] = {}
    for source_type, model in SOURCE_MODELS.items():
        rows = db.execute(
            select(model).where(model.festival_id == festival_id).order_by(model.id)
        ).scalars()
        for source in rows:
            key = (source_type, source.id)
            sources[key] = ExperienceInsight(
                source_type=source_type,
                source_id=source.id,
                title=source_title(source_type, source),
                completed_participants=None if source_type == "exhibit" else 0,
                verification_kind={
                    "mission": "mission_completion",
                    "lecture": "lecture_checkin",
                    "exhibit": "audience_vote",
                }[source_type],
            )

    open_rows = list(
        db.execute(
            select(ExperienceOpen).where(ExperienceOpen.festival_id == festival_id)
        ).scalars()
    )
    openers: dict[tuple[str, int], set[int]] = defaultdict(set)
    contexts: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    for row in open_rows:
        key = (row.source_type, row.source_id)
        if key not in sources:
            continue
        sources[key].opens += 1
        openers[key].add(row.participant_id)
        contexts[key][row.source_context] += 1

    favorite_rows = list(
        db.execute(
            select(FavoriteMemory).where(FavoriteMemory.festival_id == festival_id)
        ).scalars()
    )
    reasons: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    for row in favorite_rows:
        key = (row.source_type, row.source_id)
        if key not in sources:
            continue
        sources[key].favorites += 1
        if row.reason:
            reasons[key][row.reason] += 1

    mission_people: dict[int, set[int]] = defaultdict(set)
    mission_rows = db.execute(
        select(Participation).where(
            Participation.festival_id == festival_id,
            Participation.status == ParticipationStatus.COMPLETED,
            Participation.mission_id.is_not(None),
        )
    ).scalars()
    for row in mission_rows:
        if row.mission_id is not None:
            mission_people[row.mission_id].add(row.participant_id)

    lecture_people: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    lecture_ids = [key[1] for key in sources if key[0] == "lecture"]
    if lecture_ids:
        attendance_rows = db.execute(
            select(SessionAttendance).where(SessionAttendance.session_id.in_(lecture_ids))
        ).scalars()
        for row in attendance_rows:
            lecture_people[row.session_id][row.participant_id].add(row.checkpoint_id)

    exhibit_people: dict[int, set[int]] = defaultdict(set)
    vote_rows = db.execute(
        select(AudienceVote).where(AudienceVote.festival_id == festival_id)
    ).scalars()
    for row in vote_rows:
        exhibit_people[row.exhibit_id].add(row.participant_id)

    lecture_required = {
        source.id: source.required_checkins
        for source in db.execute(
            select(LectureSession).where(LectureSession.festival_id == festival_id)
        ).scalars()
    }

    for key, insight in sources.items():
        insight.unique_openers = len(openers[key])
        insight.discovery_contexts = dict(sorted(contexts[key].items()))
        insight.favorite_reasons = dict(sorted(reasons[key].items()))
        if insight.source_type == "mission":
            insight.verified_participants = len(mission_people[insight.source_id])
            insight.completed_participants = insight.verified_participants
        elif insight.source_type == "lecture":
            people = lecture_people[insight.source_id]
            insight.verified_participants = len(people)
            required = lecture_required.get(insight.source_id, 1)
            insight.completed_participants = sum(
                len(checkpoints) >= required for checkpoints in people.values()
            )
        else:
            insight.verified_participants = len(exhibit_people[insight.source_id])

        if insight.unique_openers >= 5 and insight.verified_participants == 0:
            insight.observations.append(
                "상세를 본 참여자는 있었지만 확인된 참여 기록은 없습니다."
            )
        if insight.favorites > insight.verified_participants and insight.favorites >= 3:
            insight.observations.append(
                "Favorite Memory 선택 수가 확인된 참여자 수보다 많습니다."
            )

    return sorted(
        sources.values(),
        key=lambda item: (-item.unique_openers, -item.verified_participants, item.title),
    )
