import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_initial_migration_creates_schedule_import_tables(tmp_path):
    db_path = tmp_path / "migration.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table' order by name"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "alembic_version",
        "audit_log",
        "groups",
        "lessons",
        "roles",
        "rooms",
        "schedule_imports",
        "subjects",
        "teachers",
        "users",
    }.issubset(tables)
