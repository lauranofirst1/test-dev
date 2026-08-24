"""성과 목표 (kpi_targets)

기획 STEP 3 에서 세운 목표를 사후 리포트가 채점합니다.
`is_measurable=false` 인 지표는 달성률을 계산하지 않습니다 —
FestaFlow 가 세지 않는 방문객에 달성률을 붙이면 QR 참여자 수가 방문객 수로
둔갑하고, 리포트 전체의 신뢰가 무너집니다.

Revision ID: 7da5eab7c8c6
Revises: b93e5a17c8d2
Create Date: 2026-08-24 23:04:35.317683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7da5eab7c8c6'
down_revision: Union[str, Sequence[str], None] = 'b93e5a17c8d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('kpi_targets',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('festival_id', sa.BigInteger(), nullable=False),
    sa.Column('metric_key', sa.Text(), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('target_value', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('unit', sa.Text(), server_default='건', nullable=False),
    sa.Column('is_measurable', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint('target_value >= 0', name=op.f('ck_kpi_targets_target_non_negative')),
    sa.ForeignKeyConstraint(['festival_id'], ['festivals.id'], name=op.f('fk_kpi_targets_festival_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kpi_targets')),
    # 같은 지표를 두 번 세우면 리포트에 같은 줄이 두 개 뜬다.
    sa.UniqueConstraint('festival_id', 'metric_key', name='uq_kpi_targets_key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('kpi_targets')
