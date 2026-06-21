"""normalize monday class hour

Revision ID: 20260610_0008
Revises: 20260610_0007
Create Date: 2026-06-10
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from alembic import op
import sqlalchemy as sa

revision = "20260610_0008"
down_revision = "20260610_0007"
branch_labels = None
depends_on = None

CLASS_HOUR_SUBJECT = "Классный час"
CLASS_HOUR_SLOT = 4
MONDAY_WEEKDAY = 1
CLASS_HOUR_START = "13:10:00"
CLASS_HOUR_END = "14:40:00"
SHIFTED_SLOT_TIMES = {
    5: ("15:00:00", "16:30:00"),
    6: ("16:40:00", "18:10:00"),
    7: ("18:20:00", "19:50:00"),
}

lessons_table = sa.table(
    "lessons",
    sa.column("source_lesson_id", sa.String()),
    sa.column("schedule_import_id", sa.Integer()),
    sa.column("group_id", sa.Integer()),
    sa.column("subject_id", sa.Integer()),
    sa.column("teacher_id", sa.Integer()),
    sa.column("room_id", sa.Integer()),
    sa.column("lesson_date", sa.Date()),
    sa.column("start_time", sa.Time()),
    sa.column("end_time", sa.Time()),
    sa.column("weekday", sa.Integer()),
    sa.column("week_number", sa.Integer()),
    sa.column("time_slot", sa.Integer()),
    sa.column("subgroup", sa.Integer()),
    sa.column("lesson_type", sa.String()),
    sa.column("raw_payload", sa.JSON()),
)


def upgrade() -> None:
    bind = op.get_bind()
    subject_id = _ensure_class_hour_subject(bind)
    if _class_hours_exist(bind, subject_id):
        return

    _shift_existing_monday_lessons(bind, subject_id)
    _insert_class_hours(bind, subject_id)


def downgrade() -> None:
    bind = op.get_bind()
    subject_id = bind.execute(
        sa.text("select id from subjects where source_name = :subject"),
        {"subject": CLASS_HOUR_SUBJECT},
    ).scalar()
    if subject_id is None:
        return

    bind.execute(sa.text("delete from lessons where subject_id = :subject_id"), {"subject_id": subject_id})

    for old_slot, new_slot in ((7, 6), (6, 5), (5, 4)):
        start_time, end_time = _slot_time(new_slot)
        bind.execute(
            sa.text(
                """
                update lessons
                set time_slot = :new_slot,
                    start_time = :start_time,
                    end_time = :end_time
                where weekday = :weekday
                  and time_slot = :old_slot
                """
            ),
            {
                "old_slot": old_slot,
                "new_slot": new_slot,
                "start_time": start_time,
                "end_time": end_time,
                "weekday": MONDAY_WEEKDAY,
            },
        )


def _ensure_class_hour_subject(bind) -> int:
    subject_id = bind.execute(
        sa.text("select id from subjects where source_name = :subject"),
        {"subject": CLASS_HOUR_SUBJECT},
    ).scalar()
    if subject_id is not None:
        return int(subject_id)

    bind.execute(sa.text("insert into subjects (source_name) values (:subject)"), {"subject": CLASS_HOUR_SUBJECT})
    return int(
        bind.execute(
            sa.text("select id from subjects where source_name = :subject"),
            {"subject": CLASS_HOUR_SUBJECT},
        ).scalar_one()
    )


def _class_hours_exist(bind, subject_id: int) -> bool:
    count = bind.execute(
        sa.text("select count(*) from lessons where subject_id = :subject_id"),
        {"subject_id": subject_id},
    ).scalar_one()
    return int(count) > 0


def _shift_existing_monday_lessons(bind, subject_id: int) -> None:
    bind.execute(
        sa.text(
            """
            update lessons
            set time_slot = time_slot + 10
            where weekday = :weekday
              and time_slot >= :class_hour_slot
              and subject_id != :subject_id
            """
        ),
        {"weekday": MONDAY_WEEKDAY, "class_hour_slot": CLASS_HOUR_SLOT, "subject_id": subject_id},
    )

    for temporary_slot, normalized_slot in ((14, 5), (15, 6), (16, 7)):
        start_time, end_time = SHIFTED_SLOT_TIMES[normalized_slot]
        bind.execute(
            sa.text(
                """
                update lessons
                set time_slot = :normalized_slot,
                    start_time = :start_time,
                    end_time = :end_time
                where weekday = :weekday
                  and time_slot = :temporary_slot
                """
            ),
            {
                "temporary_slot": temporary_slot,
                "normalized_slot": normalized_slot,
                "start_time": start_time,
                "end_time": end_time,
                "weekday": MONDAY_WEEKDAY,
            },
        )


def _insert_class_hours(bind, subject_id: int) -> None:
    groups = dict(bind.execute(sa.text("select source_name, id from groups")).all())
    existing_sources = {
        str(source_id)
        for source_id in bind.execute(sa.text("select source_lesson_id from lessons where subject_id = :subject_id"), {"subject_id": subject_id})
    }

    rows = []
    for import_id, raw_payload in bind.execute(sa.text("select id, raw_payload from schedule_imports order by id")):
        for timetable in _iter_timetables(raw_payload):
            for group_payload in timetable.get("groups", []):
                group_name = str(group_payload.get("group_name", "")).strip()
                group_id = groups.get(group_name)
                if group_id is None:
                    continue
                for day_payload in group_payload.get("days", []):
                    if int(day_payload.get("weekday", 0) or 0) != MONDAY_WEEKDAY:
                        continue
                    lessons = day_payload.get("lessons") or []
                    if not lessons:
                        continue
                    first_lesson = lessons[0] if lessons else {}
                    lesson_date = str(first_lesson.get("date") or timetable.get("date_start", "")).strip()
                    if not lesson_date:
                        continue
                    source_lesson_id = f"class-hour:{lesson_date}:{group_name}"
                    if source_lesson_id in existing_sources:
                        continue
                    existing_sources.add(source_lesson_id)
                    rows.append(
                        {
                            "source_lesson_id": source_lesson_id,
                            "schedule_import_id": import_id,
                            "group_id": group_id,
                            "subject_id": subject_id,
                            "teacher_id": None,
                            "room_id": None,
                            "lesson_date": datetime.strptime(lesson_date, "%d-%m-%Y").date(),
                            "start_time": datetime.strptime(CLASS_HOUR_START, "%H:%M:%S").time(),
                            "end_time": datetime.strptime(CLASS_HOUR_END, "%H:%M:%S").time(),
                            "weekday": MONDAY_WEEKDAY,
                            "week_number": int(first_lesson.get("week") or timetable.get("week_number", 0) or 0),
                            "time_slot": CLASS_HOUR_SLOT,
                            "subgroup": 0,
                            "lesson_type": CLASS_HOUR_SUBJECT,
                            "raw_payload": {
                                "subject": CLASS_HOUR_SUBJECT,
                                "type": CLASS_HOUR_SUBJECT,
                                "subgroup": 0,
                                "time_start": "13:10",
                                "time_end": "14:40",
                                "time": CLASS_HOUR_SLOT,
                                "week": int(first_lesson.get("week") or timetable.get("week_number", 0) or 0),
                                "date": lesson_date,
                                "teachers": [],
                                "auditories": [],
                                "Lesson_ID_Num": source_lesson_id,
                            },
                        }
                    )

    if rows:
        op.bulk_insert(lessons_table, rows)


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


def _slot_time(slot: int) -> tuple[str, str]:
    if slot == 4:
        return CLASS_HOUR_START, CLASS_HOUR_END
    return SHIFTED_SLOT_TIMES[slot]
