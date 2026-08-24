"""재전송 키를 축제 단위로 (uq_participations_client_request)

`client_request_id` 는 오프라인 큐가 만들어 보내는 재전송 키입니다. 유니크
제약이 전역이면 두 가지가 깨집니다.

1. 다른 축제가 같은 키를 쓰면 INSERT 가 막혀 500 이 됩니다. 500 은 큐가
   **재시도하는** 응답이라 그 항목 하나가 큐 앞에서 영원히 돕니다.
2. 조회에 스코프가 없으면 남의 축제 지급 기록이 `was_already_granted: true` 와
   함께 포인트·미션·부스·완료 시각까지 실려 돌아갑니다.

재전송은 언제나 같은 축제로 갑니다(URL 에 축제가 있습니다). 이 값은 클라이언트가
만들어 보내는 값이라 우연에만 기대면 안 됩니다.

Revision ID: a6f0f11c3f14
Revises: bfacbf451d7b
Create Date: 2026-08-25 00:36:21.478874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6f0f11c3f14'
down_revision: Union[str, Sequence[str], None] = 'bfacbf451d7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('uq_participations_client_request'), table_name='participations', postgresql_where='(client_request_id IS NOT NULL)')
    op.create_index('uq_participations_client_request', 'participations', ['festival_id', 'client_request_id'], unique=True, postgresql_where='client_request_id IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_participations_client_request', table_name='participations', postgresql_where='client_request_id IS NOT NULL')
    op.create_index(op.f('uq_participations_client_request'), 'participations', ['client_request_id'], unique=True, postgresql_where='(client_request_id IS NOT NULL)')
