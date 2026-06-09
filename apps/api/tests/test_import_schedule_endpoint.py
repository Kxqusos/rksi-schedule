import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_post_import_schedule_imports_fixture_into_database(tmp_path):
    app.state.database_url = f"sqlite:///{tmp_path / 'api.db'}"
    client = TestClient(app)
    payload = Path(__file__).resolve().parents[3] / "7.json"

    response = client.post("/imports/schedule", json=json.loads(payload.read_text(encoding="utf-8")))

    assert response.status_code == 200
    body = response.json()
    assert body["timetable_count"] == 1
    assert body["group_count"] == 115
    assert body["lesson_count"] == 2218
    assert body["empty_day_count"] == 16


def test_post_import_schedule_accepts_uploaded_json_file(tmp_path):
    app.state.database_url = f"sqlite:///{tmp_path / 'api-file.db'}"
    client = TestClient(app)
    payload = Path(__file__).resolve().parents[3] / "7.json"

    with payload.open("rb") as file_handle:
        response = client.post(
            "/imports/schedule",
            files={"file": ("7.json", file_handle, "application/json")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["timetable_count"] == 1
    assert body["group_count"] == 115
    assert body["lesson_count"] == 2218
    assert body["empty_day_count"] == 16
