from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_json
from conftest import migrate_database


def test_admin_can_create_list_and_delete_teacher(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'teachers.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    create_response = client.post(
        "/teachers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Тестовый Преподаватель", "teacher_id": "teacher-999", "post": "преподаватель"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Тестовый Преподаватель"
    assert created["teacher_id"] == "teacher-999"
    assert created["lesson_count"] == 0

    list_response = client.get("/teachers", headers={"Authorization": f"Bearer {admin_token}"})
    assert list_response.status_code == 200
    assert any(teacher["id"] == created["id"] for teacher in list_response.json())

    delete_response = client.delete(f"/teachers/{created['id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert delete_response.status_code == 204

    updated_list_response = client.get("/teachers", headers={"Authorization": f"Bearer {admin_token}"})
    assert updated_list_response.status_code == 200
    assert all(teacher["id"] != created["id"] for teacher in updated_list_response.json())


def test_duplicate_teacher_identifier_is_rejected(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'duplicate_teacher.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    teachers = client.get("/teachers", headers={"Authorization": f"Bearer {admin_token}"}).json()
    existing_teacher = next(teacher for teacher in teachers if teacher["teacher_id"])

    response = client.post(
        "/teachers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Дубликат", "teacher_id": existing_teacher["teacher_id"], "post": ""},
    )

    assert response.status_code == 409


def test_teacher_with_lessons_can_be_deleted_without_deleting_lessons(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'busy_teacher.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    teachers = client.get("/teachers", headers={"Authorization": f"Bearer {admin_token}"}).json()
    occupied_teacher = next(teacher for teacher in teachers if teacher["lesson_count"] > 0)

    response = client.delete(
        f"/teachers/{occupied_teacher['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 204

    updated_teachers = client.get("/teachers", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert all(teacher["id"] != occupied_teacher["id"] for teacher in updated_teachers)

    conn = sqlite3.connect(database_url.removeprefix("sqlite:///"))
    try:
        unassigned_count = conn.execute(
            "select count(*) from lessons where teacher_id is null"
        ).fetchone()[0]
        deleted_teacher_lesson_count = conn.execute(
            "select count(*) from lessons where teacher_id = ?",
            (occupied_teacher["id"],),
        ).fetchone()[0]
    finally:
        conn.close()

    assert unassigned_count >= occupied_teacher["lesson_count"]
    assert deleted_teacher_lesson_count == 0


def test_operator_can_manage_teachers(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'operator_teachers.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.post(
        "/teachers",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"name": "Операторский преподаватель", "teacher_id": "operator-teacher", "post": ""},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Операторский преподаватель"

    delete_response = client.delete(
        f"/teachers/{created['id']}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert delete_response.status_code == 204


def _seed_import(database_url: str) -> None:
    source = Path(__file__).resolve().parents[3] / "7.json"
    import_schedule_from_json(source, database_url=database_url)


def _bootstrap_and_get_admin_token(database_url: str, monkeypatch) -> str:
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin(database_url)
    client = TestClient(app)
    return client.post(
        "/auth/login",
        json={"username": "root", "password": "root-password"},
    ).json()["access_token"]


def _bootstrap_and_get_operator_token(database_url: str, monkeypatch) -> str:
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    client = TestClient(app)
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "operator-teachers",
            "display_name": "Оператор преподавателей",
            "password": "operator-password",
            "role": "operator",
        },
    )
    return client.post(
        "/auth/login",
        json={"username": "operator-teachers", "password": "operator-password"},
    ).json()["access_token"]
