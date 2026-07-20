import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from conftest import bind_engine, migrate_database


EXPECTED_CLASS_HOUR_COUNT = 108
EXPECTED_LESSON_COUNT = 2218 + EXPECTED_CLASS_HOUR_COUNT
EXPECTED_EMPTY_DAY_COUNT = 16


def test_post_import_schedule_requires_authorization(tmp_path):
    app.state.database_url = f"sqlite:///{tmp_path / 'api-noauth.db'}"
    migrate_database(app.state.database_url)
    with TestClient(app) as client:
        payload = Path(__file__).resolve().parents[3] / "7.json"

        response = client.post("/imports/schedule", json=json.loads(payload.read_text(encoding="utf-8")))

        assert response.status_code == 401


def test_post_import_schedule_imports_fixture_into_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        payload = Path(__file__).resolve().parents[3] / "7.json"

        response = client.post(
            "/imports/schedule",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=json.loads(payload.read_text(encoding="utf-8")),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["timetable_count"] == 1
        assert body["group_count"] == 115
        assert body["lesson_count"] == EXPECTED_LESSON_COUNT
        assert body["empty_day_count"] == EXPECTED_EMPTY_DAY_COUNT


def test_post_import_schedule_accepts_uploaded_json_file(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'api-file.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        payload = Path(__file__).resolve().parents[3] / "7.json"

        with payload.open("rb") as file_handle:
            response = client.post(
                "/imports/schedule",
                headers={"Authorization": f"Bearer {operator_token}"},
                files={"file": ("7.json", file_handle, "application/json")},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["timetable_count"] == 1
        assert body["group_count"] == 115
        assert body["lesson_count"] == EXPECTED_LESSON_COUNT
        assert body["empty_day_count"] == EXPECTED_EMPTY_DAY_COUNT


def _bootstrap_and_get_admin_token(database_url: str, monkeypatch) -> str:
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin()
    with TestClient(app) as client:
        return client.post(
            "/auth/login",
            json={"username": "root", "password": "root-password"},
        ).json()["access_token"]


def _bootstrap_and_get_operator_token(database_url: str, monkeypatch) -> str:
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    bind_engine(database_url)
    client = TestClient(app)
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "operator-import",
            "display_name": "Оператор импорта",
            "password": "operator-password",
            "role": "operator",
        },
    )
    return client.post(
        "/auth/login",
        json={"username": "operator-import", "password": "operator-password"},
    ).json()["access_token"]
