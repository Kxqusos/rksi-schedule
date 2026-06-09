from pathlib import Path
from datetime import date, time
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Group, Lesson, Room, Subject, Teacher
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
    _seed_group_lessons(database_url, group_name="EDIT-1", slots=(1, 2), room_prefix="edit")

    create_response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "EDIT-1",
            "course": 0,
            "faculty": "",
            "subject": "Алгебра",
            "teacher_name": "Иванова А.А.",
            "teacher_id": "90001",
            "teacher_post": "",
            "room_name": "12/1",
            "date": "2026-02-23",
            "time_start": "11:30:00",
            "time_end": "13:00:00",
            "weekday": 1,
            "week_number": 7,
            "time_slot": 3,
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


def test_operator_can_list_lessons_by_date_and_slot(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'lesson_slice.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.get(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        params={"date": "2026-02-23", "time_slot": 1},
    )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) > 0
    assert rows[0]["room_name"]
    assert rows[0]["building"]

    occupied_row = next(row for row in rows if row["lesson"] is not None)
    assert occupied_row["lesson"]["date"] == "2026-02-23"
    assert occupied_row["lesson"]["time_slot"] == 1
    assert occupied_row["lesson"]["room_name"] == occupied_row["room_name"]
    assert occupied_row["lesson"]["group_name"]


def test_operator_can_create_lesson_in_empty_room_from_slot_grid(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'empty_room_create.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_group_lessons(database_url, group_name="ТЕСТ-77", slots=(2, 3), room_prefix="empty")

    list_response = client.get(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        params={"date": "2026-02-23", "time_slot": 1},
    )
    assert list_response.status_code == 200
    free_room = next(row for row in list_response.json() if row["lesson"] is None)

    create_response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "ТЕСТ-77",
            "course": 0,
            "faculty": "",
            "subject": "Тестовая замена",
            "teacher_name": "Проверка П.П.",
            "teacher_id": None,
            "teacher_post": "",
            "room_name": free_room["room_name"],
            "date": "2026-02-23",
            "time_start": "08:00:00",
            "time_end": "09:30:00",
            "weekday": 1,
            "week_number": 7,
            "time_slot": 1,
            "subgroup": 0,
            "lesson_type": "",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["room_name"] == free_room["room_name"]

    updated_list_response = client.get(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        params={"date": "2026-02-23", "time_slot": 1},
    )
    assert updated_list_response.status_code == 200
    updated_room = next(row for row in updated_list_response.json() if row["room_name"] == free_room["room_name"])
    assert updated_room["lesson"]["id"] == created["id"]
    assert updated_room["lesson"]["subject"] == "Тестовая замена"


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


def test_teacher_and_room_conflicts_are_returned_as_warnings(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'warnings.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_group_lessons(database_url, group_name="WARN-1", slots=(2, 3), room_prefix="warn")

    response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "WARN-1",
            "course": 0,
            "faculty": "",
            "subject": "Замена",
            "teacher_name": "Мальцева И.Е.",
            "teacher_id": "35147",
            "teacher_post": "",
            "room_name": "103/1",
            "date": "2026-02-23",
            "time_start": "08:00:00",
            "time_end": "09:30:00",
            "weekday": 1,
            "week_number": 7,
            "time_slot": 1,
            "subgroup": 0,
            "lesson_type": "",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["subject"] == "Замена"
    warning_codes = {warning["code"] for warning in payload["warnings"]}
    assert "teacher_double_booked" in warning_codes
    assert "room_double_booked" in warning_codes


def test_group_day_maximum_is_blocked(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'day_max.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_group_lessons(database_url, group_name="DAY-MAX", slots=(1, 2, 3, 4), room_prefix="daymax")

    response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "DAY-MAX",
            "course": 0,
            "faculty": "",
            "subject": "Лишняя пара",
            "teacher_name": "Свободный П.П.",
            "teacher_id": None,
            "teacher_post": "",
            "room_name": "daymax-5",
            "date": "2026-02-23",
            "time_start": "15:00:00",
            "time_end": "16:30:00",
            "weekday": 1,
            "week_number": 7,
            "time_slot": 5,
            "subgroup": 0,
            "lesson_type": "",
        },
    )

    assert response.status_code == 409
    assert "group day lesson limit exceeded" in response.json()["detail"]


def test_linter_limit_messages_include_actual_count_and_overage(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'limit_details.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_group_lessons(database_url, group_name="DETAIL-DAY", slots=(1, 2, 3, 4, 5), room_prefix="detail-day")
    _seed_group_week_lessons(database_url, group_name="DETAIL-WEEK", lesson_count=19)

    response = client.get("/schedule/problems", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    problems = response.json()
    day_problem = next(
        problem
        for problem in problems
        if problem["code"] == "group_day_limit_exceeded" and problem["group_name"] == "DETAIL-DAY"
    )
    week_problem = next(
        problem
        for problem in problems
        if problem["code"] == "group_week_limit_exceeded" and problem["group_name"] == "DETAIL-WEEK"
    )
    assert "максимум 4 пары" in day_problem["message"]
    assert "стоит 5 пар" in day_problem["message"]
    assert "превышение на 1 пару" in day_problem["message"]
    assert "максимум 18 пар" in week_problem["message"]
    assert "стоит 19 пар" in week_problem["message"]
    assert "превышение на 1 пару" in week_problem["message"]


def test_group_window_is_blocked(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'window.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_group_lessons(database_url, group_name="WINDOW-1", slots=(1,), room_prefix="window")

    response = client.post(
        "/schedule/lessons",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "group_name": "WINDOW-1",
            "course": 0,
            "faculty": "",
            "subject": "Пара с окном",
            "teacher_name": "Свободный О.О.",
            "teacher_id": None,
            "teacher_post": "",
            "room_name": "window-3",
            "date": "2026-02-23",
            "time_start": "11:30:00",
            "time_end": "13:00:00",
            "weekday": 1,
            "week_number": 7,
            "time_slot": 3,
            "subgroup": 0,
            "lesson_type": "",
        },
    )

    assert response.status_code == 409
    assert "group day schedule has a window" in response.json()["detail"]


def test_schedule_problems_linter_lists_warnings(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'problems.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)

    response = client.get("/schedule/problems", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    problems = response.json()
    assert any(problem["severity"] == "warning" for problem in problems)
    assert any(problem["code"] == "teacher_double_booked" for problem in problems)


def test_foreign_language_split_subgroups_are_not_multiple_teacher_error(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'foreign_language_split.db'}"
    migrate_database(database_url)
    _seed_import(database_url)
    operator_token = _bootstrap_and_get_operator_token(database_url, monkeypatch)
    app.state.database_url = database_url
    client = TestClient(app)
    _seed_foreign_language_split(database_url)

    response = client.get("/schedule/problems", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    problems = response.json()
    assert not any(
        problem["code"] == "group_slot_multiple_teachers" and problem["group_name"] == "LANG-SPLIT"
        for problem in problems
    )


def _seed_import(database_url: str) -> None:
    source = Path(__file__).resolve().parents[3] / "7.json"
    import_schedule_from_json(source, database_url=database_url)


def _seed_group_lessons(database_url: str, *, group_name: str, slots: tuple[int, ...], room_prefix: str) -> None:
    from app.db.session import build_session_factory

    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        with session.begin():
            group = Group(source_name=group_name, course=0, faculty="")
            subject = Subject(source_name=f"{group_name} subject")
            teacher = Teacher(source_teacher_id=f"{group_name} teacher", source_name=f"{group_name} teacher", post="")
            session.add_all([group, subject, teacher])
            session.flush()
            for slot in slots:
                room = Room(source_name=f"{room_prefix}-{slot}")
                session.add(room)
                session.flush()
                session.add(
                    Lesson(
                        source_lesson_id=f"{group_name}:{slot}",
                        schedule_import_id=1,
                        group_id=group.id,
                        subject_id=subject.id,
                        teacher_id=teacher.id,
                        room_id=room.id,
                        lesson_date=date(2026, 2, 23),
                        start_time=time(8 + slot, 0),
                        end_time=time(8 + slot, 30),
                        weekday=1,
                        week_number=7,
                        time_slot=slot,
                        subgroup=0,
                        lesson_type="",
                        raw_payload={},
                    )
                )


def _seed_foreign_language_split(database_url: str) -> None:
    from app.db.session import build_session_factory

    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        with session.begin():
            group = Group(source_name="LANG-SPLIT", course=0, faculty="")
            subject = session.scalar(select(Subject).where(Subject.source_name == "Иностранный язык"))
            if subject is None:
                subject = Subject(source_name="Иностранный язык")
                session.add(subject)
            teacher_one = Teacher(source_teacher_id="lang-teacher-1", source_name="Lang Teacher 1", post="")
            teacher_two = Teacher(source_teacher_id="lang-teacher-2", source_name="Lang Teacher 2", post="")
            room_one = Room(source_name="lang-1")
            room_two = Room(source_name="lang-2")
            session.add_all([group, subject, teacher_one, teacher_two, room_one, room_two])
            session.flush()
            for subgroup, teacher, room in ((1, teacher_one, room_one), (2, teacher_two, room_two)):
                session.add(
                    Lesson(
                        source_lesson_id=f"LANG-SPLIT:{subgroup}",
                        schedule_import_id=1,
                        group_id=group.id,
                        subject_id=subject.id,
                        teacher_id=teacher.id,
                        room_id=room.id,
                        lesson_date=date(2026, 2, 23),
                        start_time=time(8, 0),
                        end_time=time(9, 30),
                        weekday=1,
                        week_number=7,
                        time_slot=1,
                        subgroup=subgroup,
                        lesson_type="",
                        raw_payload={},
                    )
                )


def _seed_group_week_lessons(database_url: str, *, group_name: str, lesson_count: int) -> None:
    from app.db.session import build_session_factory

    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        with session.begin():
            group = Group(source_name=group_name, course=0, faculty="")
            subject = Subject(source_name=f"{group_name} subject")
            teacher = Teacher(source_teacher_id=f"{group_name} teacher", source_name=f"{group_name} teacher", post="")
            session.add_all([group, subject, teacher])
            session.flush()
            created = 0
            for day_offset in range(5):
                for slot in range(1, 5):
                    if created >= lesson_count:
                        return
                    room = Room(source_name=f"{group_name}-{day_offset}-{slot}")
                    session.add(room)
                    session.flush()
                    session.add(
                        Lesson(
                            source_lesson_id=f"{group_name}:{day_offset}:{slot}",
                            schedule_import_id=1,
                            group_id=group.id,
                            subject_id=subject.id,
                            teacher_id=teacher.id,
                            room_id=room.id,
                            lesson_date=date(2026, 2, 23 + day_offset),
                            start_time=time(8 + slot, 0),
                            end_time=time(8 + slot, 30),
                            weekday=1 + day_offset,
                            week_number=7,
                            time_slot=slot,
                            subgroup=0,
                            lesson_type="",
                            raw_payload={},
                        )
                    )
                    created += 1


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
