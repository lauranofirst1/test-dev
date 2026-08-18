"""스태프 로그인 스키마 — docs/03-api-contract.md §1."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
