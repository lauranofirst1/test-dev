"""운영 인사이트 응답 · 추천 판정 입력. 계약 §5, §14.5."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import BoothLoadStatus, RecommendationType


class InsightKpi(BaseModel):
    total_participants: int
    total_completions: int
    completions_last_30m: int
    #: 최근 30분 상태가 HIGH 인 부스 수.
    high_concentration_booths: int


class BoothLoadOut(BaseModel):
    booth_id: int
    name: str
    is_active: bool
    total_completions: int
    unique_participants: int
    last_10m: int
    last_30m: int
    last_60m: int
    share_last_30m: float
    status: BoothLoadStatus
    #: 화면이 비율을 다시 계산하지 않게 서버가 판정 근거를 문장으로 내려준다.
    #: 색만으로 상태를 알리면 색각 이상 사용자와 흑백 인쇄에서 정보가 사라진다.
    status_reason: str
    status_label: str
    last_completed_at: datetime | None


class RecommendationOut(BaseModel):
    """상황 · 판단 근거 · 권장 행동을 **분리해서** 담는다.

    한 문단으로 합치면 근거와 지시가 섞여 "데이터가 그렇다니 하라는 대로"
    읽힙니다. 나눠 두면 운영자가 근거를 먼저 보고 판단할 수 있습니다.
    """

    type: RecommendationType
    situation: str
    evidence: str
    action: str
    target_booth_id: int | None


class WarningOut(BaseModel):
    code: str
    message: str


class InsightsOut(BaseModel):
    generated_at: datetime
    kpi: InsightKpi
    booths: list[BoothLoadOut]
    recommendations: list[RecommendationOut]
    warnings: list[WarningOut]
    #: 항상 함께 나갑니다. 조건부로 빼면 빠진 화면에서 혼잡도로 읽힙니다.
    disclaimer: str


class FeedbackIn(BaseModel):
    """추천 카드의 확인함 / 해당 없음.

    제품이 자기 추천의 정확도를 스스로 측정하게 만드는 입력입니다.
    """

    model_config = ConfigDict(extra="forbid")

    rec_type: RecommendationType
    booth_id: int | None = None
    #: 추천이 화면에 떠 있던 시각. 지금 시각이 아니다 — 운영자가 현장을 확인하고
    #: 돌아와 누르기까지 몇 분이 걸리고, 그 사이 상태는 바뀐다.
    observed_at: datetime
    verdict: bool = Field(description="true = 현장이 추천과 일치했다")


class FeedbackOut(BaseModel):
    id: int
    rec_type: RecommendationType
    booth_id: int | None
    verdict: bool
    observed_at: datetime
