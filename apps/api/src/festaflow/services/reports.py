"""축제 사후 성과 리포트. 기획서 5.9, 계약 §15.

**이 리포트가 하지 않는 일이 하는 일만큼 중요합니다.**

- 미션 성공률을 만들지 않습니다. 시도자 분모를 모르기 때문입니다.
- 방문객 대비 참여율을 마음대로 만들지 않습니다. 실측(`visitor_counts`)이
  들어와 있을 때만 계산하고, 없으면 `expected_visitors` 대비 **참여 규모**로만
  부르며 그게 방문률이 아니라는 문구를 함께 답니다.
- 측정하지 않은 지표에 달성률을 붙이지 않습니다.

개선안은 설명 가능한 규칙으로만 만듭니다. AI 를 쓰지 않으므로 왜 이 문장이
나왔는지를 언제나 그대로 되짚을 수 있습니다.

부스별 집계는 **`participations.booth_id` 스냅샷**을 씁니다. 운영 중 미션을
다른 부스로 옮겨도 과거 집계가 따라 움직이지 않습니다 — 원문은 "현재 미션의
booth_id" 로 묶어서 미션 재배치 한 번에 리포트가 통째로 뒤바뀌었습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.models import (
    Booth,
    Festival,
    KpiTarget,
    Mission,
    Participation,
    RecommendationFeedback,
    VisitorCount,
)
from festaflow.models.enums import ExperienceType, ParticipationStatus, VisitorSource

#: 리포트의 시간축은 **KST 고정**입니다. 서버가 UTC 로 돌아도 "14시대에 몰렸다"는
#: 문장은 현장 사람의 시계로 읽혀야 합니다. 브라우저 시간대를 쓰면 서울에서 만든
#: 리포트를 다른 시간대에서 열었을 때 피크 시각이 달라집니다.
KST = timezone(timedelta(hours=9), "KST")

#: 실측 방문객 출처 우선순위. 낮을수록 먼저 쓴다.
SOURCE_PRIORITY = {
    VisitorSource.BEACON: 1,
    VisitorSource.MANUAL_COUNTER: 2,
    VisitorSource.PARTNER: 3,
    VisitorSource.ESTIMATE: 4,
}

SOURCE_LABEL = {
    VisitorSource.BEACON: "출입구 센서",
    VisitorSource.MANUAL_COUNTER: "입구 계수기",
    VisitorSource.PARTNER: "지자체·조직위 집계",
    VisitorSource.ESTIMATE: "주최측 추산",
    VisitorSource.KTO_BIGDATA: "한국관광공사 빅데이터",
}

#: 추산 출처에만 붙는 꼬리표. 센서 수치와 추산을 같은 굵기로 보여주면
#: 리포트를 읽는 사람이 둘을 구별할 방법이 없다.
ESTIMATE_NOTE = "주최측 추산 기준"

SCALE_DISCLAIMER = (
    "FestaFlow 미션 서비스의 참여 규모입니다. "
    "실제 축제 방문률이나 전체 방문객 대비 참여율이 아닙니다."
)

#: 개선안 임계값.
CONCENTRATED_SHARE = 0.35


# ── 집계 결과 ───────────────────────────────────────────────────────────────


@dataclass
class Summary:
    unique_participants: int
    total_completions: int
    missions_with_completion: int
    missions_total: int

    @property
    def avg_completions_per_participant(self) -> float:
        if self.unique_participants == 0:
            return 0.0
        return round(self.total_completions / self.unique_participants, 2)

    @property
    def mission_ratio(self) -> float:
        if self.missions_total == 0:
            return 0.0
        return round(self.missions_with_completion / self.missions_total, 4)


@dataclass
class BoothPerformance:
    booth_id: int
    name: str
    completions: int
    unique_participants: int
    share: float
    rank: int
    peak_hour_kst: datetime | None
    peak_completions: int


@dataclass
class MissionPerformance:
    mission_id: int
    title: str
    booth_name: str | None
    completions: int
    unique_participants: int
    share: float


@dataclass
class VisitorBasis:
    """실측 방문객으로 계산한 참여율."""

    visitors: int
    source: VisitorSource
    source_label: str
    #: 추산 출처에만 붙는다.
    caveat: str | None
    participation_rate: float
    #: 같은 날짜의 다른 출처. 숨기지 않고 병기한다 —
    #: 입구 계수기와 지자체 집계가 다른 것은 정상이다.
    others: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class KpiRow:
    metric_key: str
    label: str
    target: float
    actual: float | None
    achievement: float | None
    measurable: bool
    unit: str
    note: str | None


@dataclass
class Improvement:
    rule: str
    message: str


@dataclass
class Report:
    festival: Festival
    summary: Summary
    timeline: list[tuple[datetime, int]]
    booths: list[BoothPerformance]
    missions: list[MissionPerformance]
    unassigned_completions: int
    visitor_basis: VisitorBasis | None
    kpi: list[KpiRow]
    recommendation_hits: tuple[int, int] | None
    improvements: list[Improvement]

    @property
    def participation_scale(self) -> float:
        """예상 방문객 대비 참여 규모. **방문률이 아니다.**"""
        if not self.festival.expected_visitors:
            return 0.0
        return round(
            self.summary.unique_participants / self.festival.expected_visitors, 4
        )


# ── 집계 ────────────────────────────────────────────────────────────────────


def _completed(festival_id: int):
    return (
        Participation.festival_id == festival_id,
        Participation.status == ParticipationStatus.COMPLETED,
        Participation.completed_at.is_not(None),
    )


def _summary(db: Session, festival_id: int) -> Summary:
    where = _completed(festival_id)
    total = int(db.execute(select(func.count(Participation.id)).where(*where)).scalar_one())
    unique = int(
        db.execute(
            select(func.count(func.distinct(Participation.participant_id))).where(*where)
        ).scalar_one()
    )
    with_completion = int(
        db.execute(
            select(func.count(func.distinct(Participation.mission_id))).where(
                *where, Participation.mission_id.is_not(None)
            )
        ).scalar_one()
    )
    missions_total = int(
        db.execute(
            select(func.count(Mission.id)).where(
                Mission.festival_id == festival_id, Mission.archived_at.is_(None)
            )
        ).scalar_one()
    )
    return Summary(
        unique_participants=unique,
        total_completions=total,
        missions_with_completion=with_completion,
        missions_total=missions_total,
    )


def _timeline(db: Session, festival_id: int) -> list[tuple[datetime, int]]:
    """완료 시각을 **KST 1시간 버킷**으로 묶는다.

    시간대 변환을 DB 에 맡깁니다. 파이썬에서 UTC 시각을 잘라 9시간을 더하면
    자정 근처 버킷이 하루 밀리는 실수가 나기 쉽습니다.
    """
    bucket = func.date_trunc(
        "hour", func.timezone("Asia/Seoul", Participation.completed_at)
    ).label("bucket")
    rows = db.execute(
        select(bucket, func.count(Participation.id))
        .where(*_completed(festival_id))
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    return [(b.replace(tzinfo=KST), int(n)) for b, n in rows]


def _peak_hours(db: Session, festival_id: int) -> dict[int, tuple[datetime, int]]:
    """부스별 최다 완료 시간대."""
    bucket = func.date_trunc(
        "hour", func.timezone("Asia/Seoul", Participation.completed_at)
    ).label("bucket")
    rows = db.execute(
        select(Participation.booth_id, bucket, func.count(Participation.id))
        .where(*_completed(festival_id), Participation.booth_id.is_not(None))
        .group_by(Participation.booth_id, bucket)
    ).all()

    best: dict[int, tuple[datetime, int]] = {}
    for booth_id, hour, count in rows:
        n = int(count)
        current = best.get(int(booth_id))
        # 동률이면 **이른 시각**을 남긴다. 운영 인력 배치는 앞쪽 시간대를 기준으로
        # 잡아야 뒤쪽까지 덮인다.
        if current is None or n > current[1]:
            best[int(booth_id)] = (hour.replace(tzinfo=KST), n)
    return best


def _booths(db: Session, festival_id: int, total: int) -> tuple[list[BoothPerformance], int]:
    rows = db.execute(
        select(
            Participation.booth_id,
            func.count(Participation.id),
            func.count(func.distinct(Participation.participant_id)),
        )
        .where(*_completed(festival_id), Participation.booth_id.is_not(None))
        .group_by(Participation.booth_id)
        .order_by(func.count(Participation.id).desc())
    ).all()

    unassigned = int(
        db.execute(
            select(func.count(Participation.id)).where(
                *_completed(festival_id), Participation.booth_id.is_(None)
            )
        ).scalar_one()
    )

    peaks = _peak_hours(db, festival_id)
    out: list[BoothPerformance] = []
    prev_count: int | None = None
    prev_rank = 0
    for index, (booth_id, count, unique) in enumerate(rows, start=1):
        booth_id, count, unique = int(booth_id), int(count), int(unique)
        # 동률은 같은 순위. 1등이 둘이면 다음은 3등이다.
        rank = prev_rank if count == prev_count else index
        prev_count, prev_rank = count, rank
        booth = db.get(Booth, booth_id)
        peak = peaks.get(booth_id)
        out.append(
            BoothPerformance(
                booth_id=booth_id,
                name=booth.name if booth else f"부스 {booth_id}",
                completions=count,
                unique_participants=unique,
                share=round(count / total, 4) if total else 0.0,
                rank=rank,
                peak_hour_kst=peak[0] if peak else None,
                peak_completions=peak[1] if peak else 0,
            )
        )
    return out, unassigned


def _missions(db: Session, festival_id: int, total: int) -> list[MissionPerformance]:
    rows = db.execute(
        select(
            Participation.mission_id,
            func.count(Participation.id),
            func.count(func.distinct(Participation.participant_id)),
        )
        .where(*_completed(festival_id), Participation.mission_id.is_not(None))
        .group_by(Participation.mission_id)
        .order_by(func.count(Participation.id).desc())
    ).all()

    out: list[MissionPerformance] = []
    for mission_id, count, unique in rows:
        mission = db.get(Mission, int(mission_id))
        booth = db.get(Booth, mission.booth_id) if mission and mission.booth_id else None
        out.append(
            MissionPerformance(
                mission_id=int(mission_id),
                title=mission.title if mission else f"미션 {mission_id}",
                booth_name=booth.name if booth else None,
                completions=int(count),
                unique_participants=int(unique),
                share=round(int(count) / total, 4) if total else 0.0,
            )
        )
    return out


def visitor_basis(db: Session, festival_id: int, unique: int) -> VisitorBasis | None:
    """실측 방문객이 있으면 근거 있는 참여율을 만든다. 없으면 **만들지 않는다.**"""
    rows = list(
        db.execute(
            select(VisitorCount).where(VisitorCount.festival_id == festival_id)
        ).scalars()
    )
    if not rows:
        return None

    # 날짜별로 우선순위가 높은 출처 하나씩 골라 합산한다.
    by_date: dict[object, list[VisitorCount]] = {}
    for row in rows:
        by_date.setdefault(row.count_date, []).append(row)

    chosen: list[VisitorCount] = []
    others: list[tuple[str, int]] = []
    for same_day in by_date.values():
        ranked = sorted(same_day, key=lambda v: SOURCE_PRIORITY.get(v.source, 99))
        chosen.append(ranked[0])
        others.extend((SOURCE_LABEL.get(v.source, v.source.value), v.visitors) for v in ranked[1:])

    visitors = sum(v.visitors for v in chosen)
    if visitors == 0:
        return None

    # 대표 출처는 고른 것들 중 가장 신뢰도가 낮은 쪽이다. 하루는 센서, 하루는
    # 추산으로 채웠다면 합계 전체를 센서 수치라고 부를 수 없다.
    worst = max(chosen, key=lambda v: SOURCE_PRIORITY.get(v.source, 99)).source
    return VisitorBasis(
        visitors=visitors,
        source=worst,
        source_label=SOURCE_LABEL.get(worst, worst.value),
        caveat=ESTIMATE_NOTE if worst == VisitorSource.ESTIMATE else None,
        participation_rate=round(unique / visitors, 4),
        others=others,
    )


def _kpi(
    db: Session, festival: Festival, summary: Summary, basis: VisitorBasis | None
) -> list[KpiRow]:
    targets = list(
        db.execute(
            select(KpiTarget).where(KpiTarget.festival_id == festival.id).order_by(KpiTarget.id)
        ).scalars()
    )
    if not targets:
        # 목표를 세우지 않았으면 블록 자체를 생략한다. 빈 표를 그리면
        # "목표가 0" 처럼 읽힌다.
        return []

    actuals: dict[str, float | None] = {
        "qr_participants": float(summary.unique_participants),
        "total_completions": float(summary.total_completions),
        "completions_per_participant": summary.avg_completions_per_participant,
        "satisfaction": satisfaction_average(db, festival.id),
        # 실측이 들어와야 비로소 값이 생긴다.
        "expected_visitors": float(basis.visitors) if basis else None,
    }

    out: list[KpiRow] = []
    for t in targets:
        target = float(t.target_value)
        actual = actuals.get(t.metric_key)
        measurable = t.is_measurable
        note = None

        if t.metric_key == "expected_visitors":
            # 실측이 들어오면 그때부터 달성률을 갖는다. 그 전까지는 참고값이다.
            measurable = basis is not None
            note = (
                f"{basis.source_label} 실측 {basis.visitors:,}명 기준입니다."
                if basis
                else "FestaFlow는 방문객 수를 측정하지 않습니다. 참고값입니다."
            )
        elif t.metric_key == "satisfaction":
            # 응답이 없으면 달성률을 만들지 않는다. 0 으로 치면 "만족도 0점" 이
            # 되어 설문을 안 돌린 축제가 최악의 축제로 보인다.
            measurable = actual is not None
            note = (
                "설문 체험 응답의 평점 문항 평균입니다(5점 환산). "
                "응답자가 QR 참여자에 한정되므로 전체 방문객의 의견이 아닙니다."
                if actual is not None
                else "설문 응답이 없어 실제값을 집계하지 않습니다."
            )
        elif t.metric_key.startswith("custom:"):
            note = "사용자 정의 지표입니다. 실제값은 직접 입력해야 합니다."
            measurable = False

        achievement = (
            round(actual / target, 4)
            if measurable and actual is not None and target > 0
            else None
        )
        out.append(
            KpiRow(
                metric_key=t.metric_key,
                label=t.label,
                target=target,
                actual=actual if measurable else None,
                achievement=achievement,
                measurable=measurable,
                unit=t.unit,
                note=note,
            )
        )
    return out


def satisfaction_average(db: Session, festival_id: int) -> float | None:
    """설문의 평점 문항 평균. 응답이 없으면 **None**.

    **척도가 다른 문항을 그대로 섞지 않습니다.** 5점 만점과 7점 만점을 함께
    평균 내면 7점 문항이 저절로 높은 값이 되어 결과가 그쪽으로 끌려갑니다.
    각 응답을 자기 척도로 나눠 0~1 로 만든 뒤 5점 만점으로 환산합니다.

    선택 문항은 세지 않습니다 — "SNS/현수막/지인" 은 순서가 없는 값이라
    평균이 아무 뜻도 없습니다.
    """
    rows = db.execute(
        select(Participation.response, Mission.experience_config)
        .join(Mission, Mission.id == Participation.mission_id)
        .where(
            *_completed(festival_id),
            Mission.experience_type == ExperienceType.SURVEY,
            Participation.response.is_not(None),
        )
    ).all()

    normalized: list[float] = []
    for response, config in rows:
        answers = (response or {}).get("answers") or []
        questions = (config or {}).get("questions") or []
        for q, a in zip(questions, answers, strict=False):
            if q.get("type") != "rating" or not isinstance(a, int):
                continue
            scale = q.get("scale", 5)
            if scale < 2:
                continue
            # 1~scale 을 0~1 로. 최저점이 0 이 되도록 1 을 뺀다.
            normalized.append((a - 1) / (scale - 1))

    if not normalized:
        return None
    # 5점 만점으로 환산해 돌려준다. 사람이 읽는 단위가 그것이다.
    return round(1 + (sum(normalized) / len(normalized)) * 4, 2)


def _recommendation_hits(db: Session, festival_id: int) -> tuple[int, int] | None:
    """추천 적중률. 제품이 자기 정확도를 스스로 보고하는 항목이다."""
    rows = db.execute(
        select(RecommendationFeedback.verdict, func.count(RecommendationFeedback.id))
        .where(RecommendationFeedback.festival_id == festival_id)
        .group_by(RecommendationFeedback.verdict)
    ).all()
    if not rows:
        return None
    hits = sum(int(n) for verdict, n in rows if verdict)
    total = sum(int(n) for _, n in rows)
    return hits, total


# ── 개선안 ──────────────────────────────────────────────────────────────────


def _improvements(
    report_summary: Summary,
    timeline: list[tuple[datetime, int]],
    booths: list[BoothPerformance],
    impacts: list[tuple[str, float, bool]],
) -> list[Improvement]:
    """설명 가능한 규칙만. AI 를 쓰지 않는다."""
    out: list[Improvement] = []

    if report_summary.total_completions == 0:
        out.append(
            Improvement(
                rule="NO_DATA",
                message=(
                    "참여 기록이 한 건도 없습니다. 참여 코드 안내물이 실제로 붙어 있었는지, "
                    "부스에서 지급 화면에 로그인했는지를 먼저 확인하세요."
                ),
            )
        )
        return out

    if timeline:
        peak_hour, peak_count = max(timeline, key=lambda x: x[1])
        out.append(
            Improvement(
                rule="PEAK_HOUR",
                message=(
                    f"{peak_hour.hour}시대에 완료가 가장 많았습니다({peak_count}건). "
                    "다음 행사에서 그 시간대 운영인력과 대기 동선 강화를 검토하세요."
                ),
            )
        )

    for b in booths:
        if b.share >= CONCENTRATED_SHARE:
            out.append(
                Improvement(
                    rule="CONCENTRATED_BOOTH",
                    message=(
                        f"{b.name} 한 곳에서 전체 완료의 "
                        f"{round(b.share * 100)}%가 나왔습니다. "
                        "공간 확대나 인접 부스로의 분산 배치를 검토하세요."
                    ),
                )
            )
            break

    if len(booths) >= 2:
        average = report_summary.total_completions / len(booths)
        lowest = booths[-1]
        if lowest.completions < average:
            out.append(
                Improvement(
                    rule="LOW_BOOTH",
                    message=(
                        f"{lowest.name}의 완료가 {lowest.completions}건으로 "
                        f"부스 평균({average:.1f}건)에 못 미쳤습니다. "
                        "위치·프로그램·인센티브를 검토하세요."
                    ),
                )
            )

    for title, change_pp, sufficient in impacts:
        if sufficient and abs(change_pp) >= 10:
            direction = "올랐습니다" if change_pp > 0 else "내렸습니다"
            out.append(
                Improvement(
                    rule="CAMPAIGN_EFFECT",
                    message=(
                        f"'{title}' 전후로 대상 부스 비중이 {change_pp:+.1f}%p {direction}. "
                        "같은 전략을 다음 행사에서 다시 확인해 볼 만합니다."
                    ),
                )
            )
            break

    return out


# ── 조립 ────────────────────────────────────────────────────────────────────


def build(
    db: Session,
    festival: Festival,
    impacts: list[tuple[str, float, bool]] | None = None,
) -> Report:
    summary = _summary(db, festival.id)
    timeline = _timeline(db, festival.id)
    booths, unassigned = _booths(db, festival.id, summary.total_completions)
    missions = _missions(db, festival.id, summary.total_completions)
    basis = visitor_basis(db, festival.id, summary.unique_participants)

    return Report(
        festival=festival,
        summary=summary,
        timeline=timeline,
        booths=booths,
        missions=missions,
        unassigned_completions=unassigned,
        visitor_basis=basis,
        kpi=_kpi(db, festival, summary, basis),
        recommendation_hits=_recommendation_hits(db, festival.id),
        improvements=_improvements(summary, timeline, booths, impacts or []),
    )
