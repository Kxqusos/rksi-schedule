from fastapi.testclient import TestClient

from app.main import app
from conftest import migrate_database


def test_admin_can_create_and_list_users(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'users.db'}"
    migrate_database(database_url)
    app.state.database_url = database_url
    client = TestClient(app)

    create_response = client.post(
        "/users",
        headers={"X-Role": "admin", "X-Actor": "root"},
        json={"username": "operator-1", "role": "operator"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "operator-1"
    assert created["role"] == "operator"
    assert created["id"] > 0

    list_response = client.get("/users", headers={"X-Role": "admin", "X-Actor": "root"})

    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_operator_cannot_create_users(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'operator_forbidden.db'}"
    migrate_database(database_url)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.post(
        "/users",
        headers={"X-Role": "operator", "X-Actor": "operator-1"},
        json={"username": "operator-2", "role": "operator"},
    )

    assert response.status_code == 403


def test_duplicate_username_is_rejected(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'duplicate_users.db'}"
    migrate_database(database_url)
    app.state.database_url = database_url
    client = TestClient(app)

    payload = {"username": "admin-2", "role": "admin"}
    first_response = client.post("/users", headers={"X-Role": "admin"}, json=payload)
    second_response = client.post("/users", headers={"X-Role": "admin"}, json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
