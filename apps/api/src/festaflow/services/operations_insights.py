"""운영 인사이트 — 부스 참여 편중 판정. 계약 §5, 기획서 7.1.

**이 지표는 혼잡도가 아닙니다.** GPS·카메라·센서로 잰 인원수도, 물리적 밀집도도
아닙니다. 부스에서 검증된 QR/미션 완료 건수를 현장 참여량의 *proxy* 로 쓰는
**참여 편중 위험** 지표입니다. QR 참여자는 방문객의 일부이고 적극적 참여자에
편향된 표본입니다.

이 제한을 문구로만 밝히고 화면에서는 혼잡도처럼 그리면, 그 문구는 면피가 됩니다.
그래서 상태 이름부터 `LOW/CAUTION/HIGH` 를 "여유/주의/집중" 으로 부르고
"한산/혼잡" 이라는 말을 쓰지 않습니다.

**표본이 적으면 판정하지 않습니다.** 최근 30분 전체가 10건 미만이면 모든 부스가
`INSUFFICIENT_DATA` 입니다. 3건 중 2건이 한 부스에서 나왔다고 "67% 집중" 이라
말하면 그 숫자가 근거처럼 보입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.models import Booth, Participation
from festaflow.models.enums import BoothLoadStatus, ParticipationStatus

#: 편중 판정 임계값 — 기획서 7.1 의 표 그대로.
CAUTION_SHARE = 0.25
HIGH_SHARE = 0.40

#: 최근 창 길이(분). 10·30·60 을 함께 보여주는 이유는 30분 하나만으로는
#: "방금 몰린 것" 과 "계속 몰리는 것" 이 구분되지 않기 때문이다.
WINDOWS_MINUTES = (10, 30, 60)
PRIMARY_WINDOW = 30


@dataclass
class BoothLoad:
    booth: Booth
    total_completions: int
    unique_participants: int
    #: 분 → 건수.
    recent: dict[int, int]
    share_last_30m: float
    status: BoothLoadStatus
    status_reason: str
    last_completed_at: datetime | None


@dataclass
class Insights:
    generated_at: datetime
    total_participants: int
    total_completions: int
    completions_last_30m: int
    booths: list[BoothLoad] = field(default_factory=list)

    @property
    def high_concentration_booths(self) -> int:
        return sum(1 for b in self.booths if b.status == BoothLoadStatus.HIGH)

    @property
    def enough_data(self) -> bool:
        return self.completions_last_30m >= settings.insights_min_sample


def _completed(festival_id: int):
    return (
        Participation.festival_id == festival_id,
        Participation.status == ParticipationStatus.COMPLETED,
        Participation.completed_at.is_not(None),
    )


def _classify(share: float, *, enough: bool, count: int, total: int):
    if not enough:
        return (
            BoothLoadStatus.INSUFFICIENT_DATA,
            f"최근 {PRIMARY_WINDOW}분 축제 전체 완료가 {total}건이라 판정하지 않습니다.",
        )

    pct = round(share * 100)
    reason = (
        f"최근 {PRIMARY_WINDOW}분 축제 전체 {total}건 중 {count}건({pct}%)이 "
        f"이 부스에서 발생"
    )
    if share >= HIGH_SHARE:
        return BoothLoadStatus.HIGH, reason
    if share >= CAUTION_SHARE:
        return BoothLoadStatus.CAUTION, reason
    return BoothLoadStatus.LOW, reason


def build(db: Session, festival_id: int, *, now: datetime | None = None) -> Insights:
    at = now or datetime.now(UTC)
    where = _completed(festival_id)

    total_completions = int(
        db.execute(select(func.count(Participation.id)).where(*where)).scalar_one()
    )
    total_participants = int(
        db.execute(
            select(func.count(func.distinct(Participation.participant_id))).where(*where)
        ).scalar_one()
    )

    since30 = at - timedelta(minutes=PRIMARY_WINDOW)
    completions_last_30m = int(
        db.execute(
            select(func.count(Participation.id)).where(
                *where, Participation.completed_at >= since30
            )
        ).scalar_one()
    )
    enough = completions_last_30m >= settings.insights_min_sample

    booths = list(
        db.execute(
            select(Booth)
            .where(Booth.festival_id == festival_id, Booth.archived_at.is_(None))
            .order_by(Booth.id)
        ).scalars()
    )

    # 부스별 누적 · 고유 참여자 · 마지막 완료를 한 번에.
    rows = dict(
        (bid, (int(n), int(u), last))
        for bid, n, u, last in db.execute(
            select(
                Participation.booth_id,
                func.count(Participation.id),
                func.count(func.distinct(Participation.participant_id)),
                func.max(Participation.completed_at),
            )
            .where(*where, Participation.booth_id.is_not(None))
            .group_by(Participation.booth_id)
        ).all()
    )

    recent: dict[int, dict[int, int]] = {b.id: {} for b in booths}
    for minutes in WINDOWS_MINUTES:
        since = at - timedelta(minutes=minutes)
        for bid, n in db.execute(
            select(Participation.booth_id, func.count(Participation.id))
            .where(*where, Participation.completed_at >= since, Participation.booth_id.is_not(None))
            .group_by(Participation.booth_id)
        ).all():
            if bid in recent:
                recent[bid][minutes] = int(n)

    loads: list[BoothLoad] = []
    for b in booths:
        total, unique, last = rows.get(b.id, (0, 0, None))
        counts = {m: recent[b.id].get(m, 0) for m in WINDOWS_MINUTES}
        c30 = counts[PRIMARY_WINDOW]
        share = (c30 / completions_last_30m) if completions_last_30m else 0.0
        status, reason = _classify(
            share, enough=enough, count=c30, total=completions_last_30m
        )
        loads.append(
            BoothLoad(
                booth=b,
                total_completions=total,
                unique_participants=unique,
                recent=counts,
                share_last_30m=round(share, 4),
                status=status,
                status_reason=reason,
                last_completed_at=last,
            )
        )

    return Insights(
        generated_at=at,
        total_participants=total_participants,
        total_completions=total_completions,
        completions_last_30m=completions_last_30m,
        booths=loads,
    )
