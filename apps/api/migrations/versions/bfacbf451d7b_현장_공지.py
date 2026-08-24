"""현장 공지 (announcements, announcement_acks)

관객용과 스태프용이 한 테이블에 있고 `channel` 로 갈립니다. 관객용 조회 경로는
이 값을 파라미터로 받지 않고 서버가 고정하므로, 스태프 공지가 관객에게 샐 수
없습니다.

`announcement_acks` 는 긴급 공지를 누가 확인했는지 남깁니다. 브라우저에만 두면
"덮개를 다시 안 씌운다" 는 되지만 운영자는 몇 명이 봤는지 알 수 없고, 우천 중단
공지에서는 그게 전부입니다.

Revision ID: bfacbf451d7b
Revises: 7da5eab7c8c6
Create Date: 2026-08-24 23:28:49.190074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfacbf451d7b'
down_revision: Union[str, Sequence[str], None] = '7da5eab7c8c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('announcements',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('festival_id', sa.BigInteger(), nullable=False),
    sa.Column('channel', sa.Enum('audience', 'staff', 'both', name='announcement_channel'), nullable=False),
    sa.Column('level', sa.Enum('normal', 'urgent', name='announcement_level'), server_default='normal', nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('body', sa.String(length=1000), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_by_staff_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('ends_at IS NULL OR ends_at > starts_at', name=op.f('ck_announcements_window_valid')),
    sa.ForeignKeyConstraint(['created_by_staff_id'], ['festival_staff.id'], name=op.f('fk_announcements_created_by_staff_id'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['festival_id'], ['festivals.id'], name=op.f('fk_announcements_festival_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_announcements'))
    )
    op.create_index('ix_announcements_live', 'announcements', ['festival_id', 'starts_at'], unique=False, postgresql_where='is_active')
    op.create_table('announcement_acks',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('announcement_id', sa.BigInteger(), nullable=False),
    sa.Column('participant_id', sa.BigInteger(), nullable=True),
    sa.Column('staff_id', sa.BigInteger(), nullable=True),
    sa.Column('acked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    # 참여자이거나 스태프이거나, 정확히 하나다.
    sa.CheckConstraint('(participant_id IS NULL) <> (staff_id IS NULL)', name=op.f('ck_announcement_acks_one_identity')),
    sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], name=op.f('fk_announcement_acks_announcement_id'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], name=op.f('fk_announcement_acks_participant_id'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['staff_id'], ['festival_staff.id'], name=op.f('fk_announcement_acks_staff_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_announcement_acks'))
    )
    # 덮개를 연타해도 행은 하나다. 애플리케이션 조건문으로 두면 동시 요청에서 뚫린다.
    op.create_index('uq_announcement_acks_participant', 'announcement_acks', ['announcement_id', 'participant_id'], unique=True, postgresql_where='participant_id IS NOT NULL')
    op.create_index('uq_announcement_acks_staff', 'announcement_acks', ['announcement_id', 'staff_id'], unique=True, postgresql_where='staff_id IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_announcement_acks_staff', table_name='announcement_acks', postgresql_where='staff_id IS NOT NULL')
    op.drop_index('uq_announcement_acks_participant', table_name='announcement_acks', postgresql_where='participant_id IS NOT NULL')
    op.drop_table('announcement_acks')
    op.drop_index('ix_announcements_live', table_name='announcements', postgresql_where='is_active')
    op.drop_table('announcements')
