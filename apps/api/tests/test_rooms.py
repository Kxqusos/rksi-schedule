from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_json
from conftest import migrate_database


def test_admin_can_create_list_and_delete_room(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'rooms.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        create_response = client.post(
            "/rooms",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "999/3"},
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "999/3"
        assert created["building"] == "Корпус 3"

        list_response = client.get("/rooms", headers={"Authorization": f"Bearer {admin_token}"})
        assert list_response.status_code == 200
        assert any(room["id"] == created["id"] for room in list_response.json())

        delete_response = client.delete(f"/rooms/{created['id']}", headers={"Authorization": f"Bearer {admin_token}"})
        assert delete_response.status_code == 204

        updated_list_response = client.get("/rooms", headers={"Authorization": f"Bearer {admin_token}"})
        assert updated_list_response.status_code == 200
        assert all(room["id"] != created["id"] for room in updated_list_response.json())


def test_duplicate_room_name_is_rejected(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'duplicate_room.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        response = client.post(
            "/rooms",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "103/1"},
        )

        assert response.status_code == 409


def test_room_with_lessons_can_be_deleted_without_deleting_lessons(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'busy_room.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        rooms = client.get("/rooms", headers={"Authorization": f"Bearer {admin_token}"}).json()
        occupied_room = next(room for room in rooms if room["lesson_count"] > 0)

        response = client.delete(
            f"/rooms/{occupied_room['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 204

        updated_rooms = client.get("/rooms", headers={"Authorization": f"Bearer {admin_token}"}).json()
        assert all(room["id"] != occupied_room["id"] for room in updated_rooms)

        schedule_response = client.get(
            "/schedule/lessons",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"date": "2026-02-23", "time_slot": 1},
        )
        assert schedule_response.status_code == 200
        assert any(
            row["room_name"] == "Без кабинета" and row["lesson"] is not None
            for row in schedule_response.json()
        )


def test_operator_can_manage_rooms(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'operator_rooms.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        response = client.post(
            "/rooms",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "998/3"},
        )

        assert response.status_code == 201
        created = response.json()
        assert created["name"] == "998/3"

        delete_response = client.delete(
            f"/rooms/{created['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert delete_response.status_code == 204


def test_operator_can_exclude_and_restore_room(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'exclude_room.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        rooms = client.get("/rooms", headers={"Authorization": f"Bearer {operator_token}"}).json()
        room = next(room for room in rooms if room["name"] == "103/1")

        exclude_response = client.post(
            f"/rooms/{room['id']}/exclusion",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"reason": "Ремонт"},
        )

        assert exclude_response.status_code == 200
        excluded = exclude_response.json()
        assert excluded["is_excluded"] is True
        assert excluded["exclusion_reason"] == "Ремонт"

        restore_response = client.delete(
            f"/rooms/{room['id']}/exclusion",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert restore_response.status_code == 200
        restored = restore_response.json()
        assert restored["is_excluded"] is False
        assert restored["exclusion_reason"] == ""


def _seed_import(database_url: str) -> None:
    source = Path(__file__).resolve().parents[3] / "7.json"
    import_schedule_from_json(source)


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
    with TestClient(app) as client:
        client.post(
            "/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "username": "operator-rooms",
                "display_name": "Оператор кабинетов",
                "password": "operator-password",
                "role": "operator",
            },
        )
        return client.post(
            "/auth/login",
            json={"username": "operator-rooms", "password": "operator-password"},
        ).json()["access_token"]
