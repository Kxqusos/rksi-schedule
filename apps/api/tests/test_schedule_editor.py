from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_json
from conftest import migrate_database


def test_operator_can_create_update_and_delete_lesson(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'editor.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    app.state.database_url = database_url
    client = TestClient(app)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)

    create_response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "БД-11",
            "course": 1,
            "faculty": "",
            "subject": "Алгебра",
            "teacher_name": "Иванова А.А.",
            "teacher_id": "90001",
            "teacher_post": "",
            "room_name": "12/1",
            "date": "2026-02-28",
            "time_start": "14:00:00",
            "time_end": "15:30:00",
            "weekday": 6,
            "week_number": 7,
            "time_slot": 4,
            "subgroup": 0,
            "lesson_type": "",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["subject"] == "Алгебра"
    lesson_id = created["id"]

    update_response = client.patch(
        f"/schedule/lessons/{lesson_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"subject": "Геометрия"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["subject"] == "Геометрия"

    delete_response = client.delete(
        f"/schedule/lessons/{lesson_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert delete_response.status_code == 204

    conn = sqlite3.connect(database_url.removeprefix("sqlite:///"))
    try:
        audit_count = conn.execute("select count(*) from audit_log").fetchone()[0]
        remaining = conn.execute("select count(*) from lessons where id = ?", (lesson_id,)).fetchone()[0]
    finally:
        conn.close()

    assert audit_count >= 3
    assert remaining == 0


def test_request_without_role_is_rejected(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'forbidden.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.patch(
        "/schedule/lessons/1",
        json={"subject": "Геометрия"},
    )

    assert response.status_code == 401


def test_conflicting_update_is_rejected(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'conflict.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.patch(
        "/schedule/lessons/2",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"time_slot": 1, "time_start": "08:00:00", "time_end": "09:30:00"},
    )

    assert response.status_code == 409


def _seed_import(database_url: str) -> None:
    source = Path(__file__).resolve().parents[3] / "7.json"
    import_schedule_from_json(source, database_url=database_url)


def _bootstrap_and_get_operator_token(database_url: str, monkeypatch) -> str:
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin(database_url)
    client = TestClient(app)
    admin_token = client.post(
        "/auth/login",
        json={"username": "root", "password": "root-password"},
    ).json()["access_token"]
    create_response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "operator-1",
            "display_name": "Оператор 1",
            "password": "operator-password",
            "role": "operator",
        },
    )
    if create_response.status_code != 201:
        create_response = client.post(
            "/auth/login",
            json={"username": "operator-1", "password": "operator-password"},
        )
        return create_response.json()["access_token"]

    login_response = client.post(
        "/auth/login",
        json={"username": "operator-1", "password": "operator-password"},
    )
    return login_response.json()["access_token"]
