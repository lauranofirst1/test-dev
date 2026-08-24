"""비밀번호 재설정 표

**평문 토큰을 저장하지 않습니다.** 저장하는 것은 sha256 해시뿐이고 평문은 메일로
나간 링크에만 있습니다. DB 가 유출돼도 그 표로는 아무 계정도 열 수 없습니다.

bcrypt 가 아니라 sha256 인 이유는 서버가 만든 32바이트 난수라 전수 대입이 애초에
불가능하기 때문입니다 — 느린 해시는 저엔트로피 값(6자리 코드·비밀번호)에만
필요합니다.

Revision ID: b93e5a17c8d2
Revises: a1c62f0d3b57
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b93e5a17c8d2"
down_revision = "a1c62f0d3b57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["organization_accounts.id"],
            name="fk_password_reset_tokens_account_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
    )
    op.create_index(
        "uq_password_reset_tokens_hash", "password_reset_tokens", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_password_reset_tokens_account", "password_reset_tokens", ["account_id", "expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_account", table_name="password_reset_tokens")
    op.drop_index("uq_password_reset_tokens_hash", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
