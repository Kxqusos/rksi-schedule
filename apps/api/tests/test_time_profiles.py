from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from conftest import migrate_database


def test_operator_can_create_update_list_and_delete_day_time_profile(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'day_profiles.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:

        create_response = client.post(
            "/time-profiles/day",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "Обычный день", "slots": _day_slots()},
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "Обычный день"
        assert len(created["slots"]) == 7
        assert created["slots"][0] == {"slot_number": 1, "time_start": "08:00:00", "time_end": "09:30:00"}

        update_response = client.patch(
            f"/time-profiles/day/{created['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "name": "Сокращённый день",
                "slots": _day_slots(first_start="08:30:00", first_end="09:15:00"),
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Сокращённый день"
        assert updated["slots"][0]["time_start"] == "08:30:00"
        assert updated["slots"][0]["time_end"] == "09:15:00"

        list_response = client.get("/time-profiles/day", headers={"Authorization": f"Bearer {operator_token}"})
        assert list_response.status_code == 200
        assert [profile["id"] for profile in list_response.json()] == [created["id"]]

        delete_response = client.delete(
            f"/time-profiles/day/{created['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert delete_response.status_code == 204

        empty_response = client.get("/time-profiles/day", headers={"Authorization": f"Bearer {operator_token}"})
        assert empty_response.status_code == 200
        assert empty_response.json() == []


def test_operator_can_create_update_list_and_delete_week_time_profile(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'week_profiles.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:

        default_day = _create_day_profile(client, operator_token, "Обычный день")
        short_day = _create_day_profile(client, operator_token, "Короткий день")

        create_response = client.post(
            "/time-profiles/week",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "name": "Учебная неделя",
                "days": [{"weekday": weekday, "day_profile_id": default_day["id"]} for weekday in range(1, 8)],
            },
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "Учебная неделя"
        assert len(created["days"]) == 7
        assert created["days"][0]["weekday"] == 1
        assert created["days"][0]["day_profile_name"] == "Обычный день"

        update_response = client.patch(
            f"/time-profiles/week/{created['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "name": "Неделя с короткой субботой",
                "days": [
                    {"weekday": weekday, "day_profile_id": short_day["id"] if weekday == 6 else default_day["id"]}
                    for weekday in range(1, 8)
                ],
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Неделя с короткой субботой"
        saturday = next(day for day in updated["days"] if day["weekday"] == 6)
        assert saturday["day_profile_id"] == short_day["id"]
        assert saturday["day_profile_name"] == "Короткий день"

        list_response = client.get("/time-profiles/week", headers={"Authorization": f"Bearer {operator_token}"})
        assert list_response.status_code == 200
        assert [profile["id"] for profile in list_response.json()] == [created["id"]]

        delete_response = client.delete(
            f"/time-profiles/week/{created['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert delete_response.status_code == 204

        empty_response = client.get("/time-profiles/week", headers={"Authorization": f"Bearer {operator_token}"})
        assert empty_response.status_code == 200
        assert empty_response.json() == []


def test_day_profile_used_by_week_profile_cannot_be_deleted(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'day_profile_in_use.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:

        day_profile = _create_day_profile(client, operator_token, "Используемый день")
        week_response = client.post(
            "/time-profiles/week",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "name": "Неделя",
                "days": [{"weekday": weekday, "day_profile_id": day_profile["id"]} for weekday in range(1, 8)],
            },
        )
        assert week_response.status_code == 201

        delete_response = client.delete(
            f"/time-profiles/day/{day_profile['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert delete_response.status_code == 409
        assert delete_response.json()["detail"] == "day profile is used by week profile"


def test_time_profile_payload_must_contain_seven_unique_slots_and_days(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'profile_validation.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:

        bad_day_response = client.post(
            "/time-profiles/day",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "Неполный день", "slots": _day_slots()[:6]},
        )
        assert bad_day_response.status_code == 422

        day_profile = _create_day_profile(client, operator_token, "Обычный день")
        bad_week_response = client.post(
            "/time-profiles/week",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "name": "Неполная неделя",
                "days": [{"weekday": weekday, "day_profile_id": day_profile["id"]} for weekday in range(1, 7)],
            },
        )
        assert bad_week_response.status_code == 422


def _day_slots(first_start: str = "08:00:00", first_end: str = "09:30:00") -> list[dict]:
    starts = [first_start, "09:40:00", "10:00:00", "11:40:00", "13:20:00", "15:00:00", "16:40:00"]
    ends = [first_end, "11:10:00", "11:30:00", "13:10:00", "14:50:00", "16:30:00", "18:10:00"]
    return [
        {"slot_number": index + 1, "time_start": starts[index], "time_end": ends[index]}
        for index in range(7)
    ]


def _create_day_profile(client: TestClient, token: str, name: str) -> dict:
    response = client.post(
        "/time-profiles/day",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slots": _day_slots()},
    )
    assert response.status_code == 201
    return response.json()


def _bootstrap_and_get_admin_token(database_url: str, monkeypatch) -> str:
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin()
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
            "username": "operator-time-profiles",
            "display_name": "Оператор профилей",
            "password": "operator-password",
            "role": "operator",
        },
    )
    return client.post(
        "/auth/login",
        json={"username": "operator-time-profiles", "password": "operator-password"},
    ).json()["access_token"]
