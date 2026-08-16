"""SQLAlchemy 선언적 기반.

제약 이름 규칙을 고정합니다. Alembic 이 자동 생성한 마이그레이션에서
제약 이름이 매번 달라지면 다운그레이드가 깨지기 때문입니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pk() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def fk_col() -> Mapped[int]:
    """FK 컬럼 타입. PK 가 BigInteger 이므로 맞춰야 한다."""
    return mapped_column(BigInteger)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ArchivableMixin:
    """삭제는 전부 아카이브. 목록·집계는 archived_at IS NULL 만 본다."""

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
