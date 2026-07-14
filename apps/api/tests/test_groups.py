from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_json
from conftest import migrate_database


def test_operator_can_list_rename_and_delete_group(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'groups.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        list_response = client.get("/groups", headers={"Authorization": f"Bearer {operator_token}"})

        assert list_response.status_code == 200
        groups = list_response.json()
        target = next(group for group in groups if group["name"] == "ИС-18")
        assert target["lesson_count"] > 0
        assert target["homeroom_teacher_id"] is None

        rename_response = client.patch(
            f"/groups/{target['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "ИС-18А"},
        )

        assert rename_response.status_code == 200
        assert rename_response.json()["name"] == "ИС-18А"

        delete_response = client.delete(f"/groups/{target['id']}", headers={"Authorization": f"Bearer {operator_token}"})

        assert delete_response.status_code == 204
        updated_groups = client.get("/groups", headers={"Authorization": f"Bearer {operator_token}"}).json()
        assert all(group["id"] != target["id"] for group in updated_groups)

        db_path = database_url.removeprefix("sqlite:///")
        conn = sqlite3.connect(db_path)
        try:
            remaining_lessons = conn.execute("select count(*) from lessons where group_id = ?", (target["id"],)).fetchone()[0]
        finally:
            conn.close()
        assert remaining_lessons == 0


def test_operator_can_assign_homeroom_teacher_to_class_hours(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'group_homeroom.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        groups = client.get("/groups", headers={"Authorization": f"Bearer {operator_token}"}).json()
        target = next(group for group in groups if group["name"] == "ИС-18")
        teachers = client.get("/teachers", headers={"Authorization": f"Bearer {operator_token}"}).json()
        teacher = next(item for item in teachers if item["name"] and item["teacher_id"])

        response = client.patch(
            f"/groups/{target['id']}/homeroom-teacher",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"teacher_id": teacher["id"]},
        )

        assert response.status_code == 200
        updated_group = response.json()
        assert updated_group["homeroom_teacher_id"] == teacher["id"]
        assert updated_group["homeroom_teacher_name"] == teacher["name"]

        schedule_response = client.get(
            "/schedule/lessons",
            headers={"Authorization": f"Bearer {operator_token}"},
            params={"date": "2026-02-23", "time_slot": 4},
        )

        assert schedule_response.status_code == 200
        class_hour_row = next(
            row
            for row in schedule_response.json()
            if row["lesson"] and row["lesson"]["group_name"] == "ИС-18" and row["lesson"]["subject"] == "Классный час"
        )
        assert class_hour_row["lesson"]["teacher_name"] == teacher["name"]

        clear_response = client.patch(
            f"/groups/{target['id']}/homeroom-teacher",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"teacher_id": None},
        )

        assert clear_response.status_code == 200
        assert clear_response.json()["homeroom_teacher_id"] is None


def test_duplicate_group_name_is_rejected(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'group_duplicate.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        groups = client.get("/groups", headers={"Authorization": f"Bearer {operator_token}"}).json()
        target = next(group for group in groups if group["name"] == "ИС-18")

        response = client.patch(
            f"/groups/{target['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "ИС-19"},
        )

        assert response.status_code == 409


def _seed_import(database_url: str) -> None:
    source = Path(__file__).resolve().parents[3] / "7.json"
    import_schedule_from_json(source)


def _bootstrap_and_get_operator_token(database_url: str, monkeypatch) -> str:
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin()
    with TestClient(app) as client:
        admin_token = client.post(
            "/auth/login",
            json={"username": "root", "password": "root-password"},
        ).json()["access_token"]
        client.post(
            "/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "username": "operator-groups",
                "display_name": "Оператор групп",
                "password": "operator-password",
                "role": "operator",
            },
        )
        return client.post(
            "/auth/login",
            json={"username": "operator-groups", "password": "operator-password"},
        ).json()["access_token"]
