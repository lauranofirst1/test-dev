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
        # 1 학번 = 1 참여자. **이 인덱스가 투표 부정 방지의 뿌리다.**
        # 애플리케이션 조건문으로 두면 동시 요청에서 뚫리고, 뚫리는 순간
        # 스티커를 여러 장 붙이던 행위가 그대로 재현된다.
        Index(
            "uq_participants_student_no",
            "festival_id",
            "student_no",
            unique=True,
            postgresql_where="student_no IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)

    #: 학번. `identity_mode = student_id` 인 축제에서만 채워진다.
    #:
    #: **해시가 아니라 평문입니다.** 공결이 걸린 특강은 학교에 낼 출석 명단이
    #: 필요한데, 해시만 저장하면 그 명단을 만들 수 없어 기능 자체가 죽습니다.
    #: 대신 노출 경계를 좁힙니다 — 참여자 응답에는 절대 나가지 않고 운영자
    #: 응답에서만 나옵니다(schemas 가 유일한 경계입니다).
    #:
    #: 익명 축제에서는 NULL 입니다. 부분 유니크 인덱스가 그 경우를 비워 둡니다.
    student_no: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        #
        # **축제 단위다.** 재전송은 언제나 같은 축제로 가고(URL 에 축제가 있다),
        # 전역으로 두면 두 가지가 깨진다 — 다른 축제가 우연히 같은 키를 쓰면
        # 500 으로 막히고, 조회에 스코프가 없으면 남의 축제 지급 기록이
        # `was_already_granted` 와 함께 그대로 돌아간다. 이 값은 클라이언트가
        # 만들어 보내는 값이라 우연에만 기대면 안 된다.
        Index(
            "uq_participations_client_request",
            "festival_id",
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


class MissionAttempt(Base):
    """체험 시도 횟수.

    계약(§11)은 오답과 시도 소진이 **참여 이력을 만들지 않는다**고 못박습니다.
    집계에 섞이면 안 되기 때문입니다. 그런데 이력을 만들지 않으면 시도 횟수를
    둘 곳이 없어지고, `max_attempts` 는 클라이언트 말을 믿는 값이 됩니다.
    집에서 답을 세 번 틀려도 새로고침하면 처음으로 돌아갑니다.

    그래서 시도만 따로 셉니다. 이 테이블은 집계 대상이 아니며, 어떤 리포트도
    읽지 않습니다. 지급이 성사되면 이 값이 `participations.attempt_count` 로
    옮겨 적히고, 그때부터는 참여 이력이 진실입니다.
    """

    __tablename__ = "mission_attempts"
    __table_args__ = (
        UniqueConstraint("participant_id", "mission_id", name="uq_mission_attempts_key"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
