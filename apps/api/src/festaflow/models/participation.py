"""참여자 · 참여 이력 · 부스 스캔 사용 기록.

핵심 원칙: **집계 대상은 지급 시점에 고정한다.**
부스·미션·캠페인을 나중에 바꿔도 과거 수치가 변하지 않아야 한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base
from festaflow.models.enums import BoothVerifyMode, ParticipationStatus


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Participant(Base):
    """익명 참여자. 코드는 서버가 발급하고 유일성을 보장한다."""

    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("festival_id", "code", name="uq_participants_festival_code"),
        CheckConstraint("code ~ '^FF-[0-9A-Z]{8}$'", name="code_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    #: 조회 인증용. 발급 시 1회만 평문 전달. 코드는 부스에서 노출되므로 분리해야 한다.
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)

    #: 기기 변경 복구. 휴대폰 뒷 4자리를 축제별 솔트와 함께 해시로만 저장한다.
    recovery_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    #: 축제 종료 +90일. 찍히면 code 는 파기된 상태이며 개인 단위 추적이 불가능해진다.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Participation(Base):
    __tablename__ = "participations"
    __table_args__ = (
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_consistent"
        ),
        CheckConstraint("base_points >= 0", name="base_points_non_negative"),
        CheckConstraint("bonus_points >= 0", name="bonus_points_non_negative"),
        CheckConstraint("attempt_count >= 1", name="attempt_count_positive"),
        # 중복 지급 방지 — 애플리케이션 코드에만 두면 동시 요청에서 뚫린다.
        Index(
            "uq_participations_grant",
            "participant_id",
            "mission_id",
            unique=True,
            postgresql_where="mission_id IS NOT NULL",
        ),
        # 오프라인 재전송이 중복 지급이 되지 않게.
        Index(
            "uq_participations_client_request",
            "client_request_id",
            unique=True,
            postgresql_where="client_request_id IS NOT NULL",
        ),
        Index(
            "ix_participations_festival_time",
            "festival_id",
            "completed_at",
            postgresql_where="status = 'completed'",
        ),
        Index(
            "ix_participations_booth_time",
            "booth_id",
            "completed_at",
            postgresql_where="status = 'completed'",
        ),
        Index("ix_participations_participant", "participant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True
    )
    #: 지급 시점 스냅샷. 미션을 다른 부스로 옮겨도 과거 집계가 이동하지 않는다.
    booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ParticipationStatus] = mapped_column(
        _pg_enum(ParticipationStatus, "participation_status"),
        nullable=False,
        server_default=ParticipationStatus.COMPLETED.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── 포인트 스냅샷 ──
    base_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bonus_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: 생성 컬럼 — 애플리케이션이 합계를 잘못 계산할 여지를 없앤다.
    granted_points: Mapped[int] = mapped_column(
        Integer, Computed("base_points + bonus_points", persisted=True), nullable=False
    )
    reward_campaign_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reward_campaigns.id", ondelete="SET NULL"), nullable=True
    )

    verified_via: Mapped[BoothVerifyMode | None] = mapped_column(
        _pg_enum(BoothVerifyMode, "booth_verify_mode"), nullable=True
    )
    granted_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )

    #: 체험 응답. quiz 정답 여부, survey 응답, info 체류시간 등.
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")

    # ── 오프라인 큐 동기화 ──
    client_request_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    #: 현장에서 지급 버튼을 누른 시각. completed_at 은 이 값으로 기록한다 —
    #: 그래야 통신 복구 시각에 완료가 몰려 보이는 왜곡이 생기지 않는다.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BoothScanUse(Base):
    """1 스캔 = 1 미션 지급.

    부스 QR 은 방문을 확인할 뿐 개별 미션 수행을 확인하지 못하므로,
    한 번 스캔으로 그 부스 미션을 전부 쓸어담는 것을 막는다.
    """

    __tablename__ = "booth_scan_uses"
    __table_args__ = (
        UniqueConstraint(
            "booth_id", "window_index", "participant_id", name="uq_booth_scan_uses_window"
        ),
        Index("ix_booth_scan_uses_cleanup", "used_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booth_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="CASCADE"), nullable=False
    )
    window_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    participation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("participations.id", ondelete="SET NULL"), nullable=True
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
