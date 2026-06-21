"""group homeroom teacher

Revision ID: 20260610_0009
Revises: 20260610_0008
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260610_0009"
down_revision = "20260610_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.add_column(sa.Column("homeroom_teacher_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_groups_homeroom_teacher_id_teachers",
            "teachers",
            ["homeroom_teacher_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_constraint("fk_groups_homeroom_teacher_id_teachers", type_="foreignkey")
        batch_op.drop_column("homeroom_teacher_id")
