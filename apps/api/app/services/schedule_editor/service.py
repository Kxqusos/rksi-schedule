from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from app.models import AuditLog, Group, Lesson, Room, Subject, Teacher
from app.schemas.schedule_edit import (
    LessonCreateRequest,
    LessonResponse,
    LessonUpdateRequest,
    PublicEntityRef,
    PublicScheduleDayResponse,
    PublicScheduleIndexResponse,
    PublicScheduleWeekResponse,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)

PUBLIC_ENTITY_TYPES = ("group", "teacher", "room")
# One cache key per (entity_type, entity_id, week); see core/cache.ScheduleCache.
CacheKey = tuple[str, int, int]
from app.services.auth.permissions import Actor
from app.services.schedule_editor import mappers, repository
from app.services.schedule_editor.problems import (
    _blocking_detail,
    _group_day_errors,
    _group_slot_teacher_errors,
    _group_week_errors,
    _warnings_for_lesson,
    list_schedule_problems,
)
from app.services.teachers import teacher_absence_for_slot

__all__ = [
    "ConflictError",
    "LessonMutationResult",
    "LessonNotFoundError",
    "PUBLIC_ENTITY_TYPES",
    "create_lesson",
    "delete_lesson",
    "get_latest_public_week",
    "get_latest_week_number",
    "get_public_schedule_index",
    "get_public_week_for_entity",
    "list_lessons_by_slot",
    "list_schedule_problems",
    "update_lesson",
]


@dataclass(frozen=True, slots=True)
class LessonMutationResult:
    lesson: LessonResponse
    warnings: list[ScheduleProblemResponse]
    cache_keys: list[CacheKey]


class ConflictError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class LessonNotFoundError(Exception):
    pass


def create_lesson(session, payload: LessonCreateRequest, actor: Actor) -> LessonMutationResult:
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
    )
    session.add(lesson)
    session.flush()
    _ensure_group_rules(session, group_ids={group.id}, dates={payload.date}, week_numbers={payload.week_number})
    _audit(session, action="create", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json"))
    lesson_response = _lesson_response(session, lesson)
    cache_keys = _lesson_cache_keys(
        group_id=lesson.group_id, teacher_id=lesson.teacher_id, room_id=lesson.room_id, week_number=lesson.week_number
    )
    return LessonMutationResult(lesson=lesson_response, warnings=_warnings_for_lesson(session, lesson), cache_keys=cache_keys)


def update_lesson(session, lesson_id: int, payload: LessonUpdateRequest, actor: Actor) -> LessonMutationResult:
    lesson = repository.get_lesson_by_id(session, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()

    original_group_id = lesson.group_id
    original_date = lesson.lesson_date
    original_week_number = lesson.week_number
    original_room_id = lesson.room_id
    original_teacher_id = lesson.teacher_id
    changed_fields = payload.model_fields_set

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
    if "room_name" in changed_fields:
        room = _get_or_create_room(session, payload.room_name)
        room_id = room.id if room else None

    lesson_date = payload.date or lesson.lesson_date
    time_slot = payload.time_slot or lesson.time_slot
    subgroup = payload.subgroup if payload.subgroup is not None else lesson.subgroup
    swapped_lesson = (
        _lesson_in_room_slot(
            session,
            room_id=room_id,
            lesson_date=lesson_date,
            time_slot=time_slot,
            exclude_lesson_id=lesson.id,
        )
        if "room_name" in changed_fields and room_id != original_room_id
        else None
    )

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
    if swapped_lesson is not None:
        swapped_lesson.room_id = original_room_id
    if payload.lesson_type is not None:
        lesson.lesson_type = payload.lesson_type
    session.flush()
    if changed_fields - {"room_name"}:
        _ensure_group_rules(
            session,
            group_ids={original_group_id, group_id},
            dates={original_date, lesson.lesson_date},
            week_numbers={original_week_number, lesson.week_number},
        )
    _audit(session, action="update", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json", exclude_unset=True))
    lesson_response = _lesson_response(session, lesson)
    cache_keys = _merge_cache_keys(
        _lesson_cache_keys(
            group_id=original_group_id,
            teacher_id=original_teacher_id,
            room_id=original_room_id,
            week_number=original_week_number,
        ),
        _lesson_cache_keys(
            group_id=lesson.group_id, teacher_id=lesson.teacher_id, room_id=lesson.room_id, week_number=lesson.week_number
        ),
    )
    return LessonMutationResult(lesson=lesson_response, warnings=_warnings_for_lesson(session, lesson), cache_keys=cache_keys)


def delete_lesson(session, lesson_id: int, actor: Actor) -> list[CacheKey]:
    lesson = repository.get_lesson_by_id(session, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()
    group_id = lesson.group_id
    lesson_date = lesson.lesson_date
    week_number = lesson.week_number
    cache_keys = _lesson_cache_keys(
        group_id=group_id, teacher_id=lesson.teacher_id, room_id=lesson.room_id, week_number=week_number
    )
    _audit(session, action="delete", lesson=lesson, actor=actor, payload={"source_lesson_id": lesson.source_lesson_id})
    session.delete(lesson)
    session.flush()
    _ensure_group_rules(session, group_ids={group_id}, dates={lesson_date}, week_numbers={week_number})
    return cache_keys


def list_lessons_by_slot(session, lesson_date, time_slot: int) -> list[ScheduleSlotRoomResponse]:
    rooms = repository.get_rooms_ordered(session)
    lessons = repository.get_lessons_for_slot(session, lesson_date, time_slot)

    lessons_by_room: dict[str, list[LessonResponse]] = {}
    unplaced_lessons: list[LessonResponse] = []
    for lesson in lessons:
        lesson_response = _lesson_response(session, lesson)
        if lesson_response.room_name:
            lessons_by_room.setdefault(lesson_response.room_name, []).append(lesson_response)
        else:
            unplaced_lessons.append(lesson_response)

    rows: list[ScheduleSlotRoomResponse] = [
        mappers.schedule_slot_room_response(
            room_name=room.source_name,
            building=_room_building(room.source_name),
            room_is_excluded=room.is_excluded,
            room_exclusion_reason=room.exclusion_reason,
            lesson=(room_lessons[0] if (room_lessons := lessons_by_room.get(room.source_name)) else None),
        )
        for room in rooms
    ]
    visible_room_names = {room.source_name for room in rooms}
    hidden_room_lessons = [
        lesson
        for room_name, room_lessons in lessons_by_room.items()
        if room_name not in visible_room_names
        for lesson in room_lessons
    ]
    for lesson in [*unplaced_lessons, *hidden_room_lessons]:
        room = repository.get_room_by_name(session, lesson.room_name) if lesson.room_name else None
        rows.append(
            mappers.schedule_slot_room_response(
                room_name=lesson.room_name or "Без кабинета",
                building=_room_building(lesson.room_name or ""),
                room_is_excluded=room.is_excluded if room else False,
                room_exclusion_reason=room.exclusion_reason if room else "",
                lesson=lesson,
            )
        )
    return rows


def get_latest_public_week(session) -> PublicScheduleWeekResponse:
    latest_date = repository.get_latest_lesson_date(session)
    if latest_date is None:
        return PublicScheduleWeekResponse()

    week_start = latest_date - timedelta(days=latest_date.weekday())
    week_end = week_start + timedelta(days=6)
    latest_week_number = repository.get_latest_week_number_for_date(session, latest_date)
    lessons = repository.get_lessons_for_week(session, week_start, week_end)

    lessons_by_date = {week_start + timedelta(days=offset): [] for offset in range(7)}
    for lesson in lessons:
        lessons_by_date.setdefault(lesson.lesson_date, []).append(_lesson_response(session, lesson))

    return mappers.public_schedule_week_response(
        week_start=week_start,
        week_end=week_end,
        week_number=latest_week_number,
        days=[
            mappers.public_schedule_day_response(
                date=day_date,
                weekday=index + 1,
                lessons=lessons_by_date.get(day_date, []),
            )
            for index, day_date in enumerate(week_start + timedelta(days=offset) for offset in range(7))
        ],
    )


def get_latest_week_number(session) -> int | None:
    latest_date = repository.get_latest_lesson_date(session)
    if latest_date is None:
        return None
    return repository.get_latest_week_number_for_date(session, latest_date)


def get_public_schedule_index(session) -> PublicScheduleIndexResponse:
    groups = repository.get_all_groups_ordered(session)
    teachers = repository.get_teachers_ordered(session)
    rooms = repository.get_rooms_ordered_all(session)
    weeks = sorted(
        {int(week) for week in repository.get_distinct_week_numbers(session) if week is not None}
    )
    return PublicScheduleIndexResponse(
        groups=[PublicEntityRef(id=group.id, name=group.source_name) for group in groups if group.source_name],
        teachers=[PublicEntityRef(id=teacher.id, name=teacher.source_name) for teacher in teachers if teacher.source_name],
        rooms=[PublicEntityRef(id=room.id, name=room.source_name) for room in rooms if room.source_name],
        weeks=weeks,
        latest_week=get_latest_week_number(session),
    )


def get_public_week_for_entity(session, entity_type: str, entity_id: int, week_number: int) -> PublicScheduleWeekResponse:
    if entity_type == "group":
        lessons = repository.get_lessons_for_group_and_week(session, entity_id, week_number)
    elif entity_type == "teacher":
        lessons = repository.get_lessons_for_teacher_and_week(session, entity_id, week_number)
    elif entity_type == "room":
        lessons = repository.get_lessons_for_room_and_week(session, entity_id, week_number)
    else:
        raise ValueError(f"unknown entity_type: {entity_type}")
    return _build_public_week(session, lessons, week_number=week_number)


def _build_public_week(session, lessons: list[Lesson], *, week_number: int) -> PublicScheduleWeekResponse:
    if not lessons:
        return PublicScheduleWeekResponse(week_number=week_number)
    reference_date = min(lesson.lesson_date for lesson in lessons)
    week_start = reference_date - timedelta(days=reference_date.weekday())
    week_end = week_start + timedelta(days=6)
    lessons_by_date = {week_start + timedelta(days=offset): [] for offset in range(7)}
    for lesson in lessons:
        lessons_by_date.setdefault(lesson.lesson_date, []).append(_lesson_response(session, lesson))
    return mappers.public_schedule_week_response(
        week_start=week_start,
        week_end=week_end,
        week_number=week_number,
        days=[
            mappers.public_schedule_day_response(
                date=day_date,
                weekday=index + 1,
                lessons=lessons_by_date.get(day_date, []),
            )
            for index, day_date in enumerate(week_start + timedelta(days=offset) for offset in range(7))
        ],
    )


def _lesson_cache_keys(*, group_id: int, teacher_id: int | None, room_id: int | None, week_number: int) -> list[CacheKey]:
    keys: list[CacheKey] = [("group", group_id, week_number)]
    if teacher_id is not None:
        keys.append(("teacher", teacher_id, week_number))
    if room_id is not None:
        keys.append(("room", room_id, week_number))
    return keys


def _merge_cache_keys(*key_lists: list[CacheKey]) -> list[CacheKey]:
    merged: list[CacheKey] = []
    for keys in key_lists:
        for key in keys:
            if key not in merged:
                merged.append(key)
    return merged


def _latest_import_id(session) -> int:
    latest_id = repository.get_latest_import_id(session)
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
    group_conflict = repository.get_conflicting_lesson(
        session,
        Lesson.group_id == group_id,
        Lesson.lesson_date == lesson_date,
        Lesson.time_slot == time_slot,
        Lesson.subgroup == subgroup,
        exclude_lesson_id=exclude_lesson_id,
    )
    if group_conflict is not None:
        raise ConflictError("group already has a lesson in this slot")

    if room_id is not None:
        room = repository.get_room_by_id(session, room_id)
        if room is not None and room.is_excluded:
            raise ConflictError("room is excluded from schedule")

    if teacher_id is not None and teacher_absence_for_slot(
        session,
        teacher_id=teacher_id,
        lesson_date=lesson_date,
        time_slot=time_slot,
    ):
        raise ConflictError("teacher is absent in this slot")


def _lesson_in_room_slot(
    session,
    *,
    room_id: int | None,
    lesson_date,
    time_slot: int,
    exclude_lesson_id: int | None,
) -> Lesson | None:
    if room_id is None:
        return None
    return repository.get_lesson_in_room_slot(
        session,
        room_id=room_id,
        lesson_date=lesson_date,
        time_slot=time_slot,
        exclude_lesson_id=exclude_lesson_id,
    )


def _ensure_group_rules(session, *, group_ids: set[int], dates: set, week_numbers: set[int]) -> None:
    for group_id in group_ids:
        for week_number in week_numbers:
            errors = _group_week_errors(session, group_id, week_number)
            if errors:
                raise ConflictError(_blocking_detail(errors[0]))
        for lesson_date in dates:
            errors = _group_day_errors(session, group_id, lesson_date)
            if errors:
                raise ConflictError(_blocking_detail(errors[0]))
            errors = _group_slot_teacher_errors(session, group_id, lesson_date)
            if errors:
                raise ConflictError(_blocking_detail(errors[0]))


def _get_or_create_group(session, name: str, course: int, faculty: str) -> Group:
    source_name = name.strip()
    group = repository.find_group_by_name(session, source_name)
    if group is not None:
        return group
    group = Group(source_name=source_name, course=course, faculty=faculty)
    session.add(group)
    session.flush()
    return group


def _get_or_create_subject(session, name: str) -> Subject:
    source_name = name.strip()
    subject = repository.find_subject_by_name(session, source_name)
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
    teacher = repository.find_teacher_by_source_id(session, source_teacher_id)
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
    room = repository.find_room_by_name(session, source_name)
    if room is not None:
        return room
    room = Room(source_name=source_name)
    session.add(room)
    session.flush()
    return room


def _lesson_response(session, lesson: Lesson) -> LessonResponse:
    group = repository.get_group_by_id(session, lesson.group_id)
    subject = repository.get_subject_by_id(session, lesson.subject_id)
    teacher = repository.get_teacher_by_id(session, lesson.teacher_id) if lesson.teacher_id else None
    room = repository.get_room_by_id(session, lesson.room_id) if lesson.room_id else None
    teacher_absence = (
        teacher_absence_for_slot(
            session,
            teacher_id=lesson.teacher_id,
            lesson_date=lesson.lesson_date,
            time_slot=lesson.time_slot,
        )
        if lesson.teacher_id
        else None
    )
    return mappers.lesson_to_response(
        lesson,
        group_name=group.source_name if group else "",
        subject_name=subject.source_name if subject else "",
        teacher_name=teacher.source_name if teacher else None,
        teacher_absence=teacher_absence,
        room_name=room.source_name if room else None,
    )


def _room_building(room_name: str) -> str:
    parts = [part for part in room_name.split("/") if part]
    if not parts:
        return "Без корпуса"
    last_part = parts[-1]
    if last_part.isdigit():
        return f"Корпус {last_part}"
    return "Без корпуса"


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
