"""drop raw_payload from schedule_imports and lessons

Revision ID: 20260714_0012
Revises: 20260629_0011
Create Date: 2026-07-14

Both raw_payload columns duplicated data already normalised into dedicated
columns (see backend-layering §8): schedule_imports.raw_payload stored the
whole 1.3 MB import file (never read back), lessons.raw_payload copied fields
that are all parsed into typed columns. Classification now relies solely on
lesson_type + Subject.source_name.

IRREVERSIBLE: downgrade re-adds the columns as empty/nullable — the original
JSON payloads are gone and cannot be restored (same caveat as 0010).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0012"
down_revision = "20260629_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lessons") as batch_op:
        batch_op.drop_column("raw_payload")
    with op.batch_alter_table("schedule_imports") as batch_op:
        batch_op.drop_column("raw_payload")


def downgrade() -> None:
    # Columns are re-created nullable; original payloads are not recoverable.
    with op.batch_alter_table("schedule_imports") as batch_op:
        batch_op.add_column(sa.Column("raw_payload", sa.JSON(), nullable=True))
    with op.batch_alter_table("lessons") as batch_op:
        batch_op.add_column(sa.Column("raw_payload", sa.JSON(), nullable=True))
