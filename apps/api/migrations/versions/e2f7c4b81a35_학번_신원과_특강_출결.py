"""학번 신원과 특강 출결

교내 행사(SW Week)를 주관하려면 두 가지가 필요합니다.

**1. 신원** — 익명 참여 코드는 무제한 발급됩니다. 1인 1표를 강제하려면 "이 사람이
아까 그 사람"임을 알아야 하는데, 익명으로는 알 수 없어 종이 스티커를 여러 장
붙이던 행위가 새로고침 여러 번으로 바뀔 뿐입니다.

`festivals.identity_mode` 로 축제마다 고릅니다. 기본값은 `anonymous` 라 기존
관광 축제는 그대로 돕니다. `student_id` 면 학번을 받고, 부분 유니크 인덱스가
1 학번 = 1 참여자를 보장합니다.

학번은 **해시가 아니라 평문**입니다. 공결이 걸린 특강은 학교에 낼 출석 명단이
필요한데, 해시만 두면 그 명단을 만들 수 없어 기능이 죽습니다. 대신 스키마 계층에서
노출 경계를 좁힙니다 — 참여자 응답에는 나가지 않습니다.

**2. 출결** — 입장 스캔 한 번은 출튀를 막지 못합니다. 예고 없는 시점에 여러 번
확인합니다. 운영자가 체크인을 열면 그 순간부터 짧게 열리고, 그 안에 회전 QR 을
찍은 사람만 기록됩니다.

Revision ID: e2f7c4b81a35
Revises: d4a91b6ec27f
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2f7c4b81a35"
down_revision = "d4a91b6ec27f"
branch_labels = None
depends_on = None

IDENTITY_MODE = sa.Enum("anonymous", "student_id", name="identity_mode")


def upgrade() -> None:
    # ── 신원 ──
    IDENTITY_MODE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "festivals",
        sa.Column("identity_mode", IDENTITY_MODE, server_default="anonymous", nullable=False),
    )
    op.add_column("participants", sa.Column("student_no", sa.Text(), nullable=True))
    # 1 학번 = 1 참여자. 부정 방지의 뿌리이므로 애플리케이션이 아니라 여기가 막는다.
    op.create_index(
        "uq_participants_student_no",
        "participants",
        ["festival_id", "student_no"],
        unique=True,
        postgresql_where=sa.text("student_no IS NOT NULL"),
    )

    # ── 특강 ──
    op.create_table(
        "lecture_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("festival_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("speaker", sa.String(length=120), nullable=True),
        sa.Column("affiliation", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("required_checkins", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column(
            "grants_excused_absence", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "qr_secret",
            sa.LargeBinary(),
            server_default=sa.text("gen_random_bytes(32)"),
            nullable=False,
        ),
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
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_lecture_sessions_period_valid")),
        sa.CheckConstraint(
            "required_checkins >= 1", name=op.f("ck_lecture_sessions_required_positive")
        ),
        sa.ForeignKeyConstraint(
            ["festival_id"],
            ["festivals.id"],
            name="fk_lecture_sessions_festival_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lecture_sessions"),
    )
    op.create_index(
        "ix_lecture_sessions_festival",
        "lecture_sessions",
        ["festival_id", "starts_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "session_checkpoints",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "opens_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_by_staff_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("closes_at > opens_at", name=op.f("ck_session_checkpoints_window_valid")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["lecture_sessions.id"],
            name="fk_session_checkpoints_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_staff_id"],
            ["festival_staff.id"],
            name="fk_session_checkpoints_opened_by_staff_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_checkpoints"),
    )
    op.create_index(
        "ix_session_checkpoints_session", "session_checkpoints", ["session_id", "opens_at"]
    )

    op.create_table(
        "session_attendances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["lecture_sessions.id"],
            name="fk_session_attendances_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["session_checkpoints.id"],
            name="fk_session_attendances_checkpoint_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name="fk_session_attendances_participant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_attendances"),
        sa.UniqueConstraint(
            "checkpoint_id", "participant_id", name="uq_session_attendances_key"
        ),
    )
    op.create_index(
        "ix_session_attendances_session",
        "session_attendances",
        ["session_id", "participant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_attendances_session", table_name="session_attendances")
    op.drop_table("session_attendances")
    op.drop_index("ix_session_checkpoints_session", table_name="session_checkpoints")
    op.drop_table("session_checkpoints")
    op.drop_index("ix_lecture_sessions_festival", table_name="lecture_sessions")
    op.drop_table("lecture_sessions")
    op.drop_index("uq_participants_student_no", table_name="participants")
    op.drop_column("participants", "student_no")
    op.drop_column("festivals", "identity_mode")
    IDENTITY_MODE.drop(op.get_bind(), checkfirst=True)
