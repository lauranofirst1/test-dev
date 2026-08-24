"""스탬프 이미지 보드 · 타일 · 공개 이력.

보드 구조를 바꿔도 **기존 공개 이력을 삭제하지 않습니다.**
version 을 올리고 새 타일 집합을 만들며, 과거 reveal 은 이전 버전 기록으로 남습니다.
축제 당일 오조작 한 번으로 모든 참여자의 수집이 증발하는 일을 막기 위해서입니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from festaflow.db.base import Base
from festaflow.models.enums import BoardStyle, GrantUnit, RevealMode


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class StampBoard(Base):
    __tablename__ = "stamp_boards"
    __table_args__ = (
        # 조각 수는 **부스 수에 맞춰** 정한다. 4·6·9 세 가지로 묶어두면 부스가
        # 8개인 축제는 9조각(완성 불가)이나 6조각(2개 부스가 조각 없이 남음) 중
        # 하나를 골라야 한다. 2~5 범위면 4·6·8·9·10·12·15·16·20·25 를 만들 수 있다.
        CheckConstraint("rows BETWEEN 2 AND 5", name="rows_range"),
        CheckConstraint("cols BETWEEN 2 AND 5", name="cols_range"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    rows: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cols: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    reveal_mode: Mapped[RevealMode] = mapped_column(
        _pg_enum(RevealMode, "reveal_mode"), nullable=False, server_default=RevealMode.RANDOM.value
    )
    #: booth = 부스당 1조각(순회 유도), mission = 미션 완료마다 1조각
    grant_unit: Mapped[GrantUnit] = mapped_column(
        _pg_enum(GrantUnit, "grant_unit"), nullable=False, server_default=GrantUnit.BOOTH.value
    )

    #: 표현만 정한다. 바꿔도 타일과 공개 기록은 그대로라 진행이 초기화되지 않는다.
    board_style: Mapped[BoardStyle] = mapped_column(
        _pg_enum(BoardStyle, "board_style"), nullable=False, server_default=BoardStyle.GRID.value
    )

    image_url: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="/images/chuncheon-stamp-board.png"
    )
    complete_message: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="모든 축제 조각을 완성했습니다!"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tiles: Mapped[list[StampTile]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )

    @property
    def total_tiles(self) -> int:
        return self.rows * self.cols


class StampTile(Base):
    __tablename__ = "stamp_tiles"
    __table_args__ = (
        UniqueConstraint("board_id", "board_version", "tile_index", name="uq_stamp_tiles_index"),
        # 한 부스는 한 버전 안에서 한 타일에만 배정된다.
        Index(
            "uq_stamp_tiles_booth",
            "board_id",
            "board_version",
            "assigned_booth_id",
            unique=True,
            postgresql_where="assigned_booth_id IS NOT NULL",
        ),
        CheckConstraint("tile_index >= 0", name="tile_index_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stamp_boards.id", ondelete="CASCADE"), nullable=False
    )
    board_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tile_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    assigned_booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )

    board: Mapped[StampBoard] = relationship(back_populates="tiles")


class StampReveal(Base):
    """참여자별 조각 공개 기록. 보드 버전이 올라가도 삭제하지 않는다."""

    __tablename__ = "stamp_reveals"
    __table_args__ = (
        UniqueConstraint(
            "board_version", "participant_id", "tile_id", name="uq_stamp_reveals_tile"
        ),
        # grant_unit='booth' 일 때 부스당 1조각.
        Index(
            "uq_stamp_reveals_booth",
            "board_id",
            "board_version",
            "participant_id",
            "booth_id",
            unique=True,
            postgresql_where="booth_id IS NOT NULL",
        ),
        Index("ix_stamp_reveals_lookup", "board_id", "board_version", "participant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stamp_boards.id", ondelete="CASCADE"), nullable=False
    )
    board_version: Mapped[int] = mapped_column(Integer, nullable=False)
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    tile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stamp_tiles.id", ondelete="CASCADE"), nullable=False
    )
    booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )
    participation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("participations.id", ondelete="SET NULL"), nullable=True
    )
    revealed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
