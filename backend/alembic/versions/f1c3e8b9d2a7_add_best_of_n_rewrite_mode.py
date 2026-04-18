"""add best_of_n rewrite mode

Revision ID: f1c3e8b9d2a7
Revises: e4f9a2b8c1d3
Create Date: 2026-04-18 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f1c3e8b9d2a7"
down_revision: Union[str, Sequence[str], None] = "e4f9a2b8c1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE rewrite_mode ADD VALUE IF NOT EXISTS 'BEST_OF_N'")
    op.execute("ALTER TYPE rewrite_mode_variant ADD VALUE IF NOT EXISTS 'BEST_OF_N'")


def downgrade() -> None:
    pass
