"""remove class hours from empty mondays

Revision ID: 20260610_0010
Revises: 20260610_0009
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa

revision = "20260610_0010"
down_revision = "20260610_0009"
branch_labels = None
depends_on = None

CLASS_HOUR_SUBJECT = "Классный час"
MONDAY_WEEKDAY = 1


def upgrade() -> None:
    bind = op.get_bind()
    subject_id = bind.execute(
        sa.text("select id from subjects where source_name = :subject"),
        {"subject": CLASS_HOUR_SUBJECT},
    ).scalar()
    if subject_id is None:
        return

    empty_class_hour_sources = _empty_monday_class_hour_sources(bind)
    if not empty_class_hour_sources:
        return

    bind.execute(
        sa.text(
            """
            delete from lessons
            where subject_id = :subject_id
              and source_lesson_id in :source_ids
            """
        ).bindparams(sa.bindparam("source_ids", expanding=True)),
        {
            "subject_id": subject_id,
            "source_ids": empty_class_hour_sources,
        },
    )


def downgrade() -> None:
    pass


def _empty_monday_class_hour_sources(bind) -> list[str]:
    sources: list[str] = []
    for _import_id, raw_payload in bind.execute(sa.text("select id, raw_payload from schedule_imports order by id")):
        for timetable in _iter_timetables(raw_payload):
            for group_payload in timetable.get("groups", []):
                group_name = str(group_payload.get("group_name", "")).strip()
                if not group_name:
                    continue
                for day_payload in group_payload.get("days", []):
                    if int(day_payload.get("weekday", 0) or 0) != MONDAY_WEEKDAY:
                        continue
                    lessons = day_payload.get("lessons") or []
                    if lessons:
                        continue
                    lesson_date = str(timetable.get("date_start", "")).strip()
                    if lesson_date:
                        sources.append(f"class-hour:{lesson_date}:{group_name}")
    return list(dict.fromkeys(sources))


def _iter_timetables(raw_payload: Any):
    documents = raw_payload.get("documents") if isinstance(raw_payload, dict) and "documents" in raw_payload else raw_payload
    if isinstance(documents, dict):
        documents = [documents]
    if not isinstance(documents, list):
        return
    for document in documents:
        if not isinstance(document, dict):
            continue
        for timetable in document.get("timetable", []):
            yield timetable
