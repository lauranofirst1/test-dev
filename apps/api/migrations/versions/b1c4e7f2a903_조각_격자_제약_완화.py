"""조각 격자 제약 완화 — 부스 수에 맞춰 쪼갤 수 있게

조각 수를 4·6·9 세 가지로 묶어두면 부스가 8개인 축제는 9조각(아무도 완성 못 함)
이나 6조각(부스 2개가 조각 없이 남음) 중 하나를 골라야 합니다. 격자를 2~5 로
넓혀 4·6·8·9·10·12·15·16·20·25 를 만들 수 있게 합니다.

기존 (2,2)·(2,3)·(3,3) 데이터는 새 범위 안에 있으므로 그대로 유효합니다.

Revision ID: b1c4e7f2a903
Revises: 0e89b871c6a2
"""

from __future__ import annotations

from alembic import op

revision = "b1c4e7f2a903"
down_revision = "0e89b871c6a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("grid_supported", "stamp_boards", type_="check")
    op.drop_constraint("rows_range", "stamp_boards", type_="check")
    op.drop_constraint("cols_range", "stamp_boards", type_="check")
    op.create_check_constraint("rows_range", "stamp_boards", "rows BETWEEN 2 AND 5")
    op.create_check_constraint("cols_range", "stamp_boards", "cols BETWEEN 2 AND 5")


def downgrade() -> None:
    # 되돌리기 전에 범위를 벗어난 보드를 정리해야 한다 — 조용히 실패하지 않도록
    # 제약을 다시 걸기만 하고, 위반 행이 있으면 마이그레이션이 실패하게 둔다.
    op.drop_constraint("rows_range", "stamp_boards", type_="check")
    op.drop_constraint("cols_range", "stamp_boards", type_="check")
    op.create_check_constraint("rows_range", "stamp_boards", "rows BETWEEN 2 AND 3")
    op.create_check_constraint("cols_range", "stamp_boards", "cols BETWEEN 2 AND 3")
    op.create_check_constraint(
        "grid_supported", "stamp_boards", "(rows, cols) IN ((2,2),(2,3),(3,3))"
    )
