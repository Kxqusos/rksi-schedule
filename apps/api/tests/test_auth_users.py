from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_admin
from conftest import migrate_database


def test_bootstrap_admin_can_login_and_create_user_with_display_name_and_password(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'auth_users.db'}"
    migrate_database(database_url)
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin(database_url)
    client = TestClient(app)

    login_response = client.post(
        "/auth/login",
        json={"username": "root", "password": "root-password"},
    )

    assert login_response.status_code == 200
    logged_in = login_response.json()
    assert logged_in["user"]["username"] == "root"
    assert logged_in["user"]["display_name"] == "Root Admin"
    assert logged_in["user"]["role"] == "admin"

    token = logged_in["access_token"]
    create_response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "operator-1",
            "display_name": "Оператор расписания",
            "password": "operator-password",
            "role": "operator",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "operator-1"
    assert created["display_name"] == "Оператор расписания"
    assert created["role"] == "operator"
    assert "password" not in created
    assert "password_hash" not in created

    operator_login = client.post(
        "/auth/login",
        json={"username": "operator-1", "password": "operator-password"},
    )

    assert operator_login.status_code == 200
    assert operator_login.json()["user"]["role"] == "operator"


def test_operator_token_cannot_create_users(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'operator_forbidden.db'}"
    migrate_database(database_url)
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
    operator_token = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "operator-2",
            "display_name": "Operator Two",
            "password": "operator-password",
            "role": "operator",
        },
    ).json()

    login_response = client.post(
        "/auth/login",
        json={"username": operator_token["username"], "password": "operator-password"},
    )
    token = login_response.json()["access_token"]
    forbidden_response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "operator-3",
            "display_name": "Operator Three",
            "password": "operator-password",
            "role": "operator",
        },
    )

    assert forbidden_response.status_code == 403


def test_wrong_password_is_rejected(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'wrong_password.db'}"
    migrate_database(database_url)
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Root Admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-password")
    app.state.database_url = database_url
    bootstrap_admin(database_url)
    client = TestClient(app)

    response = client.post("/auth/login", json={"username": "root", "password": "wrong"})

    assert response.status_code == 401


def test_admin_can_view_credentials_and_revoke_user(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'revoke.db'}"
    migrate_database(database_url)
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
            "username": "operator-4",
            "display_name": "Operator Four",
            "password": "operator-password",
            "role": "operator",
        },
    )

    user_id = create_response.json()["id"]

    credentials_response = client.get(
        f"/users/{user_id}/credentials",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert credentials_response.status_code == 200
    credentials = credentials_response.json()
    assert credentials["username"] == "operator-4"
    assert credentials["display_name"] == "Operator Four"
    assert credentials["role"] == "operator"
    assert credentials["is_active"] is True
    assert "password" not in credentials
    assert "password_hash" not in credentials

    revoke_response = client.post(
        f"/users/{user_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json()["is_active"] is False

    revoked_login = client.post(
        "/auth/login",
        json={"username": "operator-4", "password": "operator-password"},
    )
    assert revoked_login.status_code == 401

    session_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert session_response.status_code == 200


def test_admin_can_change_user_password(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'change_password.db'}"
    migrate_database(database_url)
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
            "username": "operator-5",
            "display_name": "Operator Five",
            "password": "old-password",
            "role": "operator",
        },
    )
    user_id = create_response.json()["id"]

    update_response = client.post(
        f"/users/{user_id}/password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"password": "new-password"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["username"] == "operator-5"
    assert "password" not in update_response.json()
    assert "password_hash" not in update_response.json()

    old_login = client.post(
        "/auth/login",
        json={"username": "operator-5", "password": "old-password"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"username": "operator-5", "password": "new-password"},
    )
    assert new_login.status_code == 200


def test_operator_cannot_change_user_password(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'change_password_forbidden.db'}"
    migrate_database(database_url)
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
            "username": "operator-6",
            "display_name": "Operator Six",
            "password": "old-password",
            "role": "operator",
        },
    )
    user_id = create_response.json()["id"]
    operator_token = client.post(
        "/auth/login",
        json={"username": "operator-6", "password": "old-password"},
    ).json()["access_token"]

    update_response = client.post(
        f"/users/{user_id}/password",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"password": "new-password"},
    )

    assert update_response.status_code == 403
