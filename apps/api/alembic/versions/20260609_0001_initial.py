"""initial schedule import schema

Revision ID: 20260609_0001
Revises:
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260609_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("timetable_count", sa.Integer(), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.Column("lesson_count", sa.Integer(), nullable=False),
        sa.Column("empty_day_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("course", sa.Integer(), nullable=False),
        sa.Column("faculty", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("source_name", name="uq_groups_source_name"),
    )
    op.create_table(
        "teachers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_teacher_id", sa.String(length=100), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("post", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("source_teacher_id", name="uq_teachers_source_teacher_id"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("source_name", name="uq_rooms_source_name"),
    )
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=250), nullable=False),
        sa.UniqueConstraint("source_name", name="uq_subjects_source_name"),
    )
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_lesson_id", sa.String(length=100), nullable=False),
        sa.Column("schedule_import_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("lesson_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("time_slot", sa.Integer(), nullable=False),
        sa.Column("subgroup", sa.Integer(), nullable=False),
        sa.Column("lesson_type", sa.String(length=50), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_import_id"], ["schedule_imports.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.UniqueConstraint("source_lesson_id", name="uq_lessons_source_lesson_id"),
    )


def downgrade() -> None:
    op.drop_table("lessons")
    op.drop_table("subjects")
    op.drop_table("rooms")
    op.drop_table("teachers")
    op.drop_table("groups")
    op.drop_table("schedule_imports")

