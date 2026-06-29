"""lesson indexes on teacher_id, room_id, lesson_date

Revision ID: 20260629_0011
Revises: 20260610_0010
Create Date: 2026-06-29
"""

revision = "20260629_0011"
down_revision = "20260610_0010"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.create_index("ix_lessons_teacher_id", "lessons", ["teacher_id"])
    op.create_index("ix_lessons_room_id", "lessons", ["room_id"])
    op.create_index("ix_lessons_lesson_date", "lessons", ["lesson_date"])


def downgrade() -> None:
    op.drop_index("ix_lessons_lesson_date", table_name="lessons")
    op.drop_index("ix_lessons_room_id", table_name="lessons")
    op.drop_index("ix_lessons_teacher_id", table_name="lessons")
