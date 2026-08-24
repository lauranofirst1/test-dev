"""참여자 · 스탬프 보드 · 지급 스키마 — docs/03-api-contract.md §7~§9."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from festaflow.models.enums import (
    BoardStyle,
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    ExperienceType,
    GrantUnit,
    IdentityMode,
    RevealMode,
)

# ── 참여자 ──────────────────────────────────────────────────────────────────


class ParticipantIssue(BaseModel):
    """참여 시작 요청.

    익명 축제에서는 본문이 필요 없습니다. 학번 축제에서는 학번이 필수이며,
    이미 발급된 학번이면 **새 참여자를 만들지 않고** 기존 참여를 이어받습니다.
    """

    student_no: str | None = Field(None, max_length=32)


class ParticipantIssued(BaseModel):
    """`secret` 은 이 응답에서만 나온다. 이후 어떤 조회에도 포함되지 않는다."""

    code: str
    secret: str
    festival_id: int
    #: 이미 있던 학번이라 기존 참여를 이어받았는가. 화면 문구가 달라진다.
    resumed: bool = False


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
    #: 참여 시작 화면이 학번을 물어야 하는지 여기서 정해진다.
    identity_mode: IdentityMode = IdentityMode.ANONYMOUS
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
    #: 표현만 정한다 — 바꿔도 진행이 초기화되지 않는다.
    board_style: BoardStyle = BoardStyle.GRID
    image_url: str
    complete_message: str
    tiles: list[BoardTile]


class StampBoardUpdate(BaseModel):
    # 2~5 — DB 의 rows_range/cols_range 와 같은 범위.
    rows: int = Field(ge=2, le=5)
    cols: int = Field(ge=2, le=5)
    reveal_mode: RevealMode
    grant_unit: GrantUnit
    #: 구조가 아니라 표현이므로 STRUCTURAL 에 넣지 않는다 — 버전을 올리지 않는다.
    board_style: BoardStyle = BoardStyle.GRID
    image_url: str = Field(min_length=1)
    complete_message: str = Field(min_length=1)


class GridOptionOut(BaseModel):
    """기획자에게 제시하는 격자 후보. A안·B안·C안으로 보여준다."""

    rows: int
    cols: int
    total: int
    #: 지급 단위 수와 정확히 맞는가
    exact: bool
    #: 조각을 못 받고 남는 지급 단위 수
    leftover: int


class StampBoardAdmin(StampBoardOut):
    """운영자 조회. 참여자 응답에는 운영 경고도 제안도 싣지 않는다."""

    #: 완성이 불가능한 구성이면 여기에 담긴다 — 당일에 알면 늦다.
    warnings: list[dict] = Field(default_factory=list)
    #: 지급 단위(부스 또는 미션) 수와 이름. 화면이 다시 세지 않게 함께 보낸다.
    unit_count: int = 0
    unit_label: str = "부스"
    #: 지급 단위 수에 맞춰 쪼갤 격자 후보. 정확히 맞는 것이 앞에 온다.
    grid_options: list[GridOptionOut] = Field(default_factory=list)


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
    #:
    #: **형식을 여기서 검사한다.** DB 컬럼이 `UUID` 라 아무 문자열이나 통과시키면
    #: Postgres 에서 터져 500 이 되고, 500 은 큐가 **재시도하는** 응답이라
    #: 그 항목 하나가 큐 앞에서 영원히 돈다. 422 로 답해야 큐가 사람에게 넘긴다.
    #:
    #: **버전은 강제하지 않는다.** 우리 화면은 v4 를 만들지만, 다른 클라이언트가
    #: v1 이나 v7 을 보낼 이유가 충분하고 그게 재전송 키로서 못할 일이 없다.
    #: 여기서 막아야 하는 것은 "UUID 가 아닌 값" 이지 "v4 가 아닌 값" 이 아니다.
    client_request_id: UUID | None = None
    #: 스태프가 **현장에서 버튼을 누른** 시각. 도달 시각이 아니다.
    #:
    #: 이 값이 없으면 오프라인에 쌓였던 지급이 전부 통신 복구 시점으로 기록되어,
    #: 운영 인사이트의 "최근 30분 편중" 과 리포트 시간축이 통째로 왜곡된다.
    #: 서버는 이 값을 `completed_at` 으로 쓴다 — 계약 §14.3.
    queued_at: datetime | None = None


class ScanGrantIn(BaseModel):
    """계약 §8.3, §11.

    `response` 는 체험 제출입니다 — quiz 는 `{"choice_index": 0}`,
    info 는 `{"dwell_seconds": 7}`. stamp 는 비워 둡니다.
    채점은 서버에서만 하므로 여기에 정답 여부를 실어 보내도 무시됩니다.
    """

    booth_id: int
    #: 회전 QR 의 토큰. 인쇄 부스에서는 비운다.
    token: str | None = Field(None, min_length=1, max_length=64)
    #: 인쇄 QR 의 고정 서명. 회전 부스에서는 비운다 — 계약 §14.4.
    signature: str | None = Field(None, min_length=1, max_length=64)
    mission_id: int
    response: dict | None = None
    client_request_id: UUID | None = None
    #: 참여자 화면도 오프라인 큐를 쓸 수 있다. 의미는 `StaffGrantIn.queued_at` 과 같다.
    queued_at: datetime | None = None


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
    #: 지급까지 걸린 시도 횟수. 퀴즈에서만 1 보다 커진다.
    attempt_count: int = 1


class RevealedTile(BaseModel):
    tile_index: int
    board_version: int


class GrantResult(BaseModel):
    """중복 요청이면 `was_already_granted: true` 와 기존 상태를 그대로 돌려준다."""

    was_already_granted: bool
    participation: ParticipationOut
    revealed_tile: RevealedTile | None
    board_progress: BoardProgress
    #: 퀴즈 해설. 맞힌 뒤에만 내려간다 — 설정에 담아 미리 내리면 정답이 새고,
    #: 틀린 직후에 내리면 남은 시도가 공짜가 된다.
    explanation: str | None = None


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

    # ── 체험 (§11) ──
    experience_type: ExperienceType = ExperienceType.STAMP
    #: **정답이 빠진** 설정. quiz 의 answer_index 는 여기 절대 담기지 않는다.
    experience_config: dict = Field(default_factory=dict)
    #: 남은 시도 횟수. 제한이 없는 유형이면 None.
    attempts_left: int | None = None


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
    #: 인쇄 QR 은 만료되지 않으므로 None. 화면은 이때 카운트다운을 그리지 않는다.
    seconds_remaining: int | None
    #: 이 부스가 인쇄 QR 인지 회전 QR 인지. 화면 문구가 달라진다.
    qr_mode: BoothQrMode = BoothQrMode.ROTATING
    missions: list[ScanContextMission]
    #: 이 window 에서 이미 한 건 받았으면 다시 스캔해야 한다.
    scan_already_used: bool
