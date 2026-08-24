"""퀴즈 시도 기록과 경품 뽑기

부스 QR 체험(계약 §11)과 조각 완성 보상 뽑기를 위한 세 테이블입니다.

**mission_attempts** — 계약은 오답이 참여 이력을 만들지 않는다고 못박습니다.
그러면 시도 횟수를 둘 곳이 없어지고 `max_attempts` 는 클라이언트 말이 됩니다.
집계에 섞이지 않는 별도 테이블에 시도만 셉니다.

**prizes / prize_draws** — 뽑기는 포인트가 아니라 경품을 줍니다. 포인트로 주면
`participations` 의 `bonus_points`·`reward_campaign_id` 가 각각 하나뿐이라
보상 캠페인과 겹칠 때 무엇이 이기는지를 스키마가 표현하지 못합니다.
경품은 그 충돌을 만들지 않습니다.

`uq_prize_draws_participant` 가 1인 1회의 진실입니다 — 애플리케이션 조건문은
동시 요청에서 뚫립니다.

Revision ID: c7d5a1e93f42
Revises: b1c4e7f2a903
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d5a1e93f42"
down_revision = "b1c4e7f2a903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        sa.Column("mission_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "attempt_count", sa.SmallInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_mission_attempts_attempt_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name="fk_mission_attempts_mission_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_mission_attempts_participant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mission_attempts"),
        sa.UniqueConstraint(
            "participant_id", "mission_id", name="uq_mission_attempts_key"
        ),
    )

    op.create_table(
        "prizes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        # NULL = 무제한. 꽝과 "선착순 아님" 상품이 여기 해당한다.
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_blank", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("weight > 0", name=op.f("ck_prizes_weight_positive")),
        sa.CheckConstraint(
            "stock IS NULL OR stock >= 0", name=op.f("ck_prizes_stock_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["festival_id"],
            ["festivals.id"],
            name="fk_prizes_festival_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prizes"),
    )
    op.create_index(
        "ix_prizes_festival",
        "prizes",
        ["festival_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "prize_draws",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        # NULL = 뽑을 수 있는 상품이 없었다. 꽝(prizes.is_blank)과 다르다.
        sa.Column("prize_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "drawn_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by_staff_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["festival_id"],
            ["festivals.id"],
            name="fk_prize_draws_festival_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_prize_draws_participant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prize_id"], ["prizes.id"], name="fk_prize_draws_prize_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["claimed_by_staff_id"],
            ["festival_staff.id"],
            name="fk_prize_draws_claimed_by_staff_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prize_draws"),
        # 1인 1회의 진실. 조건문이 아니라 여기가 막는다.
        sa.UniqueConstraint(
            "festival_id", "participant_id", name="uq_prize_draws_participant"
        ),
    )
    op.create_index(
        "ix_prize_draws_festival_time", "prize_draws", ["festival_id", "drawn_at"]
    )
    op.create_index("ix_prize_draws_prize", "prize_draws", ["prize_id"])


def downgrade() -> None:
    op.drop_index("ix_prize_draws_prize", table_name="prize_draws")
    op.drop_index("ix_prize_draws_festival_time", table_name="prize_draws")
    op.drop_table("prize_draws")
    op.drop_index("ix_prizes_festival", table_name="prizes")
    op.drop_table("prizes")
    op.drop_table("mission_attempts")
