from pathlib import Path
import sqlite3

from app.services.import_schedule.service import import_schedule_from_json, import_schedule_from_payload
from conftest import migrate_database


EXPECTED_CLASS_HOUR_COUNT = 108
EXPECTED_LESSON_COUNT = 2218 + EXPECTED_CLASS_HOUR_COUNT
EXPECTED_EMPTY_DAY_COUNT = 16


def test_import_schedule_from_fixture_persists_groups_and_lessons(tmp_path):
    source = Path(__file__).resolve().parents[3] / "7.json"
    db_path = tmp_path / "schedule.db"
    database_url = f"sqlite:///{db_path}"
    migrate_database(database_url)

    result = import_schedule_from_json(source, database_url=database_url)

    assert result.timetable_count == 1
    assert result.group_count == 115
    assert result.lesson_count == EXPECTED_LESSON_COUNT
    assert result.empty_day_count == EXPECTED_EMPTY_DAY_COUNT

    conn = sqlite3.connect(db_path)
    try:
        groups = conn.execute("select count(*) from groups").fetchone()[0]
        lessons = conn.execute("select count(*) from lessons").fetchone()[0]
        imports = conn.execute("select count(*) from schedule_imports").fetchone()[0]
        class_hours = conn.execute(
            """
            select count(*)
            from lessons
            join subjects on subjects.id = lessons.subject_id
            where lessons.weekday = 1
              and lessons.time_slot = 4
              and subjects.source_name = 'Классный час'
            """
        ).fetchone()[0]
        shifted_lesson = conn.execute(
            """
            select lessons.time_slot, lessons.start_time, lessons.end_time
            from lessons
            where lessons.source_lesson_id = '22_10_14'
            """
        ).fetchone()
        class_hour_for_group = conn.execute(
            """
            select lessons.time_slot, lessons.start_time, lessons.end_time, lessons.room_id
            from lessons
            join groups on groups.id = lessons.group_id
            join subjects on subjects.id = lessons.subject_id
            where groups.source_name = 'ИС-18'
              and lessons.lesson_date = '2026-02-23'
              and subjects.source_name = 'Классный час'
            """
        ).fetchone()
    finally:
        conn.close()

    assert groups == 115
    assert lessons == EXPECTED_LESSON_COUNT
    assert imports == 1
    assert class_hours == EXPECTED_CLASS_HOUR_COUNT
    assert shifted_lesson == (5, "15:00:00.000000", "16:30:00.000000")
    assert class_hour_for_group == (4, "13:10:00.000000", "14:40:00.000000", None)


def test_import_does_not_create_class_hour_for_empty_monday(tmp_path):
    db_path = tmp_path / "empty-monday.db"
    database_url = f"sqlite:///{db_path}"
    migrate_database(database_url)
    payload = {
        "timetable": [
            {
                "date_start": "23-02-2026",
                "week_number": 7,
                "groups": [
                    {
                        "group_name": "EMPTY-MONDAY",
                        "course": 1,
                        "faculty": "",
                        "days": [
                            {
                                "weekday": 1,
                                "lessons": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    result = import_schedule_from_payload(payload, database_url=database_url)

    conn = sqlite3.connect(db_path)
    try:
        lessons = conn.execute("select count(*) from lessons").fetchone()[0]
        class_hours = conn.execute(
            """
            select count(*)
            from lessons
            join subjects on subjects.id = lessons.subject_id
            where subjects.source_name = 'Классный час'
            """
        ).fetchone()[0]
    finally:
        conn.close()

    assert result.lesson_count == 0
    assert result.empty_day_count == 1
    assert lessons == 0
    assert class_hours == 0
