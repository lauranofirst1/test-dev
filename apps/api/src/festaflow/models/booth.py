"""부스 · 미션."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from festaflow.db.base import ArchivableMixin, Base, TimestampMixin
from festaflow.models.enums import BoothQrMode, BoothType, BoothVerifyMode, ExperienceType


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Booth(Base, TimestampMixin, ArchivableMixin):
    __tablename__ = "booths"
    __table_args__ = (
        Index(
            "uq_booths_festival_name",
            "festival_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where="archived_at IS NULL",
        ),
        Index("ix_booths_festival", "festival_id", postgresql_where="archived_at IS NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    booth_type: Mapped[BoothType] = mapped_column(_pg_enum(BoothType, "booth_type"), nullable=False)
    type_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manager_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── QR 확인 방식 ──
    verify_mode: Mapped[BoothVerifyMode] = mapped_column(
        _pg_enum(BoothVerifyMode, "booth_verify_mode"),
        nullable=False,
        server_default=BoothVerifyMode.STAFF_SCAN.value,
    )
    #: 인쇄가 기본. 회전 QR 은 태블릿·전원·네트워크가 있는 부스의 상위 옵션.
    qr_mode: Mapped[BoothQrMode] = mapped_column(
        _pg_enum(BoothQrMode, "booth_qr_mode"),
        nullable=False,
        server_default=BoothQrMode.PRINTED.value,
    )
    #: HMAC 키. API 응답에 절대 포함하지 않는다.
    qr_secret: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, server_default=text("gen_random_bytes(32)")
    )

    # ── QR 체험 화면 테마 ──
    use_experience: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    experience_theme: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    missions: Mapped[list[Mission]] = relationship(back_populates="booth")


class Mission(Base, TimestampMixin, ArchivableMixin):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint("points BETWEEN 0 AND 1000000", name="points_range"),
        Index("ix_missions_booth", "booth_id", postgresql_where="archived_at IS NULL"),
        Index("ix_missions_festival", "festival_id", postgresql_where="archived_at IS NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL = 미배정. 부스를 아카이브하면 여기로 떨어진다.
    booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── QR 체험 ──
    experience_type: Mapped[ExperienceType] = mapped_column(
        _pg_enum(ExperienceType, "experience_type"),
        nullable=False,
        server_default=ExperienceType.STAMP.value,
    )
    #: quiz 의 answer_index 는 참여자 응답에 절대 내려가지 않는다. 채점은 서버에서만.
    experience_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    booth: Mapped[Booth | None] = relationship(back_populates="missions")
