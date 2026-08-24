"""경품 · 뽑기 스키마.

참여자 응답과 운영자 응답을 **다른 타입으로 분리**합니다. 재고 수량과 가중치는
운영 정보입니다. 참여자에게 "이 상품 3개 남음 · 가중치 10" 을 보여주면 남은 재고를
보고 뽑는 시점을 재는 사람이 생기고, 그건 추첨이 아니게 됩니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PrizeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    #: None = 무제한. 꽝은 여기를 비워 둔다.
    stock: int | None = Field(None, ge=0)
    weight: int = Field(1, ge=1, le=1_000_000)
    is_blank: bool = False
    is_active: bool = True


class PrizeOut(BaseModel):
    """운영자 응답. 재고와 가중치가 그대로 담긴다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    name: str
    description: str | None
    stock: int | None
    weight: int
    is_blank: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PrizeList(BaseModel):
    items: list[PrizeOut]
    total: int
    #: 지금 실제로 뽑힐 수 있는 상품 수. 0 이면 아무도 당첨되지 않는다.
    drawable_count: int = 0
    #: 완성이 눈앞인데 상품이 없다는 것을 당일에 알면 늦다.
    warnings: list[dict] = Field(default_factory=list)


# ── 참여자 ──────────────────────────────────────────────────────────────────


class PrizePreview(BaseModel):
    """참여 화면의 "무엇이 걸려 있나". 재고도 확률도 담지 않는다."""

    name: str
    description: str | None = None
    is_blank: bool = False


class PrizeDrawOut(BaseModel):
    """뽑기 결과. 꽝도 결과다 — 실패로 표현하지 않는다."""

    id: int
    drawn_at: datetime
    #: 뽑을 수 있는 상품이 하나도 없었으면 None. 꽝(is_blank)과 다르다.
    prize_name: str | None = None
    prize_description: str | None = None
    is_blank: bool = False
    #: 스태프가 실물을 건네고 찍는다. 참여자는 찍을 수 없다.
    claimed_at: datetime | None = None


class PrizeDrawStatus(BaseModel):
    """참여 화면이 뽑기 카드를 그리는 데 필요한 전부."""

    #: 뽑기를 운영자가 설정했는가. false 면 화면에 카드를 그리지 않는다.
    enabled: bool
    #: 지금 뽑을 수 있는가 — 완성했고 아직 안 뽑았다.
    can_draw: bool
    revealed_count: int
    total_tiles: int
    is_complete: bool
    #: 이미 뽑았으면 그 결과. 없으면 None.
    draw: PrizeDrawOut | None = None
    prizes: list[PrizePreview] = Field(default_factory=list)


# ── 운영자: 당첨자 ──────────────────────────────────────────────────────────


class PrizeDrawRow(BaseModel):
    id: int
    participant_code: str
    prize_id: int | None
    prize_name: str | None
    is_blank: bool
    drawn_at: datetime
    claimed_at: datetime | None


class PrizeDrawList(BaseModel):
    items: list[PrizeDrawRow]
    total: int
    #: 아직 실물을 안 가져간 당첨자 수. 꽝은 세지 않는다.
    unclaimed: int = 0


# ── 수령대 ──────────────────────────────────────────────────────────────────


class PrizeClaimLookup(BaseModel):
    """참여 코드로 찾은 수령 대상. 경품을 건네기 직전에 스태프가 보는 화면.

    **못 건네는 경우를 오류로 만들지 않습니다.** 꽝이거나 이미 수령했거나 아직
    안 뽑은 것은 전부 정상적인 사실이고, 스태프는 그걸 읽고 안내해야 합니다.
    404 로 돌려주면 화면이 "없는 코드"와 "꽝을 뽑은 사람"을 구분하지 못합니다.
    """

    participant_code: str
    #: 지금 경품을 건네도 되는가.
    claimable: bool
    #: 건넬 수 없다면 왜인지. 화면이 그대로 보여줄 한국어 문장.
    reason: str | None = None
    draw: PrizeDrawRow | None = None
