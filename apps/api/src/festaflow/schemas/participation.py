"""참여자 · 스탬프 보드 · 지급 스키마 — docs/03-api-contract.md §7~§9."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import BoothType, BoothVerifyMode, GrantUnit, RevealMode

# ── 참여자 ──────────────────────────────────────────────────────────────────


class ParticipantIssued(BaseModel):
    """`secret` 은 이 응답에서만 나온다. 이후 어떤 조회에도 포함되지 않는다."""

    code: str
    secret: str
    festival_id: int


class MissionStatus(BaseModel):
    mission_id: int
    booth_id: int | None
    booth_name: str | None
    title: str
    points: int
    #: pending | granted
    status: str
    granted_points: int | None = None
    completed_at: datetime | None = None


class ActiveCampaign(BaseModel):
    id: int
    booth_id: int
    mission_id: int | None
    title: str
    message: str
    bonus_points: int
    ends_at: datetime


class ParticipantMe(BaseModel):
    code: str
    festival_id: int
    total_points: int
    completed_count: int
    missions: list[MissionStatus]
    active_campaigns: list[ActiveCampaign] = Field(default_factory=list)


# ── 공개 정보 ───────────────────────────────────────────────────────────────


class PublicMission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booth_id: int | None
    title: str
    description: str | None
    points: int


class PublicBooth(BaseModel):
    id: int
    name: str
    booth_type: BoothType
    type_label: str | None
    location: str | None
    verify_mode: BoothVerifyMode
    missions: list[PublicMission] = Field(default_factory=list)


class PublicFestival(BaseModel):
    """관객 화면이 참여 전에 보는 것. 인증이 없으므로 운영 정보는 담지 않는다."""

    id: int
    name: str
    region: str
    venue: str
    starts_on: str
    ends_on: str
    booths: list[PublicBooth]
    #: 화면에 반드시 함께 표시해야 하는 출처 표기
    source_note: str = "출처: ⓒ한국관광공사"


# ── 스탬프 보드 ─────────────────────────────────────────────────────────────


class BoardTile(BaseModel):
    tile_index: int
    assigned_booth_id: int | None = None
    #: 참여자 보드에서만 의미가 있다. 운영자 조회에서는 항상 False.
    is_revealed: bool = False
    revealed_at: datetime | None = None


class StampBoardOut(BaseModel):
    id: int
    festival_id: int
    version: int
    rows: int
    cols: int
    total_tiles: int
    reveal_mode: RevealMode
    grant_unit: GrantUnit
    image_url: str
    complete_message: str
    tiles: list[BoardTile]


class StampBoardUpdate(BaseModel):
    rows: int = Field(ge=2, le=3)
    cols: int = Field(ge=2, le=3)
    reveal_mode: RevealMode
    grant_unit: GrantUnit
    image_url: str = Field(min_length=1)
    complete_message: str = Field(min_length=1)


class StampBoardAdmin(StampBoardOut):
    """운영자 조회. 참여자 응답에는 운영 경고를 싣지 않는다."""

    #: 완성이 불가능한 구성이면 여기에 담긴다 — 당일에 알면 늦다.
    warnings: list[dict] = Field(default_factory=list)


class BoardProgress(BaseModel):
    revealed_count: int
    total_tiles: int
    is_complete: bool


class ParticipantBoard(StampBoardOut):
    progress: BoardProgress
    #: 완성했을 때만 채운다 — 미완성 상태에서 미리 보여주면 완성의 의미가 없다.
    complete_message_shown: str | None = None


# ── 지급 ────────────────────────────────────────────────────────────────────


class StaffGrantIn(BaseModel):
    """계약 §8.1. `participant_code` 는 서버가 공백 제거·대문자 정규화한다."""

    participant_code: str = Field(min_length=1, max_length=32)
    mission_id: int
    #: 오프라인 큐 재전송이 중복 지급이 되지 않게 하는 키.
    client_request_id: str | None = None


class ScanGrantIn(BaseModel):
    """계약 §8.3."""

    booth_id: int
    token: str = Field(min_length=1, max_length=64)
    mission_id: int
    client_request_id: str | None = None


class ParticipationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mission_id: int | None
    booth_id: int | None
    base_points: int
    bonus_points: int
    granted_points: int
    reward_campaign_id: int | None
    verified_via: BoothVerifyMode | None
    completed_at: datetime | None


class RevealedTile(BaseModel):
    tile_index: int
    board_version: int


class GrantResult(BaseModel):
    """중복 요청이면 `was_already_granted: true` 와 기존 상태를 그대로 돌려준다."""

    was_already_granted: bool
    participation: ParticipationOut
    revealed_tile: RevealedTile | None
    board_progress: BoardProgress


class RecentGrant(BaseModel):
    participation_id: int
    participant_code: str
    mission_title: str | None
    granted_points: int
    completed_at: datetime | None


class ScanContextMission(BaseModel):
    mission_id: int
    title: str
    description: str | None
    points: int
    #: 이미 받았으면 화면에서 흐리게 처리한다.
    already_granted: bool


class ScanContext(BaseModel):
    """스캔 직후 미션 선택 화면 — 계약 §8.3."""

    booth_id: int
    booth_name: str
    type_label: str | None
    location: str | None
    window_index: int
    #: 이 QR 이 화면에서 갱신되는 시각(= window 끝).
    expires_at: datetime
    #: 서버가 **실제로 받아주는** 마지막 시각. 직전 window 도 인정하므로
    #: expires_at 보다 한 window 뒤다. 화면은 이 값으로 카운트다운해야 한다 —
    #: expires_at 로 잠그면 서버가 받아줄 30초를 화면이 먼저 포기한다.
    accepted_until: datetime
    seconds_remaining: int
    missions: list[ScanContextMission]
    #: 이 window 에서 이미 한 건 받았으면 다시 스캔해야 한다.
    scan_already_used: bool
