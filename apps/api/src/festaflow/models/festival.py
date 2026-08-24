"""기관 · 축제 · 기획 상세 · 스태프."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from festaflow.db.base import ArchivableMixin, Base, TimestampMixin
from festaflow.models.enums import (
    FestivalStatus,
    IdentityMode,
    PlanStage,
    PlanTier,
    StaffRole,
)


class Organization(Base):
    """기관. 축제는 반드시 하나에 속한다.

    지금 넣는 이유는, 나중에 소급하면 모든 쿼리에 테넌트 필터를 뒤늦게 끼워야 하고
    한 곳만 빠뜨려도 다른 기관 데이터가 새기 때문이다.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="agency")
    plan_tier: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=PlanTier.PER_FESTIVAL.value,
    )
    #: NULL = 무제한 (enterprise)
    festival_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    festivals: Mapped[list[Festival]] = relationship(back_populates="organization")


class Festival(Base, TimestampMixin, ArchivableMixin):
    __tablename__ = "festivals"
    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="period_valid"),
        CheckConstraint("expected_visitors > 0", name="visitors_positive"),
        CheckConstraint("total_budget >= 0", name="budget_non_negative"),
        Index(
            "ix_festivals_org_recent",
            "organization_id",
            "created_at",
            "id",
            postgresql_where="archived_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    expected_visitors: Mapped[int] = mapped_column(Integer, nullable=False)
    total_budget: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: 참여자를 어떻게 식별하는가. 익명이 기본이라 기존 관광 축제는 그대로 돈다.
    identity_mode: Mapped[IdentityMode] = mapped_column(
        Enum(IdentityMode, name="identity_mode", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=IdentityMode.ANONYMOUS.value,
    )

    # ── 전시 심사 ──
    #: 관객 한 명이 쓸 수 있는 표 수. 무제한이면 인기 작품에 몰아주기가 되고,
    #: 1표면 "가장 좋은 하나"만 남아 부문 시상이 안 나온다.
    audience_votes_per_participant: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="3"
    )
    #: 최종 점수에서 심사위원이 차지하는 비율(%). 관객은 나머지다.
    judge_weight_percent: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="70"
    )
    #: 투표를 받고 있는가. 전시가 시작되기 전에 표가 들어오면 안 된다.
    voting_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    status: Mapped[FestivalStatus] = mapped_column(
        Enum(FestivalStatus, name="festival_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=FestivalStatus.PLANNING.value,
    )
    plan_stage: Mapped[PlanStage] = mapped_column(
        Enum(PlanStage, name="plan_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=PlanStage.DRAFT.value,
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    #: 사진 체험은 개인정보 부담이 커서 명시적으로 켜야 한다.
    allow_photo_experience: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # TourAPI 지역 코드 해석 결과. 프로세스 재시작마다 다시 검색하지 않도록 저장한다.
    area_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    sigungu_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_dong_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="festivals")
    plan: Mapped[FestivalPlan | None] = relationship(
        back_populates="festival", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def duration_days(self) -> int:
        """당일 축제 = 1일."""
        return (self.ends_on - self.starts_on).days + 1


class FestivalPlan(Base):
    """기획 상세. 목록 조회를 가볍게 유지하려고 축제 본체에서 분리했다."""

    __tablename__ = "festival_plans"

    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), primary_key=True
    )

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purposes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    target_segments: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    core_audience: Mapped[str | None] = mapped_column(Text, nullable=True)

    staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volunteer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safety_staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: 동시 수용 인원. 있으면 진단의 일일 수용력 2순위 근거가 된다.
    venue_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    planned_performance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    planned_experience: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    planned_food: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    planned_local_shop: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    planned_tour_info: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    planned_etc: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    transit_access: Mapped[str | None] = mapped_column(Text, nullable=True)
    traffic_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    crowd_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    tourism_link_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_commerce_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    lodging_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    festival: Mapped[Festival] = relationship(back_populates="plan")

    @property
    def planned_program_total(self) -> int:
        return (
            self.planned_performance
            + self.planned_experience
            + self.planned_food
            + self.planned_local_shop
            + self.planned_tour_info
            + self.planned_etc
        )

    @property
    def planned_type_count(self) -> int:
        """0보다 큰 프로그램 유형 수. 진단 ③에서 쓴다."""
        return sum(
            1
            for n in (
                self.planned_performance,
                self.planned_experience,
                self.planned_food,
                self.planned_local_shop,
                self.planned_tour_info,
                self.planned_etc,
            )
            if n > 0
        )


class FestivalStaff(Base):
    """축제별 스태프. 접근 코드는 해시만 저장하고 평문은 발급 응답에서 1회만 노출한다."""

    __tablename__ = "festival_staff"
    __table_args__ = (
        CheckConstraint(
            "role = 'booth_manager' OR booth_id IS NULL", name="booth_only_for_booth_manager"
        ),
        Index("ix_festival_staff_festival", "festival_id", postgresql_where="is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, name="staff_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: booth_manager 전용. 이 부스의 미션만 지급할 수 있다.
    booth_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("booths.id", ondelete="SET NULL"), nullable=True
    )
    access_code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
