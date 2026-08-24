"""경품 · 뽑기 — 조각 보드를 완성한 참여자가 한 번 돌린다.

**왜 포인트가 아니라 경품인가.** 설계 문서(05 §3)는 룰렛 뽑기를 v2 로 미뤘고
이유를 "보너스 포인트 산정이 보상 캠페인과 겹쳐 정책 정리가 먼저 필요"라고
적었습니다. `participations` 에는 `bonus_points` 와 `reward_campaign_id` 가
각각 하나뿐이라, 뽑기가 포인트를 주면 같은 지급에 캠페인이 겹칠 때 무엇이
이기는지를 스키마가 표현하지 못합니다.

경품은 그 충돌을 아예 만들지 않습니다. 뽑기는 미션 지급 경로를 건드리지 않고,
참여 이력·포인트 집계·중복 지급 방지가 지금 정의 그대로 남습니다.

**뽑기는 완성의 보상입니다.** 부스를 다 돌아 그림을 완성한 참여자만,
축제당 **정확히 한 번** 돌립니다. 유일성은 애플리케이션 조건문이 아니라
`uq_prize_draws_participant` 가 보장합니다 — 버튼 두 번 누름과 동시 요청은
조건문으로 막히지 않습니다.
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
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import ArchivableMixin, Base, TimestampMixin


class Prize(Base, TimestampMixin, ArchivableMixin):
    """뽑기 상품 한 종류.

    `stock` 이 NULL 이면 무제한입니다 — "꽝"이 여기 해당합니다. 꽝을 재고 있는
    상품으로 두면 소진된 순간 아무도 뽑을 수 없는 상태가 되므로, 무제한을
    표현할 수 있어야 합니다.

    `weight` 는 상대 가중치입니다. 확률(%)로 받지 않는 이유는 합이 100 이
    되도록 운영자가 맞춰야 하고, 상품 하나를 중지하면 나머지 합이 100 이
    아니게 되기 때문입니다. 가중치는 그때그때 남은 후보들로 정규화됩니다.
    """

    __tablename__ = "prizes"
    __table_args__ = (
        CheckConstraint("weight > 0", name="weight_positive"),
        CheckConstraint("stock IS NULL OR stock >= 0", name="stock_non_negative"),
        Index("ix_prizes_festival", "festival_id", postgresql_where="archived_at IS NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: NULL = 무제한. 꽝과 "선착순 아님" 상품에 쓴다.
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: 상대 가중치. 남은 후보들 사이에서 정규화된다.
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    #: true = 이 상품이 곧 "꽝". 당첨 화면 문구와 수령 확인 여부가 달라진다.
    is_blank: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class PrizeDraw(Base):
    """뽑기 1회 기록. 참여자당 축제당 한 건.

    `prize_id` 는 지급 시점 스냅샷이 아니라 참조입니다. 상품명이 바뀌면 과거
    당첨자의 화면도 바뀌는데, 경품은 실물을 받아가는 것이라 **현재 이름이
    맞는 이름**입니다. 포인트 스냅샷과 성격이 다릅니다.
    """

    __tablename__ = "prize_draws"
    __table_args__ = (
        # 축제당 1인 1회. 조건문으로 막으면 동시 요청에 그대로 뚫린다.
        UniqueConstraint("festival_id", "participant_id", name="uq_prize_draws_participant"),
        Index("ix_prize_draws_festival_time", "festival_id", "drawn_at"),
        Index("ix_prize_draws_prize", "prize_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL = 뽑을 수 있는 상품이 하나도 없었다(전부 소진·중지). 꽝과 다르다 —
    #: 꽝은 운영자가 의도한 결과이고, 이쪽은 운영 실수다. 구분해서 기록한다.
    prize_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("prizes.id", ondelete="SET NULL"), nullable=True
    )
    drawn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 수령 ──
    #: 스태프가 실물을 건네고 찍는다. 참여자가 스스로 찍을 수 없다.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="SET NULL"), nullable=True
    )
