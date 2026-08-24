"""스태프 로그인 스키마 — docs/03-api-contract.md §1."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from festaflow.models.enums import StaffRole


class StaffLogin(BaseModel):
    """2단계 로그인의 2단계. 초대 QR 이 festival_id·staff_id 를 채우고,
    사람이 6자리 접근 코드를 입력한다. QR 사진만으로는 들어올 수 없다."""

    festival_id: int
    staff_id: int
    access_code: str = Field(min_length=4, max_length=64)


class StaffInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    role: StaffRole
    display_name: str
    booth_id: int | None = None


class StaffSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    #: 만료까지 남은 초. 프런트가 재로그인 시점을 잡는다.
    expires_in: int
    staff: StaffInfo


# ── 기관 계정 ────────────────────────────────────────────────────────────────


class SignUp(BaseModel):
    """기관 회원가입. 첫 계정이 기관을 함께 만든다."""

    organization_name: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    #: 길이가 곧 강도다. 기호를 강제하지 않는 이유는 아래 services 주석 참고.
    password: str = Field(min_length=10, max_length=200)


class LogIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class AccountInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    email: str
    display_name: str


class AccountSession(BaseModel):
    """세션은 **httpOnly 쿠키로** 나갑니다. 본문에는 토큰이 없습니다 —
    화면이 손에 쥘 수 없어야 XSS 로도 새지 않습니다."""

    account: AccountInfo
    organization_name: str
    expires_in: int


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


# ── 스태프 발급 (계약 §1) ────────────────────────────────────────────────────


class StaffIssue(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: StaffRole
    #: `booth_manager` 만 의미가 있다. 그 스태프는 이 부스의 미션만 지급할 수 있다.
    booth_id: int | None = None


class StaffIssued(BaseModel):
    """**평문 접근 코드는 이 응답에서만 나옵니다.**

    저장하는 것은 bcrypt 해시뿐이라 서버도 다시 알아낼 수 없습니다.
    잃어버리면 재발급이 유일한 길이며, 그게 맞습니다 — 서버가 되읽을 수 있다면
    유출됐을 때 전부 함께 나갑니다.
    """

    staff: StaffInfo
    #: 오리진 없는 경로. **브라우저는 이걸 쓰고 자기 오리진을 앞에 붙입니다.**
    #: `invite_url` 은 `PUBLIC_WEB_ORIGIN` 이 없으면 요청이 도착한 주소(=API 서버)로
    #: 만들어져, 프런트가 따로 뜬 환경에서는 열리지 않는 곳을 가리킵니다.
    invite_path: str
    invite_url: str
    access_code: str


class StaffRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    role: StaffRole
    display_name: str
    booth_id: int | None
    is_active: bool
    last_login_at: datetime | None
    #: 지금 잠겨 있는가. 운영자가 "왜 못 들어오지" 를 바로 알 수 있어야 한다.
    locked_until: datetime | None
    failed_attempts: int


class StaffList(BaseModel):
    items: list[StaffRow]
    total: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class PasswordResetAccepted(BaseModel):
    """**가입 여부와 무관하게 같은 응답입니다.**

    응답이 갈리면 이 화면이 곧 "이 이메일이 가입돼 있나" 를 확인해 주는
    도구가 됩니다.
    """

    message: str = (
        "가입된 이메일이면 재설정 링크를 보냈습니다. 메일함을 확인해 주세요."
    )
    #: 메일 발송기가 아직 없다는 사실. 로컬에서만 채워지며, 운영자가
    #: "메일이 왜 안 오지" 로 시간을 쓰지 않게 화면이 그대로 보여준다.
    delivery_note: str | None = None
