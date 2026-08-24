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
    """**운영자 전용 응답.**

    `experience_config` 에는 quiz 의 `answer_index` 가 그대로 들어 있습니다.
    이 타입을 참여자 경로에 쓰면 정답이 새어 나갑니다 — 참여자에게는
    `PublicMission` 과 `ScanContextMission` 만 나갑니다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    booth_id: int | None
    title: str
    description: str | None
    points: int
    is_active: bool
    experience_type: ExperienceType
    experience_config: dict = Field(default_factory=dict)
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
    """부스 QR 한 장 — 계약 §8.2, §14.4.

    회전(`rotating`)이면 부스 화면이 30초마다 다시 받아 갱신하고,
    인쇄(`printed`)면 한 번 받아 종이에 인쇄해 붙입니다. 인쇄 QR 은
    `qr_secret` 을 재발행할 때까지 바뀌지 않으므로 `expires_at` 이 없습니다.
    """

    booth_id: int
    qr_mode: BoothQrMode
    #: 오리진이 빠진 경로. **브라우저는 이걸 쓰고 자기 오리진을 앞에 붙인다.**
    #: 그래야 localhost·사내망 IP·운영 도메인 어디서 열어도 QR 이 맞는 곳을 가리킨다.
    scan_path: str
    #: 서버가 짐작한 전체 주소. `PUBLIC_WEB_ORIGIN` 이 없으면 요청이 도착한
    #: 주소(=API 서버)를 쓰므로 개발 환경에서는 틀릴 수 있다. 브라우저가 아닌
    #: 클라이언트(인쇄물 생성 등)를 위한 값이다.
    scan_url: str
    #: 회전 QR 에서만 의미가 있다. 인쇄 QR 은 window 에 묶이지 않는다.
    window_index: int | None = None
    #: 인쇄 QR 은 만료되지 않으므로 None.
    expires_at: datetime | None = None
    #: 화면이 다시 받아야 하는 주기(초). 인쇄 QR 은 None — 다시 받을 일이 없다.
    refresh_after_seconds: int | None = None
