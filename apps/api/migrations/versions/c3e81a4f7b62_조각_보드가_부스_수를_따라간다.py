"""조각 보드가 부스 수를 따라간다 (stamp_boards.grid_auto)

조각 수는 부스 수에서 나온다. 그런데 지금까지는 운영자가 기획 단계에서 한 번
골라 두면 그 값이 굳었고, 부스를 더 만들어도 보드는 그대로였다. 그러면 부스가
늘어난 만큼 조각을 못 받는 부스가 생기거나, 뒤늦게 격자를 바꾸다가 이미 모은
조각을 날린다.

`grid_auto` 가 참이면 부스(또는 미션)를 만들고 지울 때마다 서버가 격자를 다시
맞춘다. 운영자가 직접 고른 순간 거짓이 되어 그 선택을 지킨다.

기본값은 참이다. 이미 있는 보드도 참으로 열어 두는데, 자동 맞춤은 **아직 아무도
조각을 모으지 않았을 때만** 동작하므로 진행 중인 축제를 건드리지 않는다.

Revision ID: c3e81a4f7b62
Revises: a6f0f11c3f14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e81a4f7b62"
down_revision = "a6f0f11c3f14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stamp_boards",
        sa.Column("grid_auto", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("stamp_boards", "grid_auto")
