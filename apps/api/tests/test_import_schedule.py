from pathlib import Path
import sqlite3

from app.services.import_schedule.service import import_schedule_from_json
from conftest import migrate_database


def test_import_schedule_from_fixture_persists_groups_and_lessons(tmp_path):
    source = Path(__file__).resolve().parents[3] / "7.json"
    db_path = tmp_path / "schedule.db"
    database_url = f"sqlite:///{db_path}"
    migrate_database(database_url)

    result = import_schedule_from_json(source, database_url=database_url)

    assert result.timetable_count == 1
    assert result.group_count == 115
    assert result.lesson_count == 2218
    assert result.empty_day_count == 16

    conn = sqlite3.connect(db_path)
    try:
        groups = conn.execute("select count(*) from groups").fetchone()[0]
        lessons = conn.execute("select count(*) from lessons").fetchone()[0]
        imports = conn.execute("select count(*) from schedule_imports").fetchone()[0]
    finally:
        conn.close()

    assert groups == 115
    assert lessons == 2218
    assert imports == 1
