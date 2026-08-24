"""전시 심사 집계 — 심사위원 점수와 관객 투표를 합산한다.

**최종 점수만 내려주지 않습니다.** 이 제품이 진단에서 점수 옆에 항상 계산 근거를
붙이는 것과 같은 이유입니다. 시상 결과에 이의가 들어왔을 때 "심사 70 · 관객 30
가중이고, 심사는 항목별로 이렇게 나왔다"를 그 자리에서 보여줄 수 없으면
그 점수는 근거가 아니라 선언입니다.

합산 방식:

    심사위원 = Σ(항목 평균 ÷ 항목 만점 × 항목 가중치) ÷ Σ가중치 × 100
    관객     = 득표수 ÷ 최다 득표수 × 100
    최종     = 심사위원 × judge_weight% + 관객 × (100 - judge_weight)%

관객 점수를 **최다 득표 기준으로 정규화**하는 이유는 표의 총량이 관객 수에 따라
달라지기 때문입니다. 절대 득표수를 그대로 쓰면 관객이 적은 해에는 관객 몫이
사실상 사라집니다.

**심사위원마다 본 작품 수가 다를 수 있습니다.** 두 명이 본 작품의 평균과 다섯 명이
본 작품의 평균은 같은 무게가 아니므로, 작품별 심사위원 수를 함께 내려 화면이
그 사실을 말할 수 있게 합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    AudienceVote,
    Exhibit,
    Festival,
    JudgeScore,
    Participant,
    VoteCriterion,
)
from festaflow.models.enums import IdentityMode


def get_exhibit(db: Session, festival_id: int, exhibit_id: int) -> Exhibit:
    e = db.execute(
        select(Exhibit).where(
            Exhibit.id == exhibit_id,
            Exhibit.festival_id == festival_id,
            Exhibit.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if e is None:
        raise not_found("작품")
    return e


def active_exhibits(db: Session, festival_id: int) -> list[Exhibit]:
    return list(
        db.execute(
            select(Exhibit)
            .where(
                Exhibit.festival_id == festival_id,
                Exhibit.archived_at.is_(None),
                Exhibit.is_active.is_(True),
            )
            .order_by(Exhibit.entry_no)
        ).scalars()
    )


def active_criteria(db: Session, festival_id: int) -> list[VoteCriterion]:
    return list(
        db.execute(
            select(VoteCriterion)
            .where(
                VoteCriterion.festival_id == festival_id,
                VoteCriterion.archived_at.is_(None),
                VoteCriterion.is_active.is_(True),
            )
            .order_by(VoteCriterion.sort_order, VoteCriterion.id)
        ).scalars()
    )


def next_entry_no(db: Session, festival_id: int) -> int:
    used = db.execute(
        select(func.coalesce(func.max(Exhibit.entry_no), 0)).where(
            Exhibit.festival_id == festival_id
        )
    ).scalar_one()
    return int(used) + 1


# ── 관객 투표 ───────────────────────────────────────────────────────────────


def assert_voting_open(festival: Festival) -> None:
    if not festival.voting_open:
        raise ApiError(
            409,
            "VOTING_CLOSED",
            "지금은 투표 기간이 아닙니다.",
        )


def votes_used(db: Session, festival_id: int, participant_id: int) -> int:
    return int(
        db.execute(
            select(func.count(AudienceVote.id)).where(
                AudienceVote.festival_id == festival_id,
                AudienceVote.participant_id == participant_id,
            )
        ).scalar_one()
    )


def voted_exhibit_ids(db: Session, festival_id: int, participant_id: int) -> set[int]:
    return set(
        db.execute(
            select(AudienceVote.exhibit_id).where(
                AudienceVote.festival_id == festival_id,
                AudienceVote.participant_id == participant_id,
            )
        ).scalars()
    )


def assert_can_vote(
    db: Session, festival: Festival, participant: Participant
) -> None:
    """표를 더 쓸 수 있는가.

    **익명 축제에서는 이 검사가 아무것도 막지 못합니다.** 참여 코드를 새로 받으면
    표가 초기화되기 때문입니다. 그래서 그 경우를 조용히 통과시키지 않고 거절합니다 —
    막히는 줄 알고 켜 두면 그 오해 위에 시상이 세워집니다.
    """
    if festival.identity_mode != IdentityMode.STUDENT_ID:
        raise ApiError(
            409,
            "VOTING_REQUIRES_IDENTITY",
            (
                "이 축제는 익명 참여라 1인 1표를 보장할 수 없습니다. "
                "참여자 식별을 '학번'으로 바꾼 뒤 투표를 여세요."
            ),
            {"identity_mode": festival.identity_mode.value},
        )

    used = votes_used(db, festival.id, participant.id)
    limit = festival.audience_votes_per_participant
    if used >= limit:
        raise ApiError(
            409,
            "VOTE_LIMIT_REACHED",
            f"표를 모두 사용했습니다({limit}표). 준 표를 취소하면 다시 줄 수 있습니다.",
            {"used": used, "limit": limit},
        )


# ── 집계 ────────────────────────────────────────────────────────────────────


@dataclass
class CriterionResult:
    criterion_id: int
    label: str
    max_score: int
    weight: int
    #: 심사위원 점수 평균. 아무도 안 매겼으면 None — 0 과 다르다.
    average: float | None
    judge_count: int


@dataclass
class ExhibitResult:
    exhibit: Exhibit
    criteria: list[CriterionResult] = field(default_factory=list)
    #: 이 작품을 한 항목이라도 심사한 사람 수.
    judge_count: int = 0
    votes: int = 0
    #: 0~100 로 정규화한 심사위원 점수. 심사 기록이 없으면 None.
    judge_score: float | None = None
    #: 0~100 로 정규화한 관객 점수. 표가 하나도 없으면 None.
    audience_score: float | None = None
    final_score: float | None = None


def results(db: Session, festival: Festival) -> list[ExhibitResult]:
    """작품별 집계. 최종 점수 내림차순으로 돌려준다."""
    exhibits = active_exhibits(db, festival.id)
    criteria = active_criteria(db, festival.id)
    if not exhibits:
        return []

    ids = [e.id for e in exhibits]

    # 항목별 평균과 심사위원 수를 한 번에 긁는다.
    score_rows = db.execute(
        select(
            JudgeScore.exhibit_id,
            JudgeScore.criterion_id,
            func.avg(JudgeScore.score),
            func.count(func.distinct(JudgeScore.staff_id)),
        )
        .where(JudgeScore.exhibit_id.in_(ids))
        .group_by(JudgeScore.exhibit_id, JudgeScore.criterion_id)
    ).all()
    by_pair = {(e, c): (float(avg), int(n)) for e, c, avg, n in score_rows}

    judges_per_exhibit = dict(
        db.execute(
            select(JudgeScore.exhibit_id, func.count(func.distinct(JudgeScore.staff_id)))
            .where(JudgeScore.exhibit_id.in_(ids))
            .group_by(JudgeScore.exhibit_id)
        ).all()
    )

    vote_rows = dict(
        db.execute(
            select(AudienceVote.exhibit_id, func.count(AudienceVote.id))
            .where(AudienceVote.exhibit_id.in_(ids))
            .group_by(AudienceVote.exhibit_id)
        ).all()
    )
    top_votes = max(vote_rows.values(), default=0)

    out: list[ExhibitResult] = []
    for e in exhibits:
        rows: list[CriterionResult] = []
        weighted, total_weight = 0.0, 0
        for c in criteria:
            avg, n = by_pair.get((e.id, c.id), (None, 0))
            rows.append(
                CriterionResult(
                    criterion_id=c.id,
                    label=c.label,
                    max_score=c.max_score,
                    weight=c.weight,
                    average=avg,
                    judge_count=n,
                )
            )
            # 아무도 안 매긴 항목은 **분모에서도 뺀다.** 0 으로 치면 심사를
            # 덜 받은 작품이 점수를 잃는다 — 작품의 문제가 아니라 운영의 문제다.
            if avg is not None:
                weighted += (avg / c.max_score) * c.weight
                total_weight += c.weight

        judge_score = (weighted / total_weight * 100) if total_weight else None
        votes = int(vote_rows.get(e.id, 0))
        audience_score = (votes / top_votes * 100) if top_votes else None

        jw = festival.judge_weight_percent / 100
        if judge_score is None and audience_score is None:
            final = None
        elif judge_score is None:
            final = audience_score
        elif audience_score is None:
            final = judge_score
        else:
            final = judge_score * jw + audience_score * (1 - jw)

        out.append(
            ExhibitResult(
                exhibit=e,
                criteria=rows,
                judge_count=int(judges_per_exhibit.get(e.id, 0)),
                votes=votes,
                judge_score=judge_score,
                audience_score=audience_score,
                final_score=final,
            )
        )

    out.sort(key=lambda r: (r.final_score is None, -(r.final_score or 0), r.exhibit.entry_no))
    return out


def integrity_warnings(results_: list[ExhibitResult], criteria_count: int) -> list[dict]:
    """집계를 믿어도 되는지 흔드는 사실들. 시상 전에 알아야 한다."""
    warnings: list[dict] = []
    if not results_:
        return warnings

    if criteria_count == 0:
        warnings.append(
            {
                "code": "NO_CRITERIA",
                "message": "심사 항목이 없습니다. 심사위원이 점수를 매길 수 없습니다.",
            }
        )

    counts = [r.judge_count for r in results_]
    if counts and max(counts) != min(counts):
        warnings.append(
            {
                "code": "UNEVEN_JUDGING",
                "message": (
                    f"작품마다 심사위원 수가 다릅니다({min(counts)}~{max(counts)}명). "
                    "적게 심사된 작품의 평균은 같은 무게로 비교하기 어렵습니다."
                ),
            }
        )

    unjudged = [r for r in results_ if r.judge_count == 0]
    if unjudged:
        warnings.append(
            {
                "code": "UNJUDGED_EXHIBITS",
                "message": f"아직 아무도 심사하지 않은 작품이 {len(unjudged)}점 있습니다.",
            }
        )

    if all(r.votes == 0 for r in results_):
        warnings.append(
            {
                "code": "NO_AUDIENCE_VOTES",
                "message": "관객 표가 한 장도 없습니다. 최종 점수가 심사위원 점수와 같습니다.",
            }
        )

    return warnings
