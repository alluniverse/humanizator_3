"""add missing tables

Revision ID: acf845ceed0f
Revises: a4a055acb0de
Create Date: 2026-04-17 11:41:22.335925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'acf845ceed0f'
down_revision: Union[str, Sequence[str], None] = 'a4a055acb0de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: all tables were already created in migration a4a055acb0de (init).
    # This revision exists only to advance the alembic_version chain.
    pass


def downgrade() -> None:
    pass
