"""특강 세션 · 체크인 · 출결 스키마.

**학번은 운영자 응답에만 담습니다.** 참여자용 타입에 한 번이라도 넣으면
공개 화면으로 새고, 그때는 되돌릴 수 없습니다. 이 파일이 그 경계입니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LectureSessionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(None, max_length=2000)
    speaker: str | None = Field(None, max_length=120)
    affiliation: str | None = Field(None, max_length=120)
    location: str | None = Field(None, max_length=200)
    starts_at: datetime
    ends_at: datetime
    #: 출석 인정에 필요한 체크인 수. 열린 체크인 전부를 요구하지 않는다 —
    #: 화장실·통신 문제로 한 번 놓치는 경우가 반드시 생긴다.
    required_checkins: int = Field(2, ge=1, le=20)
    grants_excused_absence: bool = False
    is_active: bool = True
    is_featured: bool = False


class LectureSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    title: str
    summary: str | None
    speaker: str | None
    affiliation: str | None
    location: str | None
    starts_at: datetime
    ends_at: datetime
    required_checkins: int
    grants_excused_absence: bool
    is_active: bool
    is_featured: bool


class LectureSessionDetail(LectureSessionOut):
    #: 지금까지 열린 체크인 수.
    opened_checkpoints: int = 0
    #: 한 번이라도 찍은 사람 수.
    attendee_count: int = 0
    #: 요구 횟수를 채운 사람 수.
    met_count: int = 0


class LectureSessionList(BaseModel):
    items: list[LectureSessionDetail]
    total: int


# ── 체크인 ──────────────────────────────────────────────────────────────────


class CheckpointOut(BaseModel):
    id: int
    session_id: int
    sequence: int
    opens_at: datetime
    closes_at: datetime
    #: 지금 받고 있는가. 화면이 시각을 다시 판정하지 않게 서버가 정한다.
    is_open: bool
    #: 이 체크인에 응한 사람 수.
    checked_count: int = 0


class CheckpointToken(BaseModel):
    """스크린에 띄울 회전 QR. **인쇄 QR 은 없다.**

    사진 한 장이 단톡방에 돌면 출결이 통째로 무너집니다. 부스 지급에서는
    인쇄가 합리적인 선택지였지만 출결에서는 아닙니다.
    """

    checkpoint_id: int
    sequence: int
    scan_path: str
    scan_url: str
    expires_at: datetime
    closes_at: datetime
    refresh_after_seconds: int


class CheckInIn(BaseModel):
    checkpoint_id: int
    token: str = Field(min_length=1, max_length=64)


# ── 참여자가 보는 것 ────────────────────────────────────────────────────────


class MyAttendance(BaseModel):
    session_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    grants_excused_absence: bool
    checked: int
    required: int
    #: 지금까지 열린 체크인 수. 몇 번을 놓쳤는지 스스로 알 수 있어야 한다.
    opened: int
    is_met: bool
    remaining: int
    #: 출석 인정 기준을 채운 마지막 체크인 시각. 아직 인정 전이면 None.
    completed_at: datetime | None = None


class CertificateIssued(BaseModel):
    """학생이 교수님에게 건네는 확인 코드.

    **코드 자체가 비밀입니다.** 아는 사람은 누구나 그 출결을 봅니다 —
    화면도 "아무에게나 보여주지 마세요" 를 함께 안내해야 합니다.
    """

    session_id: int
    title: str
    code: str
    #: 오리진 없는 경로. 브라우저가 자기 오리진을 붙인다.
    verify_path: str


class CertificateOut(BaseModel):
    """교수님이 보는 확인 결과. **인증 없이 열립니다.**"""

    festival_name: str
    title: str
    speaker: str | None
    starts_at: datetime
    ends_at: datetime
    #: 뒷 세 자리만. 명단 수집이 아니라 본인 확인이 목적이다.
    student_no_masked: str | None
    participant_code: str
    checked: int
    opened: int
    required: int
    is_met: bool
    grants_excused_absence: bool
    #: 확인한 시각. 이 값은 스냅샷이 아니라 **지금** 조회한 결과다.
    verified_at: datetime


class CheckInResult(BaseModel):
    #: 방금 새로 찍혔는가. false 면 이미 찍혀 있었다는 뜻이고 오류가 아니다.
    was_new: bool
    sequence: int
    attendance: MyAttendance


# ── 운영자가 보는 것 ────────────────────────────────────────────────────────


class RosterRow(BaseModel):
    """공결 명단 한 줄. **학번이 여기에만 있다.**"""

    participant_code: str
    #: 익명 축제에서는 None.
    student_no: str | None
    checked: int
    required: int
    is_met: bool
    #: 비밀 재발급 횟수. 남의 학번을 넣어 가로채려는 시도가 여기서 드러난다.
    recovery_attempts: int


class RosterOut(BaseModel):
    session_id: int
    title: str
    opened_checkpoints: int
    required_checkins: int
    grants_excused_absence: bool
    rows: list[RosterRow]
    met_count: int
    total: int
