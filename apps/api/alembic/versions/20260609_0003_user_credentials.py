"""user credentials

Revision ID: 20260609_0003
Revises: 20260609_0002
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260609_0003"
down_revision = "20260609_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=150), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=False, server_default=""),
    )
    op.execute("UPDATE users SET display_name = username WHERE display_name = ''")


def downgrade() -> None:
    op.drop_column("users", "password_hash")
    op.drop_column("users", "display_name")
