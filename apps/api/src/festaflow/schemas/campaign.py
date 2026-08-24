"""보상 캠페인 입출력. 계약 §6."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CampaignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booth_id: int
    #: 비우면 선택 부스의 **모든 활성 미션**에 적용된다.
    mission_id: int | None = None
    title: str = Field(min_length=1, max_length=120)
    #: 참여자 화면 배너에 그대로 나가는 문장이다.
    message: str = Field(min_length=1, max_length=500)
    #: 0 을 허용한다 — 포인트 없이 안내만 띄우는 캠페인도 쓰임이 있다.
    bonus_points: int = Field(ge=0, le=100_000)
    starts_at: datetime
    ends_at: datetime


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booth_id: int | None = None
    mission_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    message: str | None = Field(default=None, min_length=1, max_length=500)
    bonus_points: int | None = Field(default=None, ge=0, le=100_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class CampaignOut(BaseModel):
    id: int
    festival_id: int
    booth_id: int
    booth_name: str
    mission_id: int | None
    mission_title: str | None
    title: str
    message: str
    bonus_points: int
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    #: **서버 시각** 판정 결과. 클라이언트가 다시 계산하지 않는다.
    is_live: bool


class CampaignList(BaseModel):
    items: list[CampaignOut]
    total: int


# ── 개입 효과 ───────────────────────────────────────────────────────────────


class ImpactWindow(BaseModel):
    frm: datetime = Field(serialization_alias="from")
    to: datetime
    target_completions: int
    festival_completions: int
    share: float

    model_config = ConfigDict(populate_by_name=True)


class TopBoothOut(BaseModel):
    booth_id: int
    name: str
    share_before: float
    share_after: float


class ImpactOut(BaseModel):
    campaign_id: int
    window_minutes: int
    before: ImpactWindow
    after: ImpactWindow
    share_change_pp: float
    #: before 가 0건이면 **null**. 0 을 분모로 배수를 만들지 않는다.
    completion_change_rate: float | None
    top_booth_before: TopBoothOut | None
    data_status: str
    in_progress: bool
    #: 항상 함께 나갑니다. 빼면 이 표는 인과 효과처럼 읽힙니다.
    disclaimer: str
