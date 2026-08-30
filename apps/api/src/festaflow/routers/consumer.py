"""참가자의 명시적 관심과 행사 후 Favorite Memory API."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from festaflow.core.deps import CurrentParticipant, DbSession
from festaflow.models import ExperienceOpen, FavoriteMemory
from festaflow.schemas.consumer import (
    ExperienceOpenIn,
    ExperienceOpenOut,
    FavoriteMemoryIn,
    FavoriteMemoryOut,
)
from festaflow.services.consumer import resolve_source

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["consumer"])


@router.post(
    "/experience-opens",
    response_model=ExperienceOpenOut,
    status_code=status.HTTP_201_CREATED,
)
def record_experience_open(
    festival_id: int,
    payload: ExperienceOpenIn,
    db: DbSession,
    participant: CurrentParticipant,
) -> ExperienceOpenOut:
    resolve_source(
        db,
        festival_id=festival_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        active_only=True,
    )
    row = ExperienceOpen(
        festival_id=festival_id,
        participant_id=participant.id,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ExperienceOpenOut(
        id=row.id,
        source_type=row.source_type,
        source_id=row.source_id,
        source_context=row.source_context,
        opened_at=row.opened_at,
    )


@router.get("/favorite-memory", response_model=FavoriteMemoryOut | None)
def get_favorite_memory(
    festival_id: int,
    db: DbSession,
    participant: CurrentParticipant,
) -> FavoriteMemoryOut | None:
    row = db.execute(
        select(FavoriteMemory).where(
            FavoriteMemory.festival_id == festival_id,
            FavoriteMemory.participant_id == participant.id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return FavoriteMemoryOut.model_validate(row, from_attributes=True)


@router.put("/favorite-memory", response_model=FavoriteMemoryOut)
def put_favorite_memory(
    festival_id: int,
    payload: FavoriteMemoryIn,
    db: DbSession,
    participant: CurrentParticipant,
) -> FavoriteMemoryOut:
    # 기억은 행사가 끝난 뒤에도 남길 수 있으므로 archived source도 허용한다.
    resolve_source(
        db,
        festival_id=festival_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        active_only=False,
    )
    values = {
        "festival_id": festival_id,
        "participant_id": participant.id,
        **payload.model_dump(),
    }
    statement = (
        insert(FavoriteMemory)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_favorite_memories_participant",
            set_={
                "source_type": payload.source_type,
                "source_id": payload.source_id,
                "reason": payload.reason,
                "comment": payload.comment,
                "updated_at": func.now(),
            },
        )
        .returning(FavoriteMemory.id)
    )
    memory_id = db.execute(statement).scalar_one()
    db.commit()
    row = db.get(FavoriteMemory, memory_id)
    return FavoriteMemoryOut.model_validate(row, from_attributes=True)
