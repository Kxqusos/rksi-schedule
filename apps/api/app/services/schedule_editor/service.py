from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from uuid import uuid4

from app.models import AuditLog, Group, Lesson, Room, Subject, Teacher, TeacherAbsence

PUBLIC_ENTITY_TYPES = ("group", "teacher", "room")
# One cache key per (entity_type, entity_id, week); see core/cache.ScheduleCache.
CacheKey = tuple[str, int, int]
from app.services.auth.permissions import Actor
from app.services.schedule_editor import repository
from app.services.schedule_editor.problems import (
    ScheduleProblem,
    _blocking_detail,
    _group_day_errors,
    _group_slot_teacher_errors,
    _group_week_errors,
    _warnings_for_lesson,
    list_schedule_problems,
)
from app.services.teachers import (
    absence_matches_slot,
    teacher_absence_for_slot,
    teacher_absences_by_teacher,
)

__all__ = [
    "ConflictError",
    "EntityRefView",
    "LessonMutationResult",
    "LessonNotFoundError",
    "LessonView",
    "PUBLIC_ENTITY_TYPES",
    "ScheduleDayView",
    "ScheduleIndexView",
    "ScheduleWeekView",
    "SlotRoomView",
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
class LessonView:
    lesson: Lesson
    group_name: str
    subject_name: str
    teacher_name: str | None
    teacher_absence: TeacherAbsence | None
    room_name: str | None


@dataclass(frozen=True, slots=True)
class SlotRoomView:
    room_name: str
    building: str
    room_is_excluded: bool
    room_exclusion_reason: str
    lesson: LessonView | None


@dataclass(frozen=True, slots=True)
class ScheduleDayView:
    date: Date
    weekday: int
    lessons: list[LessonView]


@dataclass(frozen=True, slots=True)
class ScheduleWeekView:
    week_start: Date | None
    week_end: Date | None
    week_number: int | None
    days: list[ScheduleDayView]


@dataclass(frozen=True, slots=True)
class EntityRefView:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class ScheduleIndexView:
    groups: list[EntityRefView]
    teachers: list[EntityRefView]
    rooms: list[EntityRefView]
    weeks: list[int]
    latest_week: int | None


@dataclass(frozen=True, slots=True)
class LessonMutationResult:
    lesson: LessonView
    warnings: list[ScheduleProblem]
    cache_keys: list[CacheKey]


class ConflictError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class LessonNotFoundError(Exception):
    pass


def create_lesson(
    session,
    *,
    group_name: str,
    course: int,
    faculty: str,
    subject: str,
    source_teacher_id: str | None,
    teacher_name: str | None,
    teacher_post: str,
    room_name: str | None,
    lesson_date: Date,
    time_start,
    time_end,
    weekday: int,
    week_number: int,
    time_slot: int,
    subgroup: int,
    lesson_type: str,
    audit_payload: dict,
    actor: Actor,
) -> LessonMutationResult:
    group = _get_or_create_group(session, group_name, course, faculty)
    subject_obj = _get_or_create_subject(session, subject)
    teacher = _get_or_create_teacher(session, source_teacher_id, teacher_name, teacher_post)
    room = _get_or_create_room(session, room_name)

    _ensure_no_conflicts(
        session,
        group_id=group.id,
        teacher_id=teacher.id if teacher else None,
        room_id=room.id if room else None,
        lesson_date=lesson_date,
        time_slot=time_slot,
        subgroup=subgroup,
    )

    lesson = Lesson(
        source_lesson_id=f"manual:{uuid4()}",
        schedule_import_id=_latest_import_id(session),
        group_id=group.id,
        subject_id=subject_obj.id,
        teacher_id=teacher.id if teacher else None,
        room_id=room.id if room else None,
        lesson_date=lesson_date,
        start_time=time_start,
        end_time=time_end,
        weekday=weekday,
        week_number=week_number,
        time_slot=time_slot,
        subgroup=subgroup,
        lesson_type=lesson_type,
    )
    session.add(lesson)
    session.flush()
    _ensure_group_rules(session, group_ids={group.id}, dates={lesson_date}, week_numbers={week_number})
    _audit(session, action="create", lesson=lesson, actor=actor, payload=audit_payload)
    lesson_view = _lesson_view(session, lesson)
    cache_keys = _lesson_cache_keys(
        group_id=lesson.group_id, teacher_id=lesson.teacher_id, room_id=lesson.room_id, week_number=lesson.week_number
    )
    return LessonMutationResult(lesson=lesson_view, warnings=_warnings_for_lesson(session, lesson), cache_keys=cache_keys)


def update_lesson(
    session,
    lesson_id: int,
    *,
    group_name: str | None,
    course: int | None,
    faculty: str | None,
    subject: str | None,
    source_teacher_id: str | None,
    teacher_name: str | None,
    teacher_post: str | None,
    room_name: str | None,
    lesson_date: Date | None,
    time_start,
    time_end,
    weekday: int | None,
    week_number: int | None,
    time_slot: int | None,
    subgroup: int | None,
    lesson_type: str | None,
    changed_fields: set[str],
    audit_payload: dict,
    actor: Actor,
) -> LessonMutationResult:
    lesson = repository.get_lesson_by_id(session, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()

    original_group_id = lesson.group_id
    original_date = lesson.lesson_date
    original_week_number = lesson.week_number
    original_room_id = lesson.room_id
    original_teacher_id = lesson.teacher_id

    group_id = lesson.group_id
    subject_id = lesson.subject_id
    teacher_fk = lesson.teacher_id
    room_id = lesson.room_id

    if group_name is not None:
        group = _get_or_create_group(session, group_name, course or 0, faculty or "")
        group_id = group.id
    if subject is not None:
        subject_obj = _get_or_create_subject(session, subject)
        subject_id = subject_obj.id
    if source_teacher_id is not None or teacher_name is not None:
        teacher = _get_or_create_teacher(session, source_teacher_id, teacher_name, teacher_post)
        teacher_fk = teacher.id if teacher else None
    if "room_name" in changed_fields:
        room = _get_or_create_room(session, room_name)
        room_id = room.id if room else None

    new_lesson_date = lesson_date or lesson.lesson_date
    new_time_slot = time_slot or lesson.time_slot
    new_subgroup = subgroup if subgroup is not None else lesson.subgroup
    swapped_lesson = (
        _lesson_in_room_slot(
            session,
            room_id=room_id,
            lesson_date=new_lesson_date,
            time_slot=new_time_slot,
            exclude_lesson_id=lesson.id,
        )
        if "room_name" in changed_fields and room_id != original_room_id
        else None
    )

    _ensure_no_conflicts(
        session,
        group_id=group_id,
        teacher_id=teacher_fk,
        room_id=room_id,
        lesson_date=new_lesson_date,
        time_slot=new_time_slot,
        subgroup=new_subgroup,
        exclude_lesson_id=lesson.id,
    )

    lesson.group_id = group_id
    lesson.subject_id = subject_id
    lesson.teacher_id = teacher_fk
    lesson.room_id = room_id
    lesson.lesson_date = new_lesson_date
    lesson.start_time = time_start or lesson.start_time
    lesson.end_time = time_end or lesson.end_time
    lesson.weekday = weekday or lesson.weekday
    lesson.week_number = week_number or lesson.week_number
    lesson.time_slot = new_time_slot
    lesson.subgroup = new_subgroup
    if swapped_lesson is not None:
        swapped_lesson.room_id = original_room_id
    if lesson_type is not None:
        lesson.lesson_type = lesson_type
    session.flush()
    if changed_fields - {"room_name"}:
        _ensure_group_rules(
            session,
            group_ids={original_group_id, group_id},
            dates={original_date, lesson.lesson_date},
            week_numbers={original_week_number, lesson.week_number},
        )
    _audit(session, action="update", lesson=lesson, actor=actor, payload=audit_payload)
    lesson_view = _lesson_view(session, lesson)
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
    return LessonMutationResult(lesson=lesson_view, warnings=_warnings_for_lesson(session, lesson), cache_keys=cache_keys)


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


def list_lessons_by_slot(session, lesson_date, time_slot: int) -> list[SlotRoomView]:
    rooms = repository.get_rooms_ordered(session)
    lessons = repository.get_lessons_for_slot(session, lesson_date, time_slot)

    lessons_by_room: dict[str, list[LessonView]] = {}
    unplaced_lessons: list[LessonView] = []
    for lesson in lessons:
        lesson_view = _lesson_view(session, lesson)
        if lesson_view.room_name:
            lessons_by_room.setdefault(lesson_view.room_name, []).append(lesson_view)
        else:
            unplaced_lessons.append(lesson_view)

    rows: list[SlotRoomView] = [
        SlotRoomView(
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
            SlotRoomView(
                room_name=lesson.room_name or "Без кабинета",
                building=_room_building(lesson.room_name or ""),
                room_is_excluded=room.is_excluded if room else False,
                room_exclusion_reason=room.exclusion_reason if room else "",
                lesson=lesson,
            )
        )
    return rows


def get_latest_public_week(session) -> ScheduleWeekView:
    latest_date = repository.get_latest_lesson_date(session)
    if latest_date is None:
        return ScheduleWeekView(week_start=None, week_end=None, week_number=None, days=[])

    week_start = latest_date - timedelta(days=latest_date.weekday())
    week_end = week_start + timedelta(days=6)
    latest_week_number = repository.get_latest_week_number_for_date(session, latest_date)
    lessons = repository.get_lessons_for_week(session, week_start, week_end)

    views = _lesson_views(session, lessons)
    lessons_by_date = {week_start + timedelta(days=offset): [] for offset in range(7)}
    for lesson in lessons:
        lessons_by_date.setdefault(lesson.lesson_date, []).append(views[lesson.id])

    return ScheduleWeekView(
        week_start=week_start,
        week_end=week_end,
        week_number=latest_week_number,
        days=[
            ScheduleDayView(
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


def get_public_schedule_index(session) -> ScheduleIndexView:
    groups = repository.get_all_groups_ordered(session)
    teachers = repository.get_teachers_ordered(session)
    rooms = repository.get_rooms_ordered_all(session)
    weeks = sorted(
        {int(week) for week in repository.get_distinct_week_numbers(session) if week is not None}
    )
    return ScheduleIndexView(
        groups=[EntityRefView(id=group.id, name=group.source_name) for group in groups if group.source_name],
        teachers=[EntityRefView(id=teacher.id, name=teacher.source_name) for teacher in teachers if teacher.source_name],
        rooms=[EntityRefView(id=room.id, name=room.source_name) for room in rooms if room.source_name],
        weeks=weeks,
        latest_week=get_latest_week_number(session),
    )


def get_public_week_for_entity(session, entity_type: str, entity_id: int, week_number: int) -> ScheduleWeekView:
    if entity_type == "group":
        lessons = repository.get_lessons_for_group_and_week(session, entity_id, week_number)
    elif entity_type == "teacher":
        lessons = repository.get_lessons_for_teacher_and_week(session, entity_id, week_number)
    elif entity_type == "room":
        lessons = repository.get_lessons_for_room_and_week(session, entity_id, week_number)
    else:
        raise ValueError(f"unknown entity_type: {entity_type}")
    return _build_public_week(session, lessons, week_number=week_number)


def _build_public_week(session, lessons: list[Lesson], *, week_number: int) -> ScheduleWeekView:
    if not lessons:
        return ScheduleWeekView(week_start=None, week_end=None, week_number=week_number, days=[])
    reference_date = min(lesson.lesson_date for lesson in lessons)
    week_start = reference_date - timedelta(days=reference_date.weekday())
    week_end = week_start + timedelta(days=6)
    views = _lesson_views(session, lessons)
    lessons_by_date = {week_start + timedelta(days=offset): [] for offset in range(7)}
    for lesson in lessons:
        lessons_by_date.setdefault(lesson.lesson_date, []).append(views[lesson.id])
    return ScheduleWeekView(
        week_start=week_start,
        week_end=week_end,
        week_number=week_number,
        days=[
            ScheduleDayView(
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


def _lesson_view(session, lesson: Lesson) -> LessonView:
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
    return LessonView(
        lesson=lesson,
        group_name=group.source_name if group else "",
        subject_name=subject.source_name if subject else "",
        teacher_name=teacher.source_name if teacher else None,
        teacher_absence=teacher_absence,
        room_name=room.source_name if room else None,
    )


def _lesson_views(session, lessons: list[Lesson]) -> dict[int, LessonView]:
    """Build LessonViews for many lessons with a fixed number of queries.

    Prefetches every entity table and all absences once, then resolves each
    lesson in memory — avoids the per-lesson entity/absence lookups that make
    _lesson_view an N+1 when a whole week is rendered.
    """
    groups = {group.id: group for group in repository.get_all_groups_ordered(session)}
    subjects = {subject.id: subject for subject in repository.get_all_subjects(session)}
    teachers = {teacher.id: teacher for teacher in repository.get_all_teachers(session)}
    rooms = {room.id: room for room in repository.get_all_rooms(session)}
    absences_by_teacher = teacher_absences_by_teacher(session)

    views: dict[int, LessonView] = {}
    for lesson in lessons:
        group = groups.get(lesson.group_id)
        subject = subjects.get(lesson.subject_id)
        teacher = teachers.get(lesson.teacher_id) if lesson.teacher_id else None
        room = rooms.get(lesson.room_id) if lesson.room_id else None
        absence = None
        if lesson.teacher_id:
            absence = next(
                (
                    candidate
                    for candidate in absences_by_teacher.get(lesson.teacher_id, [])
                    if absence_matches_slot(candidate, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot)
                ),
                None,
            )
        views[lesson.id] = LessonView(
            lesson=lesson,
            group_name=group.source_name if group else "",
            subject_name=subject.source_name if subject else "",
            teacher_name=teacher.source_name if teacher else None,
            teacher_absence=absence,
            room_name=room.source_name if room else None,
        )
    return views


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
