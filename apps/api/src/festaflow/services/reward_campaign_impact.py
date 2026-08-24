"""운영 개입 효과 분석 — 캠페인 전후 참여 변화. 계약 §6, 기획서 7.2.

**보상의 인과 효과가 아닙니다.** 캠페인을 켠 시점은 대개 사람이 몰리기 시작한
시점이고, 같은 시간에 공연이 끝나거나 비가 그치거나 점심시간이 지납니다. 전후
차이를 "보상이 만든 효과"라고 부르면 그 숫자로 다음 축제 예산이 정해집니다.

그래서 이 모듈은 `share_change_pp` 와 `completion_change_rate` 를 계산할 뿐,
어디에서도 "효과" 나 "덕분" 이라는 말을 쓰지 않습니다.

표본이 얇으면 아예 판정하지 않습니다. before+after 합계 20건 미만이면
`INSUFFICIENT_DATA` 입니다 — 2건에서 6건이 되면 "200% 증가"가 되는데, 그건
증가가 아니라 잡음입니다.

**다른 축제 참여는 집계하지 않습니다.** 전체 완료 수가 분모라, 한 건이라도
새면 비율이 통째로 틀어집니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.models import Booth, Participation, RewardCampaign
from festaflow.models.enums import ParticipationStatus

#: 전후 비교 창의 기본 길이(분).
DEFAULT_WINDOW_MINUTES = 30

#: 판정에 필요한 before+after 최소 합계.
MIN_SAMPLE = 20

#: 최다 참여 부스로 볼 비율. 편중이 실제로 풀렸는지 함께 본다 —
#: 대상 부스만 오르고 몰린 부스도 그대로면 사람이 더 온 것이지 분산된 게 아니다.
TOP_BOOTH_SHARE = 0.40

SUFFICIENT = "SUFFICIENT"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

DISCLAIMER = "캠페인 전후 참여 변화이며 보상의 인과 효과가 아닙니다."


@dataclass
class Window:
    frm: datetime
    to: datetime
    target_completions: int
    festival_completions: int

    @property
    def share(self) -> float:
        if self.festival_completions == 0:
            return 0.0
        return round(self.target_completions / self.festival_completions, 4)


@dataclass
class TopBooth:
    booth_id: int
    name: str
    share_before: float
    share_after: float


@dataclass
class Impact:
    campaign_id: int
    window_minutes: int
    before: Window
    after: Window
    top_booth_before: TopBooth | None
    data_status: str
    #: after 구간이 아직 안 지났다. 지금 숫자로 결론을 내면 안 된다.
    in_progress: bool

    @property
    def share_change_pp(self) -> float:
        """%p 변화. 비율의 차이지 비율의 비율이 아니다."""
        return round((self.after.share - self.before.share) * 100, 1)

    @property
    def completion_change_rate(self) -> float | None:
        """before 대비 배수. before 가 0 이면 **None** 이다.

        0 을 분모로 두고 "무한 증가"나 "100%"를 만들어 내면 그 숫자가 화면에
        나가고, 아무도 그게 0 에서 시작했다는 걸 모른다.
        """
        if self.before.target_completions == 0:
            return None
        return round(
            (self.after.target_completions - self.before.target_completions)
            / self.before.target_completions,
            3,
        )


def _count(
    db: Session, festival_id: int, frm: datetime, to: datetime, booth_id: int | None = None
) -> int:
    where = [
        Participation.festival_id == festival_id,
        Participation.status == ParticipationStatus.COMPLETED,
        Participation.completed_at >= frm,
        Participation.completed_at < to,
    ]
    if booth_id is not None:
        where.append(Participation.booth_id == booth_id)
    return int(db.execute(select(func.count(Participation.id)).where(*where)).scalar_one())


def _top_booth(
    db: Session,
    festival_id: int,
    *,
    exclude_booth_id: int,
    before: Window,
    after: Window,
) -> TopBooth | None:
    """before 구간에서 대상 부스를 빼고 40% 이상 몰린 부스.

    대상 부스가 오른 것만으로는 편중이 풀렸는지 알 수 없다. 몰려 있던 쪽이
    그대로면 전체 참여가 늘어난 것이지 분산된 것이 아니다.
    """
    if before.festival_completions == 0:
        return None

    rows = db.execute(
        select(Participation.booth_id, func.count(Participation.id))
        .where(
            Participation.festival_id == festival_id,
            Participation.status == ParticipationStatus.COMPLETED,
            Participation.completed_at >= before.frm,
            Participation.completed_at < before.to,
            Participation.booth_id.is_not(None),
            Participation.booth_id != exclude_booth_id,
        )
        .group_by(Participation.booth_id)
        .order_by(func.count(Participation.id).desc())
        .limit(1)
    ).first()
    if rows is None:
        return None

    booth_id, count = int(rows[0]), int(rows[1])
    share_before = count / before.festival_completions
    if share_before < TOP_BOOTH_SHARE:
        return None

    booth = db.get(Booth, booth_id)
    after_count = _count(db, festival_id, after.frm, after.to, booth_id)
    share_after = (
        after_count / after.festival_completions if after.festival_completions else 0.0
    )
    return TopBooth(
        booth_id=booth_id,
        name=booth.name if booth else f"부스 {booth_id}",
        share_before=round(share_before, 4),
        share_after=round(share_after, 4),
    )


def build(
    db: Session,
    campaign: RewardCampaign,
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    now: datetime | None = None,
) -> Impact:
    """캠페인 **시작 시각** 기준 전후 비교.

    종료 시각이 아니라 시작 시각을 기준으로 잡습니다. 캠페인이 켜진 순간부터
    참여가 달라지는지를 보는 것이고, 종료 기준으로 보면 캠페인 기간 전체가
    before 에 섞여 들어갑니다.
    """
    at = now or datetime.now(UTC)
    span = timedelta(minutes=window_minutes)
    start = campaign.starts_at

    before = Window(
        frm=start - span,
        to=start,
        target_completions=_count(
            db, campaign.festival_id, start - span, start, campaign.booth_id
        ),
        festival_completions=_count(db, campaign.festival_id, start - span, start),
    )
    after = Window(
        frm=start,
        to=start + span,
        target_completions=_count(
            db, campaign.festival_id, start, start + span, campaign.booth_id
        ),
        festival_completions=_count(db, campaign.festival_id, start, start + span),
    )

    total = before.target_completions + after.target_completions
    return Impact(
        campaign_id=campaign.id,
        window_minutes=window_minutes,
        before=before,
        after=after,
        top_booth_before=_top_booth(
            db,
            campaign.festival_id,
            exclude_booth_id=campaign.booth_id,
            before=before,
            after=after,
        ),
        data_status=SUFFICIENT if total >= MIN_SAMPLE else INSUFFICIENT_DATA,
        in_progress=at < after.to,
    )
