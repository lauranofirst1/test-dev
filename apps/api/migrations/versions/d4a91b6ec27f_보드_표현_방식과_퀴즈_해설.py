"""보드 표현 방식과 퀴즈 해설

**stamp_boards.board_style** — 진행 보드를 격자 퍼즐로 볼지 스탬프 랠리 지도로 볼지.
구조가 아니라 표현입니다. 타일 수도 배정도 공개 기록도 달라지지 않으므로, 이 값을
바꿔도 참여자의 수집 진행은 초기화되지 않습니다(rows/cols/reveal_mode/grant_unit 과
다른 점이 여기입니다).

퀴즈 해설은 `missions.experience_config` 안의 `explanation` 키라 컬럼이 없습니다.

Revision ID: d4a91b6ec27f
Revises: c7d5a1e93f42
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4a91b6ec27f"
down_revision = "c7d5a1e93f42"
branch_labels = None
depends_on = None

BOARD_STYLE = sa.Enum("grid", "trail", name="board_style")


def upgrade() -> None:
    BOARD_STYLE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "stamp_boards",
        sa.Column("board_style", BOARD_STYLE, server_default="grid", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("stamp_boards", "board_style")
    BOARD_STYLE.drop(op.get_bind(), checkfirst=True)
