"""전시 심사와 관객 투표

작년 행사에서 투표에 스티커를 여러 장 붙이는 일이 있었습니다. 디지털로 옮긴다고
해결되지 않습니다 — 참여 코드를 무제한 발급받을 수 있으면 새로고침이 스티커를
대신합니다. 그래서 이 기능은 학번 신원(e2f7c4b81a35)을 전제로 하고,
`uq_audience_votes_key` 가 1인 1표를 보장합니다.

**심사위원 점수와 관객 투표를 따로 셉니다.** 항목별 점수는 "왜 좋았는지"가 남아
부문 시상의 근거가 되고, 관객 투표는 "얼마나 많이 좋아했는지"를 담습니다.
둘을 한 통에 섞으면 어느 쪽도 설명할 수 없게 됩니다.

`staff_role` 에 `judge` 를 더합니다. 심사위원에게 운영 권한은 주지 않습니다 —
부스를 고치거나 경품을 건드릴 이유가 없고, 그 권한이 붙어 있으면 외부 심사위원에게
계정을 줄 때마다 축제 전체가 열립니다.

Revision ID: f8b3d97e1c40
Revises: e2f7c4b81a35
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f8b3d97e1c40"
down_revision = "e2f7c4b81a35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ 는 트랜잭션 안에서 ADD VALUE 를 허용한다. 같은 트랜잭션에서 그 값을
    # **쓰지만** 않으면 된다 — 여기서는 값만 더한다.
    op.execute("ALTER TYPE staff_role ADD VALUE IF NOT EXISTS 'judge'")

    op.add_column(
        "festivals",
        sa.Column(
            "audience_votes_per_participant",
            sa.SmallInteger(),
            server_default="3",
            nullable=False,
        ),
    )
    op.add_column(
        "festivals",
        sa.Column("judge_weight_percent", sa.SmallInteger(), server_default="70", nullable=False),
    )
    op.add_column(
        "festivals",
        sa.Column("voting_open", sa.Boolean(), server_default="false", nullable=False),
    )

    op.create_table(
        "exhibits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("entry_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("team_name", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("tags", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["festival_id"], ["festivals.id"], name="fk_exhibits_festival_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exhibits"),
        sa.UniqueConstraint("festival_id", "entry_no", name="uq_exhibits_entry_no"),
    )
    op.create_index(
        "ix_exhibits_festival", "exhibits", ["festival_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    # 태그로 거르려면 GIN 이 필요하다.
    op.create_index("ix_exhibits_tags", "exhibits", ["tags"], postgresql_using="gin")

    op.create_table(
        "vote_criteria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("max_score", sa.SmallInteger(), server_default="5", nullable=False),
        sa.Column("weight", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("max_score BETWEEN 1 AND 100", name=op.f("ck_vote_criteria_max_score_range")),
        sa.CheckConstraint("weight > 0", name=op.f("ck_vote_criteria_weight_positive")),
        sa.ForeignKeyConstraint(
            ["festival_id"], ["festivals.id"], name="fk_vote_criteria_festival_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vote_criteria"),
    )
    op.create_index(
        "ix_vote_criteria_festival", "vote_criteria", ["festival_id", "sort_order"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "judge_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exhibit_id", sa.BigInteger(), nullable=False),
        sa.Column("criterion_id", sa.BigInteger(), nullable=False),
        sa.Column("staff_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("score >= 0", name=op.f("ck_judge_scores_score_non_negative")),
        sa.ForeignKeyConstraint(
            ["exhibit_id"], ["exhibits.id"], name="fk_judge_scores_exhibit_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["criterion_id"], ["vote_criteria.id"], name="fk_judge_scores_criterion_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["festival_staff.id"], name="fk_judge_scores_staff_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_judge_scores"),
        # 한 심사위원이 같은 항목에 두 번 점수를 줄 수 없다.
        sa.UniqueConstraint("exhibit_id", "criterion_id", "staff_id", name="uq_judge_scores_key"),
    )
    op.create_index("ix_judge_scores_exhibit", "judge_scores", ["exhibit_id"])
    op.create_index("ix_judge_scores_staff", "judge_scores", ["staff_id"])

    op.create_table(
        "audience_votes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("exhibit_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        sa.Column("voted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["festival_id"], ["festivals.id"], name="fk_audience_votes_festival_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["exhibit_id"], ["exhibits.id"], name="fk_audience_votes_exhibit_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], name="fk_audience_votes_participant_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audience_votes"),
        # 스티커 부정이 재현되는지 갈리는 지점. 조건문이 아니라 여기가 막는다.
        sa.UniqueConstraint("exhibit_id", "participant_id", name="uq_audience_votes_key"),
    )
    op.create_index("ix_audience_votes_festival", "audience_votes", ["festival_id", "participant_id"])
    op.create_index("ix_audience_votes_exhibit", "audience_votes", ["exhibit_id"])


def downgrade() -> None:
    op.drop_index("ix_audience_votes_exhibit", table_name="audience_votes")
    op.drop_index("ix_audience_votes_festival", table_name="audience_votes")
    op.drop_table("audience_votes")
    op.drop_index("ix_judge_scores_staff", table_name="judge_scores")
    op.drop_index("ix_judge_scores_exhibit", table_name="judge_scores")
    op.drop_table("judge_scores")
    op.drop_index("ix_vote_criteria_festival", table_name="vote_criteria")
    op.drop_table("vote_criteria")
    op.drop_index("ix_exhibits_tags", table_name="exhibits")
    op.drop_index("ix_exhibits_festival", table_name="exhibits")
    op.drop_table("exhibits")
    op.drop_column("festivals", "voting_open")
    op.drop_column("festivals", "judge_weight_percent")
    op.drop_column("festivals", "audience_votes_per_participant")
    # staff_role 의 'judge' 는 되돌리지 않는다. Postgres 는 enum 값 삭제를
    # 지원하지 않으며, 타입을 다시 만들려면 참조하는 모든 컬럼을 건드려야 한다.
