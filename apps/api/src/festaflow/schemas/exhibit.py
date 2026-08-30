"""전시 작품 · 심사 · 투표 스키마.

**관객 응답에 다른 사람의 표나 심사 점수를 담지 않습니다.** 투표 중에 순위가
보이면 표가 순위를 따라가고, 그건 더 이상 관객 투표가 아닙니다.
집계는 운영자 타입(`ExhibitResultOut`)에서만 나옵니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExhibitIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    team_name: str | None = Field(None, max_length=120)
    summary: str | None = Field(None, max_length=2000)
    poster_url: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=12)
    location: str | None = Field(None, max_length=200)
    estimated_duration_minutes: int | None = Field(None, ge=1, le=1440)
    is_active: bool = True
    is_featured: bool = False


class ExhibitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    entry_no: int
    title: str
    team_name: str | None
    summary: str | None
    poster_url: str | None
    tags: list[str]
    location: str | None
    estimated_duration_minutes: int | None
    is_active: bool
    is_featured: bool


class ExhibitList(BaseModel):
    items: list[ExhibitOut]
    total: int
    #: 등록된 작품들이 쓴 태그 전체. 화면의 거르기 칩이 이걸 쓴다.
    tags: list[str] = Field(default_factory=list)


# ── 심사 항목 ───────────────────────────────────────────────────────────────


class CriterionIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    description: str | None = Field(None, max_length=300)
    max_score: int = Field(5, ge=1, le=100)
    #: 항목 간 상대 가중치. %가 아닌 이유는 항목 하나를 빼면 합이 100 이
    #: 아니게 되기 때문이다.
    weight: int = Field(1, ge=1, le=1000)
    sort_order: int = 0
    is_active: bool = True


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    festival_id: int
    label: str
    description: str | None
    max_score: int
    weight: int
    sort_order: int
    is_active: bool


# ── 심사위원 ────────────────────────────────────────────────────────────────


class ScoreIn(BaseModel):
    criterion_id: int
    score: int = Field(ge=0, le=100)
    comment: str | None = Field(None, max_length=2000)


class ScoreSheetIn(BaseModel):
    """한 작품에 대한 심사표. 항목들을 한 번에 낸다."""

    scores: list[ScoreIn] = Field(min_length=1)


class MyScoreOut(BaseModel):
    criterion_id: int
    score: int
    comment: str | None = None


class JudgeSheetOut(BaseModel):
    """심사위원이 보는 한 작품. **다른 심사위원의 점수는 담지 않는다.**

    남의 점수가 보이면 거기에 끌려갑니다. 합의가 필요하면 회의에서 하는 것이지
    입력 화면에서 서로의 숫자를 보며 하는 것이 아닙니다.
    """

    exhibit: ExhibitOut
    criteria: list[CriterionOut]
    my_scores: list[MyScoreOut] = Field(default_factory=list)
    #: 내가 이 작품의 모든 항목을 매겼는가.
    is_complete: bool = False


class JudgeProgressOut(BaseModel):
    total_exhibits: int
    scored_exhibits: int
    sheets: list[JudgeSheetOut]


# ── 관객 ────────────────────────────────────────────────────────────────────


class PublicExhibit(BaseModel):
    """관객이 보는 작품. **득표수를 담지 않는다.**"""

    id: int
    entry_no: int
    title: str
    team_name: str | None
    summary: str | None
    poster_url: str | None
    tags: list[str]
    location: str | None
    #: 내가 이 작품에 표를 줬는가.
    voted: bool = False
    #: 내가 표를 준 시각. 표를 주지 않았다면 None.
    voted_at: datetime | None = None


class VotingStatus(BaseModel):
    """관객 투표 화면이 필요한 전부."""

    voting_open: bool
    #: 익명 축제에서는 1인 1표를 보장할 수 없어 투표를 열 수 없다.
    can_vote: bool
    #: 투표할 수 없다면 왜인지. 화면이 그대로 보여줄 문장.
    reason: str | None = None
    votes_used: int
    votes_limit: int
    exhibits: list[PublicExhibit] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class VoteResult(BaseModel):
    exhibit_id: int
    voted: bool
    votes_used: int
    votes_limit: int


# ── 집계 (운영자) ───────────────────────────────────────────────────────────


class CriterionResultOut(BaseModel):
    criterion_id: int
    label: str
    max_score: int
    weight: int
    #: 아무도 안 매겼으면 None. 0 과 다르다.
    average: float | None
    judge_count: int


class ExhibitResultOut(BaseModel):
    exhibit: ExhibitOut
    criteria: list[CriterionResultOut]
    judge_count: int
    votes: int
    judge_score: float | None
    audience_score: float | None
    final_score: float | None


class ResultsOut(BaseModel):
    """시상 근거. **최종 점수만 내려주지 않는다.**

    이의가 들어왔을 때 "심사 70 · 관객 30 가중이고, 심사는 항목별로 이렇게
    나왔다"를 그 자리에서 보여줄 수 없으면 그 점수는 근거가 아니라 선언입니다.
    """

    judge_weight_percent: int
    audience_weight_percent: int
    votes_limit: int
    voting_open: bool
    items: list[ExhibitResultOut]
    #: 집계를 믿어도 되는지 흔드는 사실들. 시상 전에 알아야 한다.
    warnings: list[dict] = Field(default_factory=list)


class ExhibitionSettingsIn(BaseModel):
    audience_votes_per_participant: int = Field(ge=1, le=20)
    judge_weight_percent: int = Field(ge=0, le=100)
    voting_open: bool
