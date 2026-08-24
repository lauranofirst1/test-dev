"""특강 세션 · 체크인 · 출석 — 공결이 걸린 강의의 출튀 방지.

**입장 스캔 한 번으로는 출석을 증명하지 못합니다.** 찍고 나가면 그만이고,
공결이 걸려 있으면 그렇게 하는 사람이 반드시 생깁니다. 퇴장 스캔을 더해도
중간에 나갔다가 끝날 때 돌아오면 똑같습니다.

그래서 **예고 없는 시점에 여러 번** 확인합니다. 강의 중 아무 때나 운영자가
체크인을 열면 스크린에 QR 이 뜨고, 그때 자리에 있는 사람만 찍을 수 있습니다.
언제 열릴지 모르니 자리를 뜰 수 없습니다.

QR 은 **회전합니다.** 인쇄 QR 을 여기에 쓰면 사진 한 장이 단톡방에 돌면서
출결이 통째로 무너집니다 — 부스 지급과 달리 여기서는 선택지가 아닙니다.

체크인은 열린 동안만 받습니다. 계속 열어 두면 늦게 온 사람도 다 찍혀서
"그 시간에 그 자리에 있었다"를 증명하지 못합니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from festaflow.db.base import ArchivableMixin, Base, TimestampMixin


class LectureSession(Base, TimestampMixin, ArchivableMixin):
    """특강 한 회차."""

    __tablename__ = "lecture_sessions"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="period_valid"),
        CheckConstraint("required_checkins >= 1", name="required_positive"),
        Index(
            "ix_lecture_sessions_festival",
            "festival_id",
            "starts_at",
            postgresql_where="archived_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(120), nullable=True)
    affiliation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: 출석으로 인정하려면 몇 번의 체크인에 응해야 하는가.
    #:
    #: 열린 체크인 **전부**를 요구하지 않는 이유는 화장실·통신 문제처럼 정당한
    #: 사유로 한 번 놓치는 경우가 반드시 생기기 때문입니다. 전부를 요구하면
    #: 그 한 번 때문에 공결이 날아가고, 운영자는 결국 손으로 예외를 만듭니다.
    required_checkins: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="2"
    )

    #: 공결 대상 강의인가. 화면 문구와 명단 출력이 달라진다.
    grants_excused_absence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    #: 체크인 QR 의 HMAC 키. 부스 `qr_secret` 과 같은 이유로 응답에 싣지 않는다.
    qr_secret: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, server_default=text("gen_random_bytes(32)")
    )

    checkpoints: Mapped[list[SessionCheckpoint]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionCheckpoint(Base):
    """운영자가 "지금 체크인"을 누른 한 순간.

    `closes_at` 이 지나면 더 받지 않습니다. 계속 열어 두면 늦게 들어온 사람도
    전부 찍혀서 이 장치가 아무것도 증명하지 않게 됩니다.
    """

    __tablename__ = "session_checkpoints"
    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="window_valid"),
        Index("ix_session_checkpoints_session", "session_id", "opens_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lecture_sessions.id", ondelete="CASCADE"), nullable=False
    )
    #: 이 세션에서 몇 번째로 열린 체크인인가. 화면이 "2회차"로 부른다.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    opens_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    opened_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[LectureSession] = relationship(back_populates="checkpoints")


class SessionAttendance(Base):
    """한 참여자가 한 체크인에 응한 기록."""

    __tablename__ = "session_attendances"
    __table_args__ = (
        # 같은 체크인에 두 번 찍어도 한 번이다. 조건문이 아니라 여기가 막는다.
        UniqueConstraint(
            "checkpoint_id", "participant_id", name="uq_session_attendances_key"
        ),
        Index("ix_session_attendances_session", "session_id", "participant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lecture_sessions.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session_checkpoints.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
