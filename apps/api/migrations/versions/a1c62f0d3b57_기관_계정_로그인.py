"""기관 계정 로그인

**지금까지 기획자에게는 자격증명이 없었습니다.** 계약(§1)의 로그인은 축제별
스태프용이라 `festival_id` 를 요구하는데, 축제 목록·생성은 축제가 생기기 전에
호출됩니다. 그래서 그 경로들이 `X-Organization-Id` 헤더 폴백에 기대고 있었고,
그 폴백은 **헤더 하나만 바꾸면 남의 기관이 열리는 구멍**입니다.

이 계정은 축제가 아니라 기관에 묶입니다. 축제가 없어도 로그인할 수 있고,
그래야 첫 축제를 만들 수 있습니다.

비밀번호는 bcrypt-sha256 입니다. bcrypt 는 72바이트를 넘는 입력을 조용히 잘라
버리는데, UTF-8 한글은 글자당 3바이트라 24자면 한계에 닿습니다. sha256 으로
먼저 줄이면 길이와 무관하게 44바이트가 되어 잘릴 일이 없습니다.

Revision ID: a1c62f0d3b57
Revises: f8b3d97e1c40
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c62f0d3b57"
down_revision = "f8b3d97e1c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_accounts_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_accounts"),
    )
    # 이메일은 시스템 전체에서 하나. 기관별로 두면 로그인할 때 어느 기관인지 물어야 한다.
    op.create_index(
        "uq_organization_accounts_email", "organization_accounts", ["email"], unique=True
    )
    op.create_index(
        "ix_organization_accounts_org", "organization_accounts", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_organization_accounts_org", table_name="organization_accounts")
    op.drop_index("uq_organization_accounts_email", table_name="organization_accounts")
    op.drop_table("organization_accounts")
