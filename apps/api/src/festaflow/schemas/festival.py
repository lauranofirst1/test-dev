"""축제 요청·응답 스키마."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from festaflow.models.enums import FestivalStatus, GrantUnit, PlanStage, RevealMode


class FestivalPlanIn(BaseModel):
    """기획 상세. 전부 선택 입력이며, 비어 있으면 운영 준비도 진단에서 부족 항목으로 잡힌다."""

    summary: str | None = Field(None, max_length=300)
    description: str | None = None
    purposes: list[str] = Field(default_factory=list)
    target_segments: list[str] = Field(default_factory=list)
    core_audience: str | None = None

    staff_count: int | None = Field(None, ge=0)
    volunteer_count: int | None = Field(None, ge=0)
    safety_staff_count: int | None = Field(None, ge=0)
    parking_capacity: int | None = Field(None, ge=0)
    venue_capacity: int | None = Field(None, ge=0, description="동시 수용 인원. 진단 수용력 2순위 근거")

    planned_performance: int = Field(0, ge=0)
    planned_experience: int = Field(0, ge=0)
    planned_food: int = Field(0, ge=0)
    planned_local_shop: int = Field(0, ge=0)
    planned_tour_info: int = Field(0, ge=0)
    planned_etc: int = Field(0, ge=0)

    transit_access: str | None = None
    traffic_plan: str | None = None
    crowd_plan: str | None = None
    safety_plan: str | None = None

    tourism_link_plan: str | None = None
    local_commerce_plan: str | None = None
    lodging_plan: str | None = None
    promotion_plan: str | None = None


class FestivalPlanOut(FestivalPlanIn):
    model_config = ConfigDict(from_attributes=True)


class FestivalBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    region: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    starts_on: date
    ends_on: date
    expected_visitors: int = Field(gt=0, description="0보다 커야 합니다")
    total_budget: int = Field(ge=0)

    @model_validator(mode="after")
    def _period(self):
        if self.ends_on < self.starts_on:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        return self


class StampBoardIn(BaseModel):
    """조각 보드 초기 구성.

    조각 수는 부스 수에 맞춰 정한다 — 격자는 2~5 범위다.

    비우면 3×3 이 기본이다. 부스 수가 조각 수보다 적으면 완성이 불가능하므로,
    부스 계획이 작은 축제는 여기서 줄여야 한다(등록 후에도 바꿀 수 있다).
    """

    rows: int = Field(3, ge=2, le=5)
    cols: int = Field(3, ge=2, le=5)
    reveal_mode: RevealMode = RevealMode.RANDOM
    grant_unit: GrantUnit = GrantUnit.BOOTH


class FestivalCreate(FestivalBase):
    plan: FestivalPlanIn | None = None
    stamp_board: StampBoardIn | None = None


class FestivalUpdate(FestivalBase):
    plan: FestivalPlanIn | None = None


class FestivalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    region: str
    venue: str
    starts_on: date
    ends_on: date
    expected_visitors: int
    total_budget: int
    status: FestivalStatus
    plan_stage: PlanStage
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class FestivalDetail(FestivalOut):
    plan: FestivalPlanOut | None = None
    duration_days: int
    booth_count: int = 0
    mission_count: int = 0


class FestivalCreated(BaseModel):
    festival: FestivalOut
    diagnosis: dict
    stamp_board: dict
    #: 이 응답에서만 평문으로 노출된다. 이후 어떤 조회에도 나오지 않는다.
    operator_access_code: str


class FestivalList(BaseModel):
    items: list[FestivalOut]
    total: int
