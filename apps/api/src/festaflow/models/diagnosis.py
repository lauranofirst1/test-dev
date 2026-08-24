"""진단 · 진단 항목 · 관광 스냅샷 · 채점표 검증 기록.

진단은 **append-only** 입니다. 스냅샷을 복사하거나 최신 진단을 교체하지 않습니다.
"최신 진단"은 ORDER BY created_at DESC LIMIT 1, "직전 대비"는 LIMIT 2 입니다.

각 진단은 계산에 쓴 input_snapshot·rubric_version·tourism_snapshot_id 를 함께 저장하므로
나중에도 당시 값 그대로 재현·설명됩니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from festaflow.db.base import Base
from festaflow.models.enums import (
    DiagnosisCategory,
    DiagnosisStatus,
    RiskLevel,
    TourismProvider,
)


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class TourismSnapshot(Base):
    """관광 지표 스냅샷.

    🚨 공모전 기간에는 캐시를 끕니다(TOURISM_SNAPSHOT_CACHE_ENABLED=false).
       규정이 실시간 호출을 요구하고 인증키 호출 이력을 검증하므로,
       이 테이블은 **API 실패 시 폴백과 이력 보존 용도로만** 씁니다.
    """

    __tablename__ = "tourism_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "region_key", "base_month", "provider", name="uq_tourism_snapshots_key"
        ),
        Index("ix_tourism_snapshots_expiry", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    region_key: Mapped[str] = mapped_column(Text, nullable=False)
    base_month: Mapped[str] = mapped_column(CHAR(6), nullable=False)  # YYYYMM
    provider: Mapped[TourismProvider] = mapped_column(
        _pg_enum(TourismProvider, "tourism_provider"), nullable=False
    )

    # ── 공사 실데이터 ──
    stay_index: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    spend_index: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    demand_index: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    season_fit: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    content_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── FestaFlow 추정치 ──
    estimated_daily_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    congestion_risk: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    local_link_readiness: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    # ── 공사 조회값 (추정치를 대체) ──
    #: DataLabService/tarDecoList — 혼잡 위험도를 계산에서 조회로
    congestion_forecast: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    #: DataLabService/tarTursmRqmtList — 히트맵 체류시간 기준선
    avg_dwell_minutes: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    #: DataLabService/tmap* — 시간대 분포 (식음료/그외 분리)
    hourly_pattern: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: DataLabService/locgoRegnVisitrDDList
    visitor_counts_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: TarRlteTarService1 — 지역 연계 준비도의 실제 근거
    related_spots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: LocgoHubTarService1
    hub_spots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: 대표 관광자원 최대 8개. 유형은 lclsSystm1, 지역은 lDong* 기준.
    resources: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    source_note: Mapped[str] = mapped_column(Text, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RubricCalibration(Base):
    """채점표 백테스트 기록.

    이 기록이 있는 rubric_version 만 점수를 공개할 수 있습니다.
    근거 없는 78.5점보다 근거 있는 체크리스트가 낫기 때문입니다.
    """

    __tablename__ = "rubric_calibrations"
    __table_args__ = (CheckConstraint("sample_size > 0", name="sample_size_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rubric_version: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    correlation: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_by: Mapped[str] = mapped_column(Text, nullable=False)
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        CheckConstraint("total_score IS NULL OR total_score BETWEEN 0 AND 100", name="score_range"),
        Index("ix_diagnoses_latest", "festival_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[DiagnosisStatus] = mapped_column(
        _pg_enum(DiagnosisStatus, "diagnosis_status"),
        nullable=False,
        server_default=DiagnosisStatus.PENDING.value,
    )
    rubric_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="v1")
    total_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    risk: Mapped[RiskLevel | None] = mapped_column(_pg_enum(RiskLevel, "risk_level"), nullable=True)

    #: 계산에 쓴 축제·기획·부스·미션 값 전체. 재현성의 근거.
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tourism_snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tourism_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[DiagnosisItem]] = relationship(
        back_populates="diagnosis", cascade="all, delete-orphan"
    )


class DiagnosisItem(Base):
    __tablename__ = "diagnosis_items"
    __table_args__ = (
        UniqueConstraint("diagnosis_id", "category", name="uq_diagnosis_items_category"),
        CheckConstraint("score >= 0", name="score_non_negative"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
        CheckConstraint("score <= max_score", name="score_within_max"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    diagnosis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[DiagnosisCategory] = mapped_column(
        _pg_enum(DiagnosisCategory, "diagnosis_category"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    level: Mapped[RiskLevel] = mapped_column(_pg_enum(RiskLevel, "risk_level"), nullable=False)
    #: 계산 근거 — 어떤 데이터를 썼는지(조회/추정/폴백)까지 문장으로 남긴다.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    diagnosis: Mapped[Diagnosis] = relationship(back_populates="items")
