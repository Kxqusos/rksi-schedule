from __future__ import annotations

from datetime import date as Date

from app.models import AuditLog
from app.schemas.audit import AuditEntryResponse, AuditPageResponse
from app.services.audit import labels
from app.services.audit.service import AuditPage


def audit_page_to_response(page: AuditPage) -> AuditPageResponse:
    return AuditPageResponse(
        items=[audit_entry_to_response(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


def audit_entry_to_response(entry: AuditLog) -> AuditEntryResponse:
    return AuditEntryResponse(
        id=entry.id,
        created_at=entry.created_at,
        actor_name=entry.actor_name,
        actor_role=entry.actor_role,
        actor_role_label=labels.role_label(entry.actor_role),
        entity_type=entry.entity_type,
        entity_label=labels.entity_label(entry.entity_type),
        action=entry.action,
        summary=build_summary(entry),
    )


def build_summary(entry: AuditLog) -> str:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    builder = _BUILDERS.get((entry.entity_type, entry.action))
    if builder is None:
        return _fallback(entry)
    return builder(payload, entry)


# --- rooms ---------------------------------------------------------------


def _room_create(payload: dict, entry: AuditLog) -> str:
    return f"Создан кабинет {_name(payload, 'name', entry)}"


def _room_delete(payload: dict, entry: AuditLog) -> str:
    return _with_counts(
        f"Удалён кабинет {_name(payload, 'name', entry)}",
        payload,
        [("unassigned_lesson_count", "занятий без кабинета")],
    )


def _room_exclude(payload: dict, entry: AuditLog) -> str:
    text = f"Кабинет {_name(payload, 'name', entry)} исключён из расписания"
    reason = (payload.get("reason") or "").strip()
    return f"{text}: {reason}" if reason else text


def _room_restore(payload: dict, entry: AuditLog) -> str:
    return f"Кабинет {_name(payload, 'name', entry)} возвращён в расписание"


# --- groups --------------------------------------------------------------


def _group_rename(payload: dict, entry: AuditLog) -> str:
    old_name = payload.get("old_name") or f"#{entry.entity_id}"
    return f"Группа {old_name} переименована в {_name(payload, 'name', entry)}"


def _group_set_homeroom_teacher(payload: dict, entry: AuditLog) -> str:
    group = _name(payload, "group_name", entry)
    teacher_name = payload.get("teacher_name")
    if teacher_name:
        return f"Классным руководителем группы {group} назначен {teacher_name}"
    return f"У группы {group} снят классный руководитель"


def _group_clear_homeroom_teacher(payload: dict, entry: AuditLog) -> str:
    group = _name(payload, "group_name", entry)
    teacher_name = payload.get("teacher_name")
    suffix = f" {teacher_name}" if teacher_name else ""
    return f"У группы {group} снят классный руководитель{suffix} — удалён преподаватель"


def _group_delete(payload: dict, entry: AuditLog) -> str:
    return _with_counts(
        f"Удалена группа {_name(payload, 'name', entry)}",
        payload,
        [("deleted_lesson_count", "удалено занятий")],
    )


# --- teachers ------------------------------------------------------------


def _teacher_create(payload: dict, entry: AuditLog) -> str:
    return f"Добавлен преподаватель {_name(payload, 'name', entry)}"


def _teacher_delete(payload: dict, entry: AuditLog) -> str:
    return _with_counts(
        f"Удалён преподаватель {_name(payload, 'name', entry)}",
        payload,
        [
            ("unassigned_lesson_count", "занятий без преподавателя"),
            ("deleted_absence_count", "снято отсутствий"),
            ("cleared_group_count", "групп без классного руководителя"),
        ],
    )


def _teacher_mark_absent(payload: dict, entry: AuditLog) -> str:
    text = f"Отмечено отсутствие: {_absence_ref(payload, entry)}"
    if payload.get("all_day"):
        text = f"{text}, весь день"
    else:
        slot_start = payload.get("time_slot_start")
        slot_end = payload.get("time_slot_end")
        if slot_start is not None and slot_end is not None:
            text = f"{text}, пары {slot_start}–{slot_end}"
    reason = (payload.get("reason") or "").strip()
    return f"{text}, причина: {reason}" if reason else text


def _teacher_clear_absence(payload: dict, entry: AuditLog) -> str:
    return f"Снято отсутствие: {_absence_ref(payload, entry)}"


def _absence_ref(payload: dict, entry: AuditLog) -> str:
    teacher = _name(payload, "teacher_name", entry)
    absence_date = _format_date(payload.get("date"))
    return f"{teacher}, {absence_date}" if absence_date else teacher


# --- time profiles -------------------------------------------------------


def _profile_builder(kind: str, verb: str):
    def build(payload: dict, entry: AuditLog) -> str:
        return f"{verb} {kind} {_name(payload, 'name', entry)}"

    return build


# --- users ---------------------------------------------------------------


def _user_create(payload: dict, entry: AuditLog) -> str:
    display_name = payload.get("display_name") or _name(payload, "username", entry)
    username = payload.get("username")
    text = f"Создан пользователь {display_name}"
    if username and username != display_name:
        text = f"{text} ({username})"
    role = payload.get("role")
    return f"{text}, роль: {labels.role_label(role)}" if role else text


def _user_revoke(payload: dict, entry: AuditLog) -> str:
    return f"Отозван доступ пользователя {_name(payload, 'username', entry)}"


def _user_change_password(payload: dict, entry: AuditLog) -> str:
    return f"Изменён пароль пользователя {_name(payload, 'username', entry)}"


# --- lessons -------------------------------------------------------------


def _lesson_create(payload: dict, entry: AuditLog) -> str:
    return f"Добавлено занятие: {_lesson_ref(payload, entry)}"


def _lesson_update(payload: dict, entry: AuditLog) -> str:
    text = f"Изменено занятие: {_lesson_ref(payload, entry)}"
    fields = _changed_field_labels(payload)
    return f"{text} — изменены поля: {', '.join(fields)}" if fields else text


def _lesson_delete(payload: dict, entry: AuditLog) -> str:
    return f"Удалено занятие: {_lesson_ref(payload, entry)}"


def _lesson_ref(payload: dict, entry: AuditLog) -> str:
    identity = payload.get("lesson") if isinstance(payload.get("lesson"), dict) else payload
    parts = []
    if identity.get("subject"):
        parts.append(str(identity["subject"]))
    if identity.get("group_name"):
        parts.append(f"группа {identity['group_name']}")
    lesson_date = _format_date(identity.get("date"))
    if lesson_date:
        parts.append(lesson_date)
    if identity.get("time_slot") is not None:
        parts.append(f"пара {identity['time_slot']}")
    return ", ".join(parts) if parts else f"#{entry.entity_id}"


def _changed_field_labels(payload: dict) -> list[str]:
    changed = [
        labels.LESSON_FIELD_LABELS[key]
        for key in payload
        if key != "lesson" and key in labels.LESSON_FIELD_LABELS
    ]
    return list(dict.fromkeys(changed))


# --- imports -------------------------------------------------------------


def _schedule_import(payload: dict, entry: AuditLog) -> str:
    group_count = payload.get("group_count", 0)
    lesson_count = payload.get("lesson_count", 0)
    return f"Импорт расписания: групп {group_count}, занятий {lesson_count}"


# --- shared helpers ------------------------------------------------------


def _name(payload: dict, key: str, entry: AuditLog) -> str:
    """Entity name from the payload, falling back to the id.

    Records written before the payloads carried entity names still have to
    render, and a deleted entity can no longer be looked up by id.
    """
    value = payload.get(key)
    return str(value) if value else f"#{entry.entity_id}"


def _with_counts(text: str, payload: dict, counts: list[tuple[str, str]]) -> str:
    parts = [f"{label}: {payload[key]}" for key, label in counts if payload.get(key)]
    return f"{text}, {', '.join(parts)}" if parts else text


def _format_date(value) -> str:
    if isinstance(value, Date):
        return value.strftime("%d.%m.%Y")
    if not value:
        return ""
    try:
        return Date.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _fallback(entry: AuditLog) -> str:
    action = labels.ACTION_LABELS.get(entry.action, entry.action)
    return f"{action} · {labels.entity_label(entry.entity_type)} #{entry.entity_id}"


_BUILDERS = {
    ("room", "create"): _room_create,
    ("room", "delete"): _room_delete,
    ("room", "exclude"): _room_exclude,
    ("room", "restore"): _room_restore,
    ("group", "rename"): _group_rename,
    ("group", "set_homeroom_teacher"): _group_set_homeroom_teacher,
    ("group", "clear_homeroom_teacher"): _group_clear_homeroom_teacher,
    ("group", "delete"): _group_delete,
    ("teacher", "create"): _teacher_create,
    ("teacher", "delete"): _teacher_delete,
    ("teacher", "mark_absent"): _teacher_mark_absent,
    ("teacher", "clear_absence"): _teacher_clear_absence,
    ("day_time_profile", "create"): _profile_builder("профиль дня", "Создан"),
    ("day_time_profile", "update"): _profile_builder("профиль дня", "Изменён"),
    ("day_time_profile", "delete"): _profile_builder("профиль дня", "Удалён"),
    ("week_time_profile", "create"): _profile_builder("профиль недели", "Создан"),
    ("week_time_profile", "update"): _profile_builder("профиль недели", "Изменён"),
    ("week_time_profile", "delete"): _profile_builder("профиль недели", "Удалён"),
    ("user", "create"): _user_create,
    ("user", "revoke"): _user_revoke,
    ("user", "change_password"): _user_change_password,
    ("lesson", "create"): _lesson_create,
    ("lesson", "update"): _lesson_update,
    ("lesson", "delete"): _lesson_delete,
    ("schedule_import", "import"): _schedule_import,
}
