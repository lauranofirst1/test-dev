"""보상 캠페인 · 실측 방문객 · 추천 판정 기록."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base
from festaflow.models.enums import RecommendationType, VisitorSource


def _pg_enum(enum_cls, name: str):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class RewardCampaign(Base):
    """한시 추가 보상. 겹치면 합산하지 않고 최대 보너스 1건만 적용한다."""

    __tablename__ = "reward_campaigns"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        CheckConstraint("bonus_points >= 0", name="bonus_non_negative"),
        Index(
            "ix_reward_campaigns_active",
            "festival_id",
            "starts_at",
            "ends_at",
            postgresql_where="is_active",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    booth_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL = 선택 부스의 모든 활성 미션에 적용
    mission_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("missions.id", ondelete="CASCADE"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    bonus_points: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VisitorCount(Base):
    """실측 방문객.

    우리는 방문객을 측정하지 않지만 **받아올 수는 있습니다.**
    같은 날짜에 여러 출처가 공존할 수 있고(입구 계수기와 지자체 집계가 다른 건 정상),
    리포트는 우선순위가 높은 하나를 쓰고 나머지는 병기합니다.
    """

    __tablename__ = "visitor_counts"
    __table_args__ = (
        UniqueConstraint("festival_id", "count_date", "source", name="uq_visitor_counts_key"),
        CheckConstraint("visitors >= 0", name="visitors_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    visitors: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[VisitorSource] = mapped_column(
        _pg_enum(VisitorSource, "visitor_source"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecommendationFeedback(Base):
    """추천 판정 기록.

    제품이 자기 추천의 정확도를 스스로 측정하게 만드는 장치입니다.
    사후 리포트가 "추천 N건 중 M건이 현장과 일치"로 집계합니다.
    """

    __tablename__ = "recommendation_feedbacks"
    __table_args__ = (Index("ix_recommendation_feedbacks_festival", "festival_id", "rec_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )
    rec_type: Mapped[RecommendationType] = mapped_column(
        _pg_enum(RecommendationType, "recommendation_type"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: true = 현장과 일치함
    verdict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
