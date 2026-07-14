from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.engine import get_session_factory
from app.models import Group, Lesson, Room, ScheduleImport, Subject, Teacher
from app.services.import_schedule import repository


MONDAY_WEEKDAY = 1
CLASS_HOUR_SLOT = 4
CLASS_HOUR_SUBJECT = "Классный час"
LESSON_SLOT_TIMES = {
    1: ("08:00", "09:30"),
    2: ("09:40", "11:10"),
    3: ("11:30", "13:00"),
    4: ("13:10", "14:40"),
    5: ("15:00", "16:30"),
    6: ("16:40", "18:10"),
    7: ("18:20", "19:50"),
}


@dataclass(slots=True)
class ImportResult:
    timetable_count: int
    group_count: int
    lesson_count: int
    empty_day_count: int


def import_schedule_from_json(source: Path) -> ImportResult:
    payload = json.loads(source.read_text(encoding="utf-8"))
    return import_schedule_from_payload(payload, source_path=str(source))


def import_schedule_from_payload(payload: Any, source_path: str = "<payload>") -> ImportResult:
    documents = _normalize_root(payload)
    session_factory = get_session_factory()

    timetable_count = 0
    group_count = 0
    lesson_count = 0
    empty_day_count = 0
    seen_groups: set[str] = set()

    with session_factory() as session:
        with session.begin():
            import_record = ScheduleImport(
                source_path=source_path,
                raw_payload=payload if isinstance(payload, dict) else {"documents": payload},
            )
            session.add(import_record)
            session.flush()

            for document in documents:
                for timetable in document.get("timetable", []):
                    timetable_count += 1
                    for group_payload in timetable.get("groups", []):
                        group = _get_or_create_group(session, group_payload)
                        if group.source_name not in seen_groups:
                            seen_groups.add(group.source_name)
                            group_count += 1
                        for day_payload in group_payload.get("days", []):
                            lessons = _normalize_day_lessons(timetable, group_payload, day_payload)
                            if not lessons:
                                empty_day_count += 1
                            for lesson_payload in lessons:
                                lesson_source_id = str(lesson_payload["Lesson_ID_Num"])
                                if repository.find_lesson_by_source_id(session, lesson_source_id):
                                    continue
                                subject = _get_or_create_subject(session, lesson_payload.get("subject", ""))
                                teacher = _get_or_create_teacher(session, lesson_payload)
                                if subject.source_name == CLASS_HOUR_SUBJECT and group.homeroom_teacher_id is not None:
                                    teacher = repository.get_teacher_by_id(session, group.homeroom_teacher_id)
                                room = _get_or_create_room(session, lesson_payload)
                                lesson = Lesson(
                                    source_lesson_id=lesson_source_id,
                                    schedule_import_id=import_record.id,
                                    group_id=group.id,
                                    subject_id=subject.id,
                                    teacher_id=teacher.id if teacher else None,
                                    room_id=room.id if room else None,
                                    lesson_date=_parse_date(lesson_payload["date"]),
                                    start_time=_parse_time(lesson_payload["time_start"]),
                                    end_time=_parse_time(lesson_payload["time_end"]),
                                    weekday=int(day_payload["weekday"]),
                                    week_number=int(lesson_payload["week"]),
                                    time_slot=int(lesson_payload["time"]),
                                    subgroup=int(lesson_payload.get("subgroup", 0)),
                                    lesson_type=str(lesson_payload.get("type", "")),
                                    raw_payload=lesson_payload,
                                )
                                session.add(lesson)
                                lesson_count += 1

            import_record.timetable_count = timetable_count
            import_record.group_count = group_count
            import_record.lesson_count = lesson_count
            import_record.empty_day_count = empty_day_count

    return ImportResult(
        timetable_count=timetable_count,
        group_count=group_count,
        lesson_count=lesson_count,
        empty_day_count=empty_day_count,
    )


def _normalize_root(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        documents = payload
    elif isinstance(payload, dict):
        documents = [payload]
    else:
        raise ValueError("schedule payload must be a JSON object or array of objects")

    normalized: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("each schedule document must be an object")
        if "timetable" not in document or not isinstance(document["timetable"], list):
            raise ValueError("each schedule document must contain a timetable array")
        normalized.append(document)
    return normalized


def _parse_date(value: str):
    return datetime.strptime(value, "%d-%m-%Y").date()


def _parse_time(value: str):
    return datetime.strptime(value, "%H:%M").time()


def _normalize_day_lessons(
    timetable_payload: dict[str, Any],
    group_payload: dict[str, Any],
    day_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    lessons = [dict(lesson) for lesson in day_payload.get("lessons") or []]
    if int(day_payload["weekday"]) != MONDAY_WEEKDAY:
        return lessons
    if not lessons:
        return lessons

    normalized: list[dict[str, Any]] = []
    has_class_hour = False
    for lesson in lessons:
        slot = int(lesson["time"])
        is_class_hour = str(lesson.get("subject", "")).strip() == CLASS_HOUR_SUBJECT
        if is_class_hour and slot == CLASS_HOUR_SLOT:
            has_class_hour = True
        elif slot >= CLASS_HOUR_SLOT:
            slot += 1
            start_time, end_time = _slot_time_payload(slot)
            lesson["time"] = slot
            lesson["time_start"] = start_time
            lesson["time_end"] = end_time
        normalized.append(lesson)

    if not has_class_hour:
        normalized.append(_build_class_hour_lesson(timetable_payload, group_payload, lessons))
    return normalized


def _build_class_hour_lesson(
    timetable_payload: dict[str, Any],
    group_payload: dict[str, Any],
    lessons: list[dict[str, Any]],
) -> dict[str, Any]:
    first_lesson = lessons[0] if lessons else {}
    group_name = str(group_payload.get("group_name", "")).strip()
    lesson_date = str(first_lesson.get("date") or timetable_payload["date_start"])
    week_number = int(first_lesson.get("week") or timetable_payload["week_number"])
    start_time, end_time = _slot_time_payload(CLASS_HOUR_SLOT)
    return {
        "subject": CLASS_HOUR_SUBJECT,
        "type": CLASS_HOUR_SUBJECT,
        "subgroup": 0,
        "time_start": start_time,
        "time_end": end_time,
        "time": CLASS_HOUR_SLOT,
        "week": week_number,
        "date": lesson_date,
        "teachers": [],
        "auditories": [],
        "Lesson_ID_Num": f"class-hour:{lesson_date}:{group_name}",
    }


def _slot_time_payload(slot: int) -> tuple[str, str]:
    if slot not in LESSON_SLOT_TIMES:
        raise ValueError(f"lesson slot {slot} has no configured time")
    return LESSON_SLOT_TIMES[slot]


def _get_or_create_group(session, payload: dict[str, Any]) -> Group:
    name = str(payload.get("group_name", "")).strip()
    group = repository.find_group_by_name(session, name)
    if group is not None:
        return group
    group = Group(
        source_name=name,
        course=int(payload.get("course", 0) or 0),
        faculty=str(payload.get("faculty", "") or ""),
    )
    session.add(group)
    session.flush()
    return group


def _get_or_create_subject(session, name: str) -> Subject:
    subject_name = name.strip()
    subject = repository.find_subject_by_name(session, subject_name)
    if subject is not None:
        return subject
    subject = Subject(source_name=subject_name)
    session.add(subject)
    session.flush()
    return subject


def _get_or_create_teacher(session, payload: dict[str, Any]) -> Teacher | None:
    teachers = payload.get("teachers") or []
    if not teachers:
        return None
    teacher_payload = teachers[0]
    teacher_id = str(teacher_payload.get("teacher_id", "")).strip()
    teacher = repository.find_teacher_by_source_id(session, teacher_id)
    if teacher is not None:
        return teacher
    teacher = Teacher(
        source_teacher_id=teacher_id,
        source_name=str(teacher_payload.get("teacher_name", "")).strip(),
        post=str(teacher_payload.get("teacher_post", "") or ""),
    )
    session.add(teacher)
    session.flush()
    return teacher


def _get_or_create_room(session, payload: dict[str, Any]) -> Room | None:
    auditories = payload.get("auditories") or []
    if not auditories:
        return None
    room_payload = auditories[0]
    room_name = str(room_payload.get("auditory_name", "")).strip()
    room = repository.find_room_by_name(session, room_name)
    if room is not None:
        return room
    room = Room(source_name=room_name)
    session.add(room)
    session.flush()
    return room
