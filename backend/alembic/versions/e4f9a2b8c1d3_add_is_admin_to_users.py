"""add is_admin to users

Revision ID: e4f9a2b8c1d3
Revises: d4b82f0c61a9
Create Date: 2026-04-17 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4f9a2b8c1d3"
down_revision: Union[str, Sequence[str], None] = "d4b82f0c61a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    # Set admin@admin.com as admin
    op.execute("UPDATE users SET is_admin = true WHERE email = 'admin@admin.com'")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
