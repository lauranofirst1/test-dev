"""성과 목표 — 기획 STEP 3 에서 세우고 사후 리포트가 채점한다. 데이터모델 §14."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base

#: 기본 제공 지표. 이 목록에 없는 키는 `custom:` 접두어를 붙인 사용자 정의다.
#:
#: `is_measurable` 을 값이 아니라 **키로부터** 정하는 이유는, 측정 가능 여부가
#: 운영자의 선택이 아니기 때문이다. 목표 방문객에 체크 하나로 달성률을 켤 수
#: 있게 두면 반드시 켜지고, 그 순간 QR 참여자 수가 방문객 수로 둔갑한다.
BUILTIN_METRICS: dict[str, tuple[str, str, bool]] = {
    # metric_key: (라벨, 단위, 측정 가능한가)
    "expected_visitors": ("목표 방문객", "명", False),
    "qr_participants": ("목표 QR 참여자", "명", True),
    "total_completions": ("목표 미션 완료", "건", True),
    "completions_per_participant": ("목표 참여자당 완료", "건", True),
    "satisfaction": ("목표 만족도", "점", True),
}


class KpiTarget(Base):
    """지표 하나의 목표값.

    `is_measurable=False` 인 지표는 리포트가 달성률을 계산하지 않고 참고값으로만
    표시합니다. FestaFlow 는 방문객을 세지 않으므로 목표 방문객이 여기 해당합니다 —
    측정하지 않은 값에 달성률을 붙이면 리포트 전체의 신뢰가 무너집니다.
    """

    __tablename__ = "kpi_targets"
    __table_args__ = (
        UniqueConstraint("festival_id", "metric_key", name="uq_kpi_targets_key"),
        CheckConstraint("target_value >= 0", name="target_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    #: `qr_participants` 같은 기본 키 또는 `custom:재방문의향` 형식.
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default="건")
    is_measurable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
