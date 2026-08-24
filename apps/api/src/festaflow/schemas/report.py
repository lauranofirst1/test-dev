"""사후 리포트 · 성과 목표 · 실측 방문객. 계약 §15, §14.1."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import VisitorSource

# ── 성과 목표 ───────────────────────────────────────────────────────────────


class KpiTargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: 기본 지표 키이거나 `custom:` 접두어가 붙은 사용자 정의.
    metric_key: str = Field(min_length=1, max_length=80)
    #: 기본 지표면 서버가 정한 라벨로 덮어씁니다 — 라벨이 제각각이면
    #: 축제 간 비교가 안 됩니다.
    label: str | None = Field(default=None, max_length=80)
    target_value: float = Field(ge=0)
    unit: str | None = Field(default=None, max_length=20)


class KpiTargetOut(BaseModel):
    id: int
    metric_key: str
    label: str
    target_value: float
    unit: str
    #: **운영자가 정하지 않습니다.** 측정 가능 여부는 지표의 성질입니다.
    is_measurable: bool


class KpiTargetList(BaseModel):
    items: list[KpiTargetOut]
    #: 아직 안 세운 기본 지표. 화면이 목록을 하드코딩하지 않게 서버가 준다.
    available: list[dict]


# ── 실측 방문객 ─────────────────────────────────────────────────────────────


class VisitorCountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count_date: date
    visitors: int = Field(ge=0)
    source: VisitorSource
    note: str | None = Field(default=None, max_length=500)


class VisitorCountOut(BaseModel):
    id: int
    count_date: date
    visitors: int
    source: VisitorSource
    source_label: str
    note: str | None


class VisitorCountList(BaseModel):
    items: list[VisitorCountOut]
    total_visitors: int


# ── 리포트 ──────────────────────────────────────────────────────────────────


class SummaryOut(BaseModel):
    unique_participants: int
    total_completions: int
    avg_completions_per_participant: float
    missions_with_completion: dict


class PlanVsActual(BaseModel):
    expected_visitors: int
    festaflow_participants: int
    participation_scale: float
    #: 항상 함께 나갑니다. 빼면 이 숫자는 방문률로 읽힙니다.
    disclaimer: str


class VisitorBasisOut(BaseModel):
    visitors: int
    source: VisitorSource
    source_label: str
    #: 추산 출처에만 붙습니다.
    caveat: str | None
    participation_rate: float
    #: 같은 날짜의 다른 출처. 숨기지 않고 병기합니다.
    others: list[dict]


class TimelinePoint(BaseModel):
    hour_kst: datetime
    completions: int


class BoothPerformanceOut(BaseModel):
    booth_id: int
    name: str
    completions: int
    unique_participants: int
    share: float
    rank: int
    peak_hour_kst: datetime | None
    peak_completions: int


class MissionPerformanceOut(BaseModel):
    mission_id: int
    title: str
    booth_name: str | None
    completions: int
    unique_participants: int
    share: float


class KpiResultOut(BaseModel):
    metric_key: str
    label: str
    target: float
    actual: float | None
    #: `measurable: false` 면 **항상 null** 입니다.
    achievement: float | None
    measurable: bool
    unit: str
    note: str | None


class RecommendationAccuracy(BaseModel):
    total: int
    hits: int
    rate: float


class CampaignImpactSummary(BaseModel):
    campaign_id: int
    title: str
    booth_name: str
    share_change_pp: float
    data_status: str
    in_progress: bool


class ImprovementOut(BaseModel):
    rule: str
    message: str


class ReportOut(BaseModel):
    festival_id: int
    festival_name: str
    generated_at: datetime
    summary: SummaryOut
    plan_vs_actual: PlanVsActual
    #: 실측이 없으면 **null**. 없는 참여율을 만들어 내지 않습니다.
    visitor_basis: VisitorBasisOut | None
    timeline: list[TimelinePoint]
    booths: list[BoothPerformanceOut]
    missions: list[MissionPerformanceOut]
    #: 부스 스냅샷이 해제된 참여 수. 전체 완료에는 포함하되 임의 배정하지 않습니다.
    unassigned_completions: int
    #: 목표를 세우지 않았으면 빈 배열.
    kpi: list[KpiResultOut]
    #: 판정 기록이 없으면 null.
    recommendation_accuracy: RecommendationAccuracy | None
    campaigns: list[CampaignImpactSummary]
    improvements: list[ImprovementOut]
