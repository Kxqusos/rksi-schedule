"""room exclusions

Revision ID: 20260610_0006
Revises: 20260610_0005
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260610_0006"
down_revision = "20260610_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("rooms", sa.Column("exclusion_reason", sa.String(length=300), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("rooms", "exclusion_reason")
    op.drop_column("rooms", "is_excluded")
