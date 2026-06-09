from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.base import Base
from app.db.session import build_session_factory
from app.models import Group, Lesson, Room, ScheduleImport, Subject, Teacher


@dataclass(slots=True)
class ImportResult:
    timetable_count: int
    group_count: int
    lesson_count: int
    empty_day_count: int


def import_schedule_from_json(source: Path, database_url: str) -> ImportResult:
    payload = json.loads(source.read_text(encoding="utf-8"))
    documents = _normalize_root(payload)
    engine, session_factory = build_session_factory(database_url)
    Base.metadata.create_all(engine)

    timetable_count = 0
    group_count = 0
    lesson_count = 0
    empty_day_count = 0
    seen_groups: set[str] = set()

    with session_factory() as session:
        with session.begin():
            import_record = ScheduleImport(
                source_path=str(source),
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
                            lessons = day_payload.get("lessons") or []
                            if not lessons:
                                empty_day_count += 1
                            for lesson_payload in lessons:
                                lesson_source_id = str(lesson_payload["Lesson_ID_Num"])
                                if session.scalar(select(Lesson).where(Lesson.source_lesson_id == lesson_source_id)):
                                    continue
                                subject = _get_or_create_subject(session, lesson_payload.get("subject", ""))
                                teacher = _get_or_create_teacher(session, lesson_payload)
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


def _get_or_create_group(session, payload: dict[str, Any]) -> Group:
    name = str(payload.get("group_name", "")).strip()
    group = session.scalar(select(Group).where(Group.source_name == name))
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
    subject = session.scalar(select(Subject).where(Subject.source_name == subject_name))
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
    teacher = session.scalar(select(Teacher).where(Teacher.source_teacher_id == teacher_id))
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
    room = session.scalar(select(Room).where(Room.source_name == room_name))
    if room is not None:
        return room
    room = Room(source_name=room_name)
    session.add(room)
    session.flush()
    return room
