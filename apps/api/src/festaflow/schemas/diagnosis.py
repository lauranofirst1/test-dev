"""진단 응답 스키마.

표시 모드에 따라 점수를 감춥니다. `display_mode = "checklist"` 이면
`total_score` / `risk` / `items[].score` 가 전부 null 이고 `fulfillment` 만 채워집니다.
점수는 DB 에 그대로 저장돼 있으며 **응답에서만** 감춥니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from festaflow.models.enums import DiagnosisCategory, RiskLevel


class DiagnosisItemOut(BaseModel):
    category: DiagnosisCategory
    score: float | None
    max_score: float | None
    level: RiskLevel
    #: checklist 모드에서 쓰는 표시값 — met / partial / unmet
    fulfillment: str
    reason: str
    recommendation: str
    details: dict


class TourismSource(BaseModel):
    provider: str
    base_month: str
    #: 지표별 조회/추정 구분
    indicators: dict[str, str]
    note: str


class DiagnosisOut(BaseModel):
    id: int
    festival_id: int
    status: str
    rubric_version: str
    display_mode: str
    score_disclosed: bool
    total_score: float | None
    risk: RiskLevel | None
    items: list[DiagnosisItemOut]
    top_risks: list[str]
    warnings: list[str]
    tourism_source: TourismSource | None
    #: 점수를 보여줄 때 화면에 반드시 함께 표시해야 하는 문구
    disclosure_note: str | None
    api_calls: int | None
    created_at: datetime


class DiagnosisDelta(BaseModel):
    category: DiagnosisCategory
    previous: float | None
    current: float | None
    delta: float | None


class DiagnosisComparison(BaseModel):
    comparable: bool
    reason: str | None = None
    previous: dict | None = None
    current: dict | None = None
    delta: float | None = None
    items: list[DiagnosisDelta] = []
    biggest_improvement: dict | None = None
