"""Experience 관심과 참가자가 명시적으로 남긴 Favorite Memory."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ExperienceSourceType = Literal["mission", "lecture", "exhibit"]
ExperienceOpenContext = Literal[
    "now",
    "featured",
    "explore_time",
    "explore_place",
    "explore_type",
    "search",
    "shared_link",
    "flow",
]
MemoryReason = Literal["fun", "new", "together", "discovered", "again"]


class ExperienceOpenIn(BaseModel):
    source_type: ExperienceSourceType
    source_id: int = Field(gt=0)
    source_context: ExperienceOpenContext


class ExperienceOpenOut(ExperienceOpenIn):
    id: int
    opened_at: datetime


class FavoriteMemoryIn(BaseModel):
    source_type: ExperienceSourceType
    source_id: int = Field(gt=0)
    reason: MemoryReason | None = None
    comment: str | None = Field(None, max_length=500)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FavoriteMemoryOut(FavoriteMemoryIn):
    id: int
    created_at: datetime
    updated_at: datetime
