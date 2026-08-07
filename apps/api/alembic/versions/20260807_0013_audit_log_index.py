"""audit_log index on created_at

The change-history endpoint sorts every page by created_at DESC, so without
this index each request sorts the whole table.

Revision ID: 20260807_0013
Revises: 20260714_0012
Create Date: 2026-08-07
"""

revision = "20260807_0013"
down_revision = "20260714_0012"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
