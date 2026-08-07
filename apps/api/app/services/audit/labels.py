from __future__ import annotations

"""Russian labels for audit records.

Shared by the mapper (which builds the phrase the user reads) and the
repository (which matches a search query against these labels, so that typing
"удаление" finds rows whose action column says "delete").
"""

ENTITY_LABELS = {
    "lesson": "Занятия",
    "group": "Группы",
    "teacher": "Преподаватели",
    "room": "Кабинеты",
    "day_time_profile": "Профили дня",
    "week_time_profile": "Профили недели",
    "user": "Пользователи",
    "schedule_import": "Импорт",
}

ROLE_LABELS = {
    "operator": "оператор",
    "admin": "администратор",
}

ACTION_LABELS = {
    "create": "создание",
    "update": "изменение",
    "delete": "удаление",
    "rename": "переименование",
    "exclude": "исключение",
    "restore": "восстановление",
    "set_homeroom_teacher": "назначение классного руководителя",
    "clear_homeroom_teacher": "снятие классного руководителя",
    "mark_absent": "отсутствие",
    "clear_absence": "снятие отсутствия",
    "revoke": "отзыв доступа",
    "change_password": "смена пароля",
    "import": "импорт",
}

LESSON_FIELD_LABELS = {
    "group_name": "группа",
    "course": "курс",
    "faculty": "отделение",
    "subject": "предмет",
    "teacher_name": "преподаватель",
    "teacher_id": "преподаватель",
    "teacher_post": "должность",
    "room_name": "кабинет",
    "date": "дата",
    "time_start": "начало",
    "time_end": "конец",
    "weekday": "день недели",
    "week_number": "неделя",
    "time_slot": "пара",
    "subgroup": "подгруппа",
    "lesson_type": "тип занятия",
}


def entity_label(entity_type: str) -> str:
    return ENTITY_LABELS.get(entity_type, entity_type)


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def match_entity_types(query: str) -> list[str]:
    return [key for key, label in ENTITY_LABELS.items() if query in label.lower()]


def match_actions(query: str) -> list[str]:
    return [key for key, label in ACTION_LABELS.items() if query in label.lower()]
