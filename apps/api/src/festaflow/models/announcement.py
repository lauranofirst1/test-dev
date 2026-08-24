"""현장 공지 — 지금 알려야 하는 것.

보상 캠페인과 다릅니다. 캠페인은 포인트를 바꾸는 **개입**이고, 공지는 아무것도
바꾸지 않는 **전달**입니다. 우천으로 야외 부스가 멈췄다는 사실은 포인트와 무관하게
전달돼야 합니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base
from festaflow.models.enums import AnnouncementChannel, AnnouncementLevel


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Announcement(Base):
    """공지 한 건."""

    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="window_valid"),
        # 살아 있는 공지만 훑는 조회가 대부분이다.
        Index(
            "ix_announcements_live",
            "festival_id",
            "starts_at",
            postgresql_where="is_active",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    channel: Mapped[AnnouncementChannel] = mapped_column(
        _pg_enum(AnnouncementChannel, "announcement_channel"), nullable=False
    )
    level: Mapped[AnnouncementLevel] = mapped_column(
        _pg_enum(AnnouncementLevel, "announcement_level"),
        nullable=False,
        server_default=AnnouncementLevel.NORMAL.value,
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: NULL 이면 **운영자가 끌 때까지** 떠 있다.
    #:
    #: 종료 시각을 필수로 하면 우천 공지처럼 언제 끝날지 모르는 것을 못 올린다.
    #: 운영자는 "일단 3시간" 같은 임의의 값을 넣게 되고, 그 시각이 지나면 비가
    #: 그대로인데 공지만 사라진다.
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AnnouncementAck(Base):
    """긴급 공지를 누가 확인했는가.

    두 가지 일을 합니다.

    1. 확인한 사람에게 같은 덮개를 다시 씌우지 않습니다. 폴링마다 다시 뜨면
       화면을 쓸 수 없습니다.
    2. 운영자에게 **몇 명이 봤는지** 알려줍니다. 우천 중단 공지를 띄우고도
       몇 명이 봤는지 모르면, 띄운 것이 전달된 것인지 알 수 없습니다.

    확인 기록을 브라우저에만 두지 않는 이유가 2번입니다. 로컬에만 두면 1번은
    되지만 운영자는 아무것도 알 수 없습니다.
    """

    __tablename__ = "announcement_acks"
    __table_args__ = (
        # 참여자이거나 스태프이거나, 정확히 하나다.
        CheckConstraint(
            "(participant_id IS NULL) <> (staff_id IS NULL)", name="one_identity"
        ),
        # 같은 사람이 두 번 확인해도 행은 하나다. 애플리케이션 조건문으로 두면
        # 덮개를 연타하는 동시 요청에서 뚫린다.
        Index(
            "uq_announcement_acks_participant",
            "announcement_id",
            "participant_id",
            unique=True,
            postgresql_where="participant_id IS NOT NULL",
        ),
        Index(
            "uq_announcement_acks_staff",
            "announcement_id",
            "staff_id",
            unique=True,
            postgresql_where="staff_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    announcement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )
    staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="CASCADE"), nullable=True
    )
    acked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
