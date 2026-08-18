"""부스 · 미션 스키마 — docs/03-api-contract.md §4.

`qr_secret` 은 어떤 응답에도 포함하지 않습니다. 모델에 있으니 스키마에서
빠뜨리기만 하면 되는 게 아니라, 이 파일이 유일한 노출 경계라는 뜻입니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import (
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    ExperienceType,
)


class MissionIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    points: int = Field(0, ge=0, le=1_000_000)
    is_active: bool = True
    experience_type: ExperienceType = ExperienceType.STAMP
    experience_config: dict = Field(default_factory=dict)


class MissionCreate(MissionIn):
    #: 어느 부스의 미션인지. 부스 생성 시 함께 만드는 경우에는 서버가 채운다.
    booth_id: int | None = None


class MissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    booth_id: int | None
    title: str
    description: str | None
    points: int
    is_active: bool
    experience_type: ExperienceType
    created_at: datetime
    updated_at: datetime


class BoothIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    booth_type: BoothType
    type_label: str | None = Field(None, max_length=60)
    location: str | None = Field(None, max_length=200)
    manager_name: str | None = Field(None, max_length=120)
    is_active: bool = True
    verify_mode: BoothVerifyMode = BoothVerifyMode.STAFF_SCAN
    qr_mode: BoothQrMode = BoothQrMode.PRINTED
    use_experience: bool = False
    experience_theme: dict = Field(default_factory=dict)


class BoothCreate(BoothIn):
    #: 부스만 만들고 미션이 없으면 지급할 것이 없다. 첫 미션을 같은 요청에서 받는다.
    first_mission: MissionIn | None = None


class BoothOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    name: str
    booth_type: BoothType
    type_label: str | None
    location: str | None
    manager_name: str | None
    is_active: bool
    verify_mode: BoothVerifyMode
    qr_mode: BoothQrMode
    use_experience: bool
    created_at: datetime
    updated_at: datetime


class BoothDetail(BoothOut):
    missions: list[MissionOut] = Field(default_factory=list)


class BoothCreated(BaseModel):
    booth: BoothOut
    first_mission: MissionOut | None = None


class BoothList(BaseModel):
    items: list[BoothDetail]
    total: int


class MissionList(BaseModel):
    items: list[MissionOut]
    total: int


class ScanToken(BaseModel):
    """부스 화면이 30초마다 다시 받아 QR 을 갱신한다 — 계약 §8.2."""

    booth_id: int
    scan_url: str
    window_index: int
    expires_at: datetime
    refresh_after_seconds: int
