from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import AuditLog
from app.services.audit.mappers import build_summary
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_json
from conftest import migrate_database


def test_change_history_requires_authentication(tmp_path):
    app.state.database_url = f"sqlite:///{tmp_path / 'audit-noauth.db'}"
    migrate_database(app.state.database_url)
    with TestClient(app) as client:
        assert client.get("/audit").status_code == 401


def test_operator_sees_own_change_with_display_name(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-operator.db'}"
    migrate_database(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        client.post("/rooms", headers=_auth(operator_token), json={"name": "901/3"})

        body = client.get("/audit", headers=_auth(operator_token)).json()

        entry = body["items"][0]
        assert entry["summary"] == "Создан кабинет 901/3"
        assert entry["actor_name"] == "Оператор аудита"
        assert entry["actor_role_label"] == "оператор"
        assert entry["entity_label"] == "Кабинеты"


def test_change_history_is_ordered_newest_first(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-order.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        for name in ("911/3", "912/3", "913/3"):
            client.post("/rooms", headers=_auth(admin_token), json={"name": name})

        items = client.get("/audit", headers=_auth(admin_token), params={"entity_type": "room"}).json()["items"]

        assert [item["summary"] for item in items] == [
            "Создан кабинет 913/3",
            "Создан кабинет 912/3",
            "Создан кабинет 911/3",
        ]


def test_pagination_returns_disjoint_batches_with_stable_total(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-pages.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        for index in range(5):
            client.post("/rooms", headers=_auth(admin_token), json={"name": f"92{index}/3"})

        first = client.get(
            "/audit", headers=_auth(admin_token), params={"entity_type": "room", "limit": 2}
        ).json()
        second = client.get(
            "/audit", headers=_auth(admin_token), params={"entity_type": "room", "limit": 2, "offset": 2}
        ).json()

        assert first["total"] == second["total"] == 5
        assert first["limit"] == 2 and second["offset"] == 2
        assert len(first["items"]) == len(second["items"]) == 2
        first_ids = {item["id"] for item in first["items"]}
        assert first_ids.isdisjoint({item["id"] for item in second["items"]})


def test_entity_type_filter_keeps_only_matching_records(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-entity-filter.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        client.post("/rooms", headers=_auth(admin_token), json={"name": "931/3"})
        client.post(
            "/teachers",
            headers=_auth(admin_token),
            json={"name": "Иванов И.И.", "teacher_id": "audit-filter", "post": ""},
        )

        body = client.get("/audit", headers=_auth(admin_token), params={"entity_type": "room"}).json()

        assert body["total"] == 1
        assert {item["entity_type"] for item in body["items"]} == {"room"}
        assert client.get("/audit", headers=_auth(admin_token)).json()["total"] == 2


def test_date_filter_includes_the_whole_upper_bound_day(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-dates.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    today = datetime.now(timezone.utc).date()
    with TestClient(app) as client:
        client.post("/rooms", headers=_auth(admin_token), json={"name": "941/3"})

        def total(**params) -> int:
            return client.get("/audit", headers=_auth(admin_token), params={"entity_type": "room", **params}).json()[
                "total"
            ]

        assert total(date_from=today.isoformat(), date_to=today.isoformat()) == 1
        assert total(date_to=(today - timedelta(days=1)).isoformat()) == 0
        assert total(date_from=(today + timedelta(days=1)).isoformat()) == 0


@pytest.mark.parametrize(
    "query",
    [
        "951/3",  # a value stored inside the payload
        "Root Admin",  # the display name of whoever made the change
        "кабинет",  # the Russian label of the entity type, absent from the DB
        "создание",  # the Russian label of the action, absent from the DB
    ],
)
def test_search_finds_the_record_by_what_the_user_sees(tmp_path, monkeypatch, query):
    database_url = f"sqlite:///{tmp_path / 'audit-search.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        client.post("/rooms", headers=_auth(admin_token), json={"name": "951/3"})

        body = client.get("/audit", headers=_auth(admin_token), params={"q": query}).json()

        assert any(item["summary"] == "Создан кабинет 951/3" for item in body["items"]), body["items"]


def test_search_excludes_records_that_match_nothing(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-search-miss.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        client.post("/rooms", headers=_auth(admin_token), json={"name": "961/3"})

        body = client.get("/audit", headers=_auth(admin_token), params={"q": "профиль"}).json()

        assert body["total"] == 0


def test_import_is_recorded_with_the_user_who_ran_it(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-import.db'}"
    migrate_database(database_url)
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        assert client.post("/imports/schedule", headers=_auth(admin_token), json={"timetable": []}).status_code == 200

        body = client.get(
            "/audit", headers=_auth(admin_token), params={"entity_type": "schedule_import"}
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["summary"] == "Импорт расписания: групп 0, занятий 0"
        assert body["items"][0]["actor_name"] == "Root Admin"


def test_deleting_a_teacher_records_every_group_left_without_a_homeroom(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'audit-homeroom.db'}"
    migrate_database(database_url)
    _seed_import()
    admin_token = _bootstrap_and_get_admin_token(database_url, monkeypatch)
    app.state.database_url = database_url
    with TestClient(app) as client:
        teacher = client.post(
            "/teachers",
            headers=_auth(admin_token),
            json={"name": "Тестов Тест Тестович", "teacher_id": "audit-homeroom", "post": ""},
        ).json()
        group = client.get("/groups", headers=_auth(admin_token)).json()[0]
        client.patch(
            f"/groups/{group['id']}/homeroom-teacher",
            headers=_auth(admin_token),
            json={"teacher_id": teacher["id"]},
        )

        client.delete(f"/teachers/{teacher['id']}", headers=_auth(admin_token))

        items = client.get("/audit", headers=_auth(admin_token), params={"entity_type": "group"}).json()["items"]
        assert items[0]["summary"] == (
            f"У группы {group['name']} снят классный руководитель Тестов Тест Тестович — удалён преподаватель"
        )


SUMMARY_CASES = [
    ("room", "create", {"name": "305"}, "Создан кабинет 305"),
    (
        "room",
        "delete",
        {"name": "305", "unassigned_lesson_count": 4},
        "Удалён кабинет 305, занятий без кабинета: 4",
    ),
    ("room", "exclude", {"name": "305", "reason": "Ремонт"}, "Кабинет 305 исключён из расписания: Ремонт"),
    ("room", "restore", {"name": "305", "previous_reason": "Ремонт"}, "Кабинет 305 возвращён в расписание"),
    ("group", "rename", {"old_name": "ИС-21", "name": "ИС-22"}, "Группа ИС-21 переименована в ИС-22"),
    (
        "group",
        "set_homeroom_teacher",
        {"group_name": "ИС-21", "teacher_id": 7, "teacher_name": "Иванов И.И."},
        "Классным руководителем группы ИС-21 назначен Иванов И.И.",
    ),
    (
        "group",
        "set_homeroom_teacher",
        {"group_name": "ИС-21", "teacher_id": None, "teacher_name": None},
        "У группы ИС-21 снят классный руководитель",
    ),
    (
        "group",
        "clear_homeroom_teacher",
        {"group_name": "ИС-21", "teacher_name": "Иванов И.И."},
        "У группы ИС-21 снят классный руководитель Иванов И.И. — удалён преподаватель",
    ),
    (
        "group",
        "delete",
        {"name": "ИС-21", "deleted_lesson_count": 12},
        "Удалена группа ИС-21, удалено занятий: 12",
    ),
    ("teacher", "create", {"teacher_id": "t-1", "name": "Иванов И.И."}, "Добавлен преподаватель Иванов И.И."),
    (
        "teacher",
        "delete",
        {
            "teacher_id": "t-1",
            "name": "Иванов И.И.",
            "unassigned_lesson_count": 3,
            "deleted_absence_count": 0,
            "cleared_group_count": 1,
        },
        "Удалён преподаватель Иванов И.И., занятий без преподавателя: 3, групп без классного руководителя: 1",
    ),
    (
        "teacher",
        "mark_absent",
        {
            "id": 1,
            "teacher_name": "Иванов И.И.",
            "date": "2026-08-07",
            "all_day": True,
            "time_slot_start": 1,
            "time_slot_end": 7,
            "reason": "Больничный",
        },
        "Отмечено отсутствие: Иванов И.И., 07.08.2026, весь день, причина: Больничный",
    ),
    (
        "teacher",
        "mark_absent",
        {
            "id": 1,
            "teacher_name": "Иванов И.И.",
            "date": "2026-08-07",
            "all_day": False,
            "time_slot_start": 2,
            "time_slot_end": 3,
            "reason": "",
        },
        "Отмечено отсутствие: Иванов И.И., 07.08.2026, пары 2–3",
    ),
    (
        "teacher",
        "clear_absence",
        {"id": 1, "teacher_name": "Иванов И.И.", "date": "2026-08-07", "all_day": True},
        "Снято отсутствие: Иванов И.И., 07.08.2026",
    ),
    ("day_time_profile", "create", {"name": "Обычный день"}, "Создан профиль дня Обычный день"),
    ("day_time_profile", "update", {"name": "Обычный день"}, "Изменён профиль дня Обычный день"),
    ("day_time_profile", "delete", {"name": "Обычный день"}, "Удалён профиль дня Обычный день"),
    ("week_time_profile", "create", {"name": "Осень"}, "Создан профиль недели Осень"),
    ("week_time_profile", "update", {"name": "Осень"}, "Изменён профиль недели Осень"),
    ("week_time_profile", "delete", {"name": "Осень"}, "Удалён профиль недели Осень"),
    (
        "user",
        "create",
        {"username": "petrov", "display_name": "Пётр Петров", "role": "operator"},
        "Создан пользователь Пётр Петров (petrov), роль: оператор",
    ),
    ("user", "revoke", {"username": "petrov"}, "Отозван доступ пользователя petrov"),
    ("user", "change_password", {"username": "petrov"}, "Изменён пароль пользователя petrov"),
    (
        "lesson",
        "create",
        {"group_name": "ИС-21", "subject": "Математика", "date": "2026-08-07", "time_slot": 2},
        "Добавлено занятие: Математика, группа ИС-21, 07.08.2026, пара 2",
    ),
    (
        "lesson",
        "update",
        {
            "room_name": "305",
            "lesson": {"group_name": "ИС-21", "subject": "Математика", "date": "2026-08-07", "time_slot": 2},
        },
        "Изменено занятие: Математика, группа ИС-21, 07.08.2026, пара 2 — изменены поля: кабинет",
    ),
    (
        "lesson",
        "delete",
        {
            "source_lesson_id": "manual:1",
            "lesson": {"group_name": "ИС-21", "subject": "Математика", "date": "2026-08-07", "time_slot": 2},
        },
        "Удалено занятие: Математика, группа ИС-21, 07.08.2026, пара 2",
    ),
    (
        "schedule_import",
        "import",
        {"source_path": "api:/imports/schedule", "group_count": 115, "lesson_count": 2326},
        "Импорт расписания: групп 115, занятий 2326",
    ),
]


@pytest.mark.parametrize("entity_type,action,payload,expected", SUMMARY_CASES)
def test_summary_phrase_for_every_known_action(entity_type, action, payload, expected):
    entry = AuditLog(
        id=1,
        entity_type=entity_type,
        entity_id=42,
        action=action,
        actor_role="admin",
        actor_name="Root Admin",
        payload=payload,
    )

    assert build_summary(entry) == expected


@pytest.mark.parametrize(
    "entity_type,action,payload,expected",
    [
        # An action this build doesn't know about must not break the page.
        ("room", "teleport", {"name": "305"}, "teleport · Кабинеты #42"),
        ("plasma", "create", {}, "создание · plasma #42"),
        # Records written before the payloads carried entity names.
        ("room", "create", {}, "Создан кабинет #42"),
        ("group", "set_homeroom_teacher", {"teacher_name": None}, "У группы #42 снят классный руководитель"),
        ("lesson", "update", {}, "Изменено занятие: #42"),
    ],
)
def test_summary_degrades_gracefully(entity_type, action, payload, expected):
    entry = AuditLog(
        id=1,
        entity_type=entity_type,
        entity_id=42,
        action=action,
        actor_role="admin",
        actor_name="Root Admin",
        payload=payload,
    )

    assert build_summary(entry) == expected


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_import() -> None:
    import_schedule_from_json(Path(__file__).resolve().parents[3] / "7.json")


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
            headers=_auth(admin_token),
            json={
                "username": "operator-audit",
                "display_name": "Оператор аудита",
                "password": "operator-password",
                "role": "operator",
            },
        )
        return client.post(
            "/auth/login",
            json={"username": "operator-audit", "password": "operator-password"},
        ).json()["access_token"]
