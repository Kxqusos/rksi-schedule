from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.models import AuditLog, Group, Lesson, Room, Subject, Teacher
from app.schemas.schedule_edit import LessonCreateRequest, LessonResponse, LessonUpdateRequest
from app.services.auth.permissions import Actor


class ConflictError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class LessonNotFoundError(Exception):
    pass


def create_lesson(session, payload: LessonCreateRequest, actor: Actor) -> LessonResponse:
    group = _get_or_create_group(session, payload.group_name, payload.course, payload.faculty)
    subject = _get_or_create_subject(session, payload.subject)
    teacher = _get_or_create_teacher(session, payload.teacher_id, payload.teacher_name, payload.teacher_post)
    room = _get_or_create_room(session, payload.room_name)

    _ensure_no_conflicts(
        session,
        group_id=group.id,
        teacher_id=teacher.id if teacher else None,
        room_id=room.id if room else None,
        lesson_date=payload.date,
        time_slot=payload.time_slot,
        subgroup=payload.subgroup,
    )

    lesson = Lesson(
        source_lesson_id=f"manual:{uuid4()}",
        schedule_import_id=_latest_import_id(session),
        group_id=group.id,
        subject_id=subject.id,
        teacher_id=teacher.id if teacher else None,
        room_id=room.id if room else None,
        lesson_date=payload.date,
        start_time=payload.time_start,
        end_time=payload.time_end,
        weekday=payload.weekday,
        week_number=payload.week_number,
        time_slot=payload.time_slot,
        subgroup=payload.subgroup,
        lesson_type=payload.lesson_type,
        raw_payload=payload.model_dump(mode="json"),
    )
    session.add(lesson)
    session.flush()
    _audit(session, action="create", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json"))
    return _lesson_response(session, lesson)


def update_lesson(session, lesson_id: int, payload: LessonUpdateRequest, actor: Actor) -> LessonResponse:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()

    group_id = lesson.group_id
    subject_id = lesson.subject_id
    teacher_id = lesson.teacher_id
    room_id = lesson.room_id

    if payload.group_name is not None:
        group = _get_or_create_group(session, payload.group_name, payload.course or 0, payload.faculty or "")
        group_id = group.id
    if payload.subject is not None:
        subject = _get_or_create_subject(session, payload.subject)
        subject_id = subject.id
    if payload.teacher_id is not None or payload.teacher_name is not None:
        teacher = _get_or_create_teacher(session, payload.teacher_id, payload.teacher_name, payload.teacher_post)
        teacher_id = teacher.id if teacher else None
    if payload.room_name is not None:
        room = _get_or_create_room(session, payload.room_name)
        room_id = room.id if room else None

    lesson_date = payload.date or lesson.lesson_date
    time_slot = payload.time_slot or lesson.time_slot
    subgroup = payload.subgroup if payload.subgroup is not None else lesson.subgroup

    _ensure_no_conflicts(
        session,
        group_id=group_id,
        teacher_id=teacher_id,
        room_id=room_id,
        lesson_date=lesson_date,
        time_slot=time_slot,
        subgroup=subgroup,
        exclude_lesson_id=lesson.id,
    )

    lesson.group_id = group_id
    lesson.subject_id = subject_id
    lesson.teacher_id = teacher_id
    lesson.room_id = room_id
    lesson.lesson_date = lesson_date
    lesson.start_time = payload.time_start or lesson.start_time
    lesson.end_time = payload.time_end or lesson.end_time
    lesson.weekday = payload.weekday or lesson.weekday
    lesson.week_number = payload.week_number or lesson.week_number
    lesson.time_slot = time_slot
    lesson.subgroup = subgroup
    if payload.lesson_type is not None:
        lesson.lesson_type = payload.lesson_type
    lesson.raw_payload = {**lesson.raw_payload, **payload.model_dump(mode="json", exclude_unset=True)}
    session.flush()
    _audit(session, action="update", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json", exclude_unset=True))
    return _lesson_response(session, lesson)


def delete_lesson(session, lesson_id: int, actor: Actor) -> None:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()
    _audit(session, action="delete", lesson=lesson, actor=actor, payload={"source_lesson_id": lesson.source_lesson_id})
    session.delete(lesson)


def _latest_import_id(session) -> int:
    latest_id = session.scalar(select(Lesson.schedule_import_id).order_by(Lesson.schedule_import_id.desc()).limit(1))
    if latest_id is not None:
        return int(latest_id)
    raise ConflictError("at least one schedule import is required before manual edits")


def _ensure_no_conflicts(
    session,
    *,
    group_id: int,
    teacher_id: int | None,
    room_id: int | None,
    lesson_date,
    time_slot: int,
    subgroup: int,
    exclude_lesson_id: int | None = None,
) -> None:
    group_conflict = _first_conflict(
        session,
        Lesson.group_id == group_id,
        Lesson.lesson_date == lesson_date,
        Lesson.time_slot == time_slot,
        Lesson.subgroup == subgroup,
        exclude_lesson_id=exclude_lesson_id,
    )
    if group_conflict is not None:
        raise ConflictError("group already has a lesson in this slot")

    if teacher_id is not None:
        teacher_conflict = _first_conflict(
            session,
            Lesson.teacher_id == teacher_id,
            Lesson.lesson_date == lesson_date,
            Lesson.time_slot == time_slot,
            exclude_lesson_id=exclude_lesson_id,
        )
        if teacher_conflict is not None:
            raise ConflictError("teacher already has a lesson in this slot")

    if room_id is not None:
        room_conflict = _first_conflict(
            session,
            Lesson.room_id == room_id,
            Lesson.lesson_date == lesson_date,
            Lesson.time_slot == time_slot,
            exclude_lesson_id=exclude_lesson_id,
        )
        if room_conflict is not None:
            raise ConflictError("room already has a lesson in this slot")


def _first_conflict(session, *conditions, exclude_lesson_id: int | None):
    query = select(Lesson).where(*conditions)
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.limit(1))


def _get_or_create_group(session, name: str, course: int, faculty: str) -> Group:
    source_name = name.strip()
    group = session.scalar(select(Group).where(Group.source_name == source_name))
    if group is not None:
        return group
    group = Group(source_name=source_name, course=course, faculty=faculty)
    session.add(group)
    session.flush()
    return group


def _get_or_create_subject(session, name: str) -> Subject:
    source_name = name.strip()
    subject = session.scalar(select(Subject).where(Subject.source_name == source_name))
    if subject is not None:
        return subject
    subject = Subject(source_name=source_name)
    session.add(subject)
    session.flush()
    return subject


def _get_or_create_teacher(session, teacher_id: str | None, teacher_name: str | None, teacher_post: str | None) -> Teacher | None:
    if not teacher_id and not teacher_name:
        return None
    source_teacher_id = (teacher_id or teacher_name or "").strip()
    teacher = session.scalar(select(Teacher).where(Teacher.source_teacher_id == source_teacher_id))
    if teacher is not None:
        return teacher
    teacher = Teacher(
        source_teacher_id=source_teacher_id,
        source_name=(teacher_name or source_teacher_id).strip(),
        post=teacher_post or "",
    )
    session.add(teacher)
    session.flush()
    return teacher


def _get_or_create_room(session, room_name: str | None) -> Room | None:
    if not room_name:
        return None
    source_name = room_name.strip()
    room = session.scalar(select(Room).where(Room.source_name == source_name))
    if room is not None:
        return room
    room = Room(source_name=source_name)
    session.add(room)
    session.flush()
    return room


def _lesson_response(session, lesson: Lesson) -> LessonResponse:
    group = session.get(Group, lesson.group_id)
    subject = session.get(Subject, lesson.subject_id)
    teacher = session.get(Teacher, lesson.teacher_id) if lesson.teacher_id else None
    room = session.get(Room, lesson.room_id) if lesson.room_id else None
    return LessonResponse(
        id=lesson.id,
        group_name=group.source_name if group else "",
        subject=subject.source_name if subject else "",
        teacher_name=teacher.source_name if teacher else None,
        room_name=room.source_name if room else None,
        date=lesson.lesson_date,
        time_start=lesson.start_time,
        time_end=lesson.end_time,
        weekday=lesson.weekday,
        week_number=lesson.week_number,
        time_slot=lesson.time_slot,
        subgroup=lesson.subgroup,
        lesson_type=lesson.lesson_type,
    )


def _audit(session, *, action: str, lesson: Lesson, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type="lesson",
            entity_id=lesson.id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )

