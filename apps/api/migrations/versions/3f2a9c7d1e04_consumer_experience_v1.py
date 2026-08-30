"""consumer experience v1

Revision ID: 3f2a9c7d1e04
Revises: a6f0f11c3f14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f2a9c7d1e04"
down_revision: str | Sequence[str] | None = "a6f0f11c3f14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "missions", sa.Column("estimated_duration_minutes", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "missions",
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(
        "estimated_duration_range",
        "missions",
        "estimated_duration_minutes IS NULL OR estimated_duration_minutes BETWEEN 1 AND 1440",
    )

    op.add_column("lecture_sessions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "lecture_sessions",
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.add_column(
        "exhibits", sa.Column("estimated_duration_minutes", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "exhibits",
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(
        "estimated_duration_range",
        "exhibits",
        "estimated_duration_minutes IS NULL OR estimated_duration_minutes BETWEEN 1 AND 1440",
    )

    op.create_table(
        "experience_opens",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("source_context", sa.String(length=32), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_type IN ('mission', 'lecture', 'exhibit')",
            name="source_type_valid",
        ),
        sa.CheckConstraint("source_id > 0", name="source_id_positive"),
        sa.CheckConstraint(
            "source_context IN ('now', 'featured', 'explore_time', 'explore_place', "
            "'explore_type', 'search', 'shared_link', 'flow')",
            name="source_context_valid",
        ),
        sa.ForeignKeyConstraint(
            ["festival_id"], ["festivals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experience_opens_source_time",
        "experience_opens",
        ["festival_id", "source_type", "source_id", "opened_at"],
    )
    op.create_index(
        "ix_experience_opens_participant_time",
        "experience_opens",
        ["participant_id", "opened_at"],
    )

    op.create_table(
        "favorite_memories",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_type IN ('mission', 'lecture', 'exhibit')",
            name="source_type_valid",
        ),
        sa.CheckConstraint("source_id > 0", name="source_id_positive"),
        sa.ForeignKeyConstraint(
            ["festival_id"], ["festivals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "festival_id", "participant_id", name="uq_favorite_memories_participant"
        ),
    )
    op.create_index(
        "ix_favorite_memories_source",
        "favorite_memories",
        ["festival_id", "source_type", "source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_favorite_memories_source", table_name="favorite_memories")
    op.drop_table("favorite_memories")
    op.drop_index("ix_experience_opens_participant_time", table_name="experience_opens")
    op.drop_index("ix_experience_opens_source_time", table_name="experience_opens")
    op.drop_table("experience_opens")

    op.drop_constraint("estimated_duration_range", "exhibits", type_="check")
    op.drop_column("exhibits", "is_featured")
    op.drop_column("exhibits", "estimated_duration_minutes")
    op.drop_column("lecture_sessions", "is_featured")
    op.drop_column("lecture_sessions", "summary")
    op.drop_constraint("estimated_duration_range", "missions", type_="check")
    op.drop_column("missions", "is_featured")
    op.drop_column("missions", "estimated_duration_minutes")
