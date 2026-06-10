"""teacher absences

Revision ID: 20260610_0005
Revises: 20260609_0004
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260610_0005"
down_revision = "20260609_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teacher_absences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("absence_date", sa.Date(), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("time_slot_start", sa.Integer(), nullable=False),
        sa.Column("time_slot_end", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
    )
    op.create_index(
        "ix_teacher_absences_teacher_date",
        "teacher_absences",
        ["teacher_id", "absence_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_absences_teacher_date", table_name="teacher_absences")
    op.drop_table("teacher_absences")
