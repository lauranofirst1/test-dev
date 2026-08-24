"""현장 공지 입출력."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import AnnouncementChannel, AnnouncementLevel


class AnnouncementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: AnnouncementChannel
    level: AnnouncementLevel = AnnouncementLevel.NORMAL
    #: 관객은 제목만 읽고 지나갑니다. 제목 하나로 뜻이 통해야 합니다.
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1000)
    #: 비우면 지금부터.
    starts_at: datetime | None = None
    #: 비우면 **운영자가 끌 때까지**. 언제 끝날지 모르는 상황이 대부분입니다.
    ends_at: datetime | None = None


class AnnouncementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: AnnouncementChannel | None = None
    level: AnnouncementLevel | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=1000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class AnnouncementOut(BaseModel):
    id: int
    channel: AnnouncementChannel
    level: AnnouncementLevel
    title: str
    body: str
    starts_at: datetime
    ends_at: datetime | None
    is_active: bool
    #: **서버 시각** 판정. 화면이 다시 계산하지 않습니다.
    is_live: bool
    #: 긴급 공지를 확인한 인원. 띄운 것과 전달된 것은 다릅니다.
    ack_count: int


class AnnouncementList(BaseModel):
    items: list[AnnouncementOut]
    total: int


class LiveAnnouncement(BaseModel):
    """관객·스태프 화면이 지금 그려야 하는 것."""

    id: int
    level: AnnouncementLevel
    title: str
    body: str
    starts_at: datetime
    #: 이 사람이 이미 확인했는가. 긴급 덮개를 다시 씌울지 정합니다.
    acked: bool


class LiveAnnouncementList(BaseModel):
    #: 긴급이 먼저 옵니다. 화면이 다시 정렬하지 않아도 첫 건이 덮개 후보입니다.
    items: list[LiveAnnouncement]


class AckOut(BaseModel):
    announcement_id: int
    acked_at: datetime
