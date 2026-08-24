"""전시 작품 · 심사 항목 · 심사위원 점수 · 관객 투표.

작년 행사에서 **투표에 스티커를 여러 장 붙이는 일**이 있었습니다. 디지털로
옮긴다고 해결되지 않습니다 — 참여 코드를 무제한 발급받을 수 있으면 새로고침이
스티커를 대신합니다. 그래서 이 기능은 `identity_mode = student_id` 를 전제로 하고,
유니크 제약이 1인 1표를 보장합니다.

**심사위원 점수와 관객 투표는 따로 셉니다.** 항목별 점수는 "왜 좋았는지"가 남아
부문 시상의 근거가 되고, 관객 투표는 "얼마나 많이 좋아했는지"를 담습니다.
둘을 한 통에 섞으면 어느 쪽도 설명할 수 없게 됩니다.
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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import ArchivableMixin, Base, TimestampMixin


class Exhibit(Base, TimestampMixin, ArchivableMixin):
    """전시 작품 한 점."""

    __tablename__ = "exhibits"
    __table_args__ = (
        UniqueConstraint("festival_id", "entry_no", name="uq_exhibits_entry_no"),
        Index("ix_exhibits_festival", "festival_id", postgresql_where="archived_at IS NULL"),
        # 태그로 거르려면 GIN 이 필요하다. 작품이 수십 점이면 없어도 돌지만,
        # 나중에 붙이면 그때는 이미 목록 화면이 느리다.
        Index("ix_exhibits_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    #: 관객이 부르는 번호. "7번 작품" 으로 이야기한다.
    entry_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: 제출한 포스터 이미지. 조각 보드 그림과 같은 저장 경로를 쓴다.
    poster_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: 자유 태그. 부문(전공/창업/기초/융합연계)과 기술 키워드가 섞인다.
    #: 별도 테이블로 정규화하지 않는 이유는 태그가 축제마다 통째로 달라지고
    #: 집계 대상이 아니기 때문이다 — 거르기에만 쓴다.
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    #: 전시 구역. 관객이 실물을 찾아갈 때 쓴다.
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class VoteCriterion(Base, TimestampMixin, ArchivableMixin):
    """심사 항목 — 창의성 · 완성도 · 실용성처럼 무엇을 보고 점수를 주는가."""

    __tablename__ = "vote_criteria"
    __table_args__ = (
        CheckConstraint("max_score BETWEEN 1 AND 100", name="max_score_range"),
        CheckConstraint("weight > 0", name="weight_positive"),
        Index(
            "ix_vote_criteria_festival",
            "festival_id",
            "sort_order",
            postgresql_where="archived_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )

    label: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: 이 항목의 만점. 5점 척도가 기본.
    max_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    #: 항목 간 상대 가중치. 확률과 같은 이유로 %가 아니라 가중치다 —
    #: 항목 하나를 빼면 합이 100 이 아니게 된다.
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class JudgeScore(Base):
    """심사위원 한 명이 작품 하나의 항목 하나에 준 점수."""

    __tablename__ = "judge_scores"
    __table_args__ = (
        # 한 심사위원이 같은 항목에 두 번 점수를 줄 수 없다. 고치는 것은
        # 새 행이 아니라 이 행의 갱신이다.
        UniqueConstraint(
            "exhibit_id", "criterion_id", "staff_id", name="uq_judge_scores_key"
        ),
        CheckConstraint("score >= 0", name="score_non_negative"),
        Index("ix_judge_scores_exhibit", "exhibit_id"),
        Index("ix_judge_scores_staff", "staff_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exhibit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exhibits.id", ondelete="CASCADE"), nullable=False
    )
    criterion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vote_criteria.id", ondelete="CASCADE"), nullable=False
    )
    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festival_staff.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AudienceVote(Base):
    """관객 한 명이 작품 하나에 준 표.

    **여기가 스티커 부정이 재현되는지 갈리는 지점입니다.** 유니크 제약이 같은
    참여자의 두 번째 표를 막고, 참여자가 학번에 묶여 있어야(§신원) 그 제약이
    의미를 갖습니다. 익명 축제에서는 코드를 새로 받으면 그만이라 이 제약이
    아무것도 막지 못합니다.
    """

    __tablename__ = "audience_votes"
    __table_args__ = (
        UniqueConstraint("exhibit_id", "participant_id", name="uq_audience_votes_key"),
        Index("ix_audience_votes_festival", "festival_id", "participant_id"),
        Index("ix_audience_votes_exhibit", "exhibit_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    festival_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("festivals.id", ondelete="CASCADE"), nullable=False
    )
    exhibit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exhibits.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
