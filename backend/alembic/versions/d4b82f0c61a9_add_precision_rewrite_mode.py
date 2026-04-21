"""add frontend enum values

Revision ID: d4b82f0c61a9
Revises: acf845ceed0f
Create Date: 2026-04-17 20:32:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4b82f0c61a9"
down_revision: Union[str, Sequence[str], None] = "acf845ceed0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE rewrite_mode ADD VALUE IF NOT EXISTS 'PRECISION'")
    op.execute("ALTER TYPE rewrite_mode_variant ADD VALUE IF NOT EXISTS 'PRECISION'")
    op.execute("ALTER TYPE library_category ADD VALUE IF NOT EXISTS 'SCIENCE'")
    op.execute("ALTER TYPE library_category ADD VALUE IF NOT EXISTS 'SOCIAL'")
    op.execute("ALTER TYPE library_category ADD VALUE IF NOT EXISTS 'OTHER'")
    op.alter_column("rewrite_tasks", "project_id", nullable=True)


def downgrade() -> None:
    # PostgreSQL cannot drop enum values without recreating the type.
    pass
