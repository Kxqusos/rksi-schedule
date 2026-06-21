"""time profiles

Revision ID: 20260610_0007
Revises: 20260610_0006
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260610_0007"
down_revision = "20260610_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "day_time_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", name="uq_day_time_profiles_name"),
    )
    op.create_table(
        "day_time_profile_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_profile_id", sa.Integer(), nullable=False),
        sa.Column("slot_number", sa.Integer(), nullable=False),
        sa.Column("time_start", sa.Time(), nullable=False),
        sa.Column("time_end", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(["day_profile_id"], ["day_time_profiles.id"]),
        sa.UniqueConstraint("day_profile_id", "slot_number", name="uq_day_time_profile_slots_profile_slot"),
    )
    op.create_table(
        "week_time_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", name="uq_week_time_profiles_name"),
    )
    op.create_table(
        "week_time_profile_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_profile_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("day_profile_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["week_profile_id"], ["week_time_profiles.id"]),
        sa.ForeignKeyConstraint(["day_profile_id"], ["day_time_profiles.id"]),
        sa.UniqueConstraint("week_profile_id", "weekday", name="uq_week_time_profile_days_profile_weekday"),
    )


def downgrade() -> None:
    op.drop_table("week_time_profile_days")
    op.drop_table("week_time_profiles")
    op.drop_table("day_time_profile_slots")
    op.drop_table("day_time_profiles")
