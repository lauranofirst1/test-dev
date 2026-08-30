"""소비자 Experience 관심과 명시적 Favorite Memory.

Experience 자체는 기존 Mission/LectureSession/Exhibit가 소유한다. 이 테이블은
그 source identity만 기록하며, 실제 행사 소속 검증은 쓰기 서비스에서 수행한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base, TimestampMixin


class ExperienceOpen(Base):
    __tablename__ = "experience_opens"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('mission', 'lecture', 'exhibit')",
            name="source_type_valid",
        ),
        CheckConstraint("source_id > 0", name="source_id_positive"),
        CheckConstraint(
            "source_context IN ('now', 'featured', 'explore_time', 'explore_place', "
            "'explore_type', 'search', 'shared_link', 'flow')",
            name="source_context_valid",
        ),
        Index(
            "ix_experience_opens_source_time",
            "festival_id",
            "source_type",
            "source_id",
            "opened_at",
        ),
        Index("ix_experience_opens_participant_time", "participant_id", "opened_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_context: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FavoriteMemory(Base, TimestampMixin):
    __tablename__ = "favorite_memories"
    __table_args__ = (
        UniqueConstraint(
            "festival_id", "participant_id", name="uq_favorite_memories_participant"
        ),
        CheckConstraint(
            "source_type IN ('mission', 'lecture', 'exhibit')",
            name="source_type_valid",
        ),
        CheckConstraint("source_id > 0", name="source_id_positive"),
        Index(
            "ix_favorite_memories_source",
            "festival_id",
            "source_type",
            "source_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
