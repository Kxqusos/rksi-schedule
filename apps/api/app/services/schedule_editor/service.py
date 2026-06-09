from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select

from app.models import AuditLog, Group, Lesson, Room, Subject, Teacher
from app.schemas.schedule_edit import (
    LessonCreateRequest,
    LessonResponse,
    LessonUpdateRequest,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)
from app.services.auth.permissions import Actor


MAX_GROUP_WEEK_LESSONS = 18
MAX_GROUP_DAY_LESSONS = 4
MIN_GROUP_DAY_LESSONS = 2


@dataclass(frozen=True, slots=True)
class LessonMutationResult:
    lesson: LessonResponse
    warnings: list[ScheduleProblemResponse]


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
        raw_payload=payload.model_dump(mode="json"),
    )
    session.add(lesson)
    session.flush()
    _ensure_group_rules(session, group_ids={group.id}, dates={payload.date}, week_numbers={payload.week_number})
    _audit(session, action="create", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json"))
    lesson_response = _lesson_response(session, lesson)
    return LessonMutationResult(lesson=lesson_response, warnings=_warnings_for_lesson(session, lesson))


def update_lesson(session, lesson_id: int, payload: LessonUpdateRequest, actor: Actor) -> LessonMutationResult:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()

    original_group_id = lesson.group_id
    original_date = lesson.lesson_date
    original_week_number = lesson.week_number

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
    _ensure_group_rules(
        session,
        group_ids={original_group_id, group_id},
        dates={original_date, lesson.lesson_date},
        week_numbers={original_week_number, lesson.week_number},
    )
    _audit(session, action="update", lesson=lesson, actor=actor, payload=payload.model_dump(mode="json", exclude_unset=True))
    lesson_response = _lesson_response(session, lesson)
    return LessonMutationResult(lesson=lesson_response, warnings=_warnings_for_lesson(session, lesson))


def delete_lesson(session, lesson_id: int, actor: Actor) -> None:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError()
    group_id = lesson.group_id
    lesson_date = lesson.lesson_date
    week_number = lesson.week_number
    _audit(session, action="delete", lesson=lesson, actor=actor, payload={"source_lesson_id": lesson.source_lesson_id})
    session.delete(lesson)
    session.flush()
    _ensure_group_rules(session, group_ids={group_id}, dates={lesson_date}, week_numbers={week_number})


def list_lessons_by_slot(session, lesson_date, time_slot: int) -> list[ScheduleSlotRoomResponse]:
    rooms = session.scalars(select(Room).order_by(Room.source_name)).all()
    lessons = session.scalars(
        select(Lesson)
        .join(Group, Group.id == Lesson.group_id)
        .outerjoin(Room, Room.id == Lesson.room_id)
        .where(
            Lesson.lesson_date == lesson_date,
            Lesson.time_slot == time_slot,
        )
        .order_by(Room.source_name, Group.source_name, Lesson.subgroup)
    ).all()

    lessons_by_room: dict[str, list[LessonResponse]] = {}
    unplaced_lessons: list[LessonResponse] = []
    for lesson in lessons:
        lesson_response = _lesson_response(session, lesson)
        if lesson_response.room_name:
            lessons_by_room.setdefault(lesson_response.room_name, []).append(lesson_response)
        else:
            unplaced_lessons.append(lesson_response)

    rows: list[ScheduleSlotRoomResponse] = [
        ScheduleSlotRoomResponse(
            room_name=room.source_name,
            building=_room_building(room.source_name),
            lesson=(room_lessons[0] if (room_lessons := lessons_by_room.get(room.source_name)) else None),
        )
        for room in rooms
    ]
    for lesson in unplaced_lessons:
        rows.append(
            ScheduleSlotRoomResponse(
                room_name="Без кабинета",
                building="Без корпуса",
                lesson=lesson,
            )
        )
    return rows


def list_schedule_problems(session) -> list[ScheduleProblemResponse]:
    problems: list[ScheduleProblemResponse] = []
    groups = session.scalars(select(Group).order_by(Group.source_name)).all()
    week_numbers = {
        int(week_number)
        for week_number in session.scalars(select(Lesson.week_number).distinct()).all()
        if week_number is not None
    }
    dates = set(session.scalars(select(Lesson.lesson_date).distinct()).all())

    for group in groups:
        for week_number in week_numbers:
            problems.extend(_group_week_errors(session, group.id, week_number))
        for lesson_date in dates:
            problems.extend(_group_day_errors(session, group.id, lesson_date))
            problems.extend(_group_slot_teacher_errors(session, group.id, lesson_date))

    problems.extend(_double_booked_teacher_warnings(session))
    problems.extend(_double_booked_room_warnings(session))
    return sorted(
        problems,
        key=lambda problem: (
            0 if problem.severity == "error" else 1,
            problem.date.isoformat() if problem.date else "",
            problem.time_slot or 0,
            problem.group_name or "",
            problem.code,
        ),
    )


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


def _first_conflict(session, *conditions, exclude_lesson_id: int | None):
    query = select(Lesson).where(*conditions)
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.limit(1))


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


def _blocking_detail(problem: ScheduleProblemResponse) -> str:
    details = {
        "group_week_limit_exceeded": "group week lesson limit exceeded",
        "group_day_limit_exceeded": "group day lesson limit exceeded",
        "group_day_minimum_not_met": "group day lesson minimum not met",
        "group_day_window": "group day schedule has a window",
        "group_slot_multiple_teachers": "group has multiple teachers in one slot",
    }
    return details.get(problem.code, problem.message)


def _group_week_errors(session, group_id: int, week_number: int) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.week_number == week_number).order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()
    if len(lessons) <= MAX_GROUP_WEEK_LESSONS:
        return []
    group = session.get(Group, group_id)
    actual_count = len(lessons)
    overage = actual_count - MAX_GROUP_WEEK_LESSONS
    return [
        ScheduleProblemResponse(
            severity="error",
            code="group_week_limit_exceeded",
            message=(
                f"У группы {group.source_name if group else ''} превышен максимум "
                f"{MAX_GROUP_WEEK_LESSONS} {_pair_word(MAX_GROUP_WEEK_LESSONS)} за неделю: "
                f"стоит {actual_count} {_pair_word(actual_count)}, "
                f"превышение на {overage} {_pair_word(overage, accusative=True)}."
            ),
            week_number=week_number,
            group_name=group.source_name if group else None,
            lesson_ids=[lesson.id for lesson in lessons],
        )
    ]


def _group_day_errors(session, group_id: int, lesson_date) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == lesson_date).order_by(Lesson.time_slot)
    ).all()
    if not lessons:
        return []

    group = session.get(Group, group_id)
    group_name = group.source_name if group else None
    lesson_ids = [lesson.id for lesson in lessons]
    problems: list[ScheduleProblemResponse] = []
    if len(lessons) > MAX_GROUP_DAY_LESSONS:
        actual_count = len(lessons)
        overage = actual_count - MAX_GROUP_DAY_LESSONS
        problems.append(
            ScheduleProblemResponse(
                severity="error",
                code="group_day_limit_exceeded",
                message=(
                    f"У группы {group_name or ''} превышен максимум "
                    f"{MAX_GROUP_DAY_LESSONS} {_pair_word(MAX_GROUP_DAY_LESSONS)} в день: "
                    f"стоит {actual_count} {_pair_word(actual_count)}, "
                    f"превышение на {overage} {_pair_word(overage, accusative=True)}."
                ),
                date=lesson_date,
                group_name=group_name,
                lesson_ids=lesson_ids,
            )
        )
    if len(lessons) < MIN_GROUP_DAY_LESSONS:
        problems.append(
            ScheduleProblemResponse(
                severity="error",
                code="group_day_minimum_not_met",
                message=f"У группы {group_name or ''} меньше {MIN_GROUP_DAY_LESSONS} пар в день.",
                date=lesson_date,
                group_name=group_name,
                lesson_ids=lesson_ids,
            )
        )

    slots = sorted({lesson.time_slot for lesson in lessons})
    if slots:
        missing_slots = [slot for slot in range(slots[0], slots[-1] + 1) if slot not in slots]
        if missing_slots:
            problems.append(
                ScheduleProblemResponse(
                    severity="error",
                    code="group_day_window",
                    message=f"У группы {group_name or ''} есть окно в расписании.",
                    date=lesson_date,
                    time_slot=missing_slots[0],
                    group_name=group_name,
                    lesson_ids=lesson_ids,
                )
            )
    return problems


def _group_slot_teacher_errors(session, group_id: int, lesson_date) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == lesson_date).order_by(Lesson.time_slot)
    ).all()
    group = session.get(Group, group_id)
    problems: list[ScheduleProblemResponse] = []
    lessons_by_slot: dict[int, list[Lesson]] = {}
    for lesson in lessons:
        lessons_by_slot.setdefault(lesson.time_slot, []).append(lesson)
    for slot, slot_lessons in lessons_by_slot.items():
        teacher_ids = {lesson.teacher_id for lesson in slot_lessons if lesson.teacher_id is not None}
        if len(teacher_ids) <= 1:
            continue
        if _is_foreign_language_subgroup_split(session, slot_lessons):
            continue
        problems.append(
            ScheduleProblemResponse(
                severity="error",
                code="group_slot_multiple_teachers",
                message=f"У группы {group.source_name if group else ''} два преподавателя на одну пару.",
                date=lesson_date,
                time_slot=slot,
                group_name=group.source_name if group else None,
                lesson_ids=[lesson.id for lesson in slot_lessons],
            )
        )
    return problems


def _is_foreign_language_subgroup_split(session, lessons: list[Lesson]) -> bool:
    if len(lessons) < 2 or any(lesson.subgroup <= 0 for lesson in lessons):
        return False
    subjects = [session.get(Subject, lesson.subject_id) for lesson in lessons]
    return all(subject is not None and "иностран" in subject.source_name.casefold() for subject in subjects)


def _pair_word(count: int, *, accusative: bool = False) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "пару" if accusative else "пара"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "пары"
    return "пар"


def _warnings_for_lesson(session, lesson: Lesson) -> list[ScheduleProblemResponse]:
    warnings = _double_booked_teacher_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot)
    warnings.extend(_double_booked_room_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot))
    lesson_warnings = []
    for warning in warnings:
        if lesson.id in warning.lesson_ids:
            lesson_warnings.append(warning)
    return lesson_warnings


def _double_booked_teacher_warnings(session, *, lesson_date=None, time_slot: int | None = None) -> list[ScheduleProblemResponse]:
    query = select(Lesson).where(Lesson.teacher_id.is_not(None))
    if lesson_date is not None:
        query = query.where(Lesson.lesson_date == lesson_date)
    if time_slot is not None:
        query = query.where(Lesson.time_slot == time_slot)
    lessons = session.scalars(query.order_by(Lesson.lesson_date, Lesson.time_slot)).all()
    grouped: dict[tuple[int, object, int], list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault((lesson.teacher_id, lesson.lesson_date, lesson.time_slot), []).append(lesson)

    warnings: list[ScheduleProblemResponse] = []
    for (teacher_id, date_value, slot), slot_lessons in grouped.items():
        group_ids = {lesson.group_id for lesson in slot_lessons}
        if len(group_ids) <= 1:
            continue
        teacher = session.get(Teacher, teacher_id)
        warnings.append(
            ScheduleProblemResponse(
                severity="warning",
                code="teacher_double_booked",
                message=f"Преподаватель {teacher.source_name if teacher else ''} стоит у двух групп в одну пару.",
                date=date_value,
                time_slot=slot,
                teacher_name=teacher.source_name if teacher else None,
                lesson_ids=[lesson.id for lesson in slot_lessons],
            )
        )
    return warnings


def _double_booked_room_warnings(session, *, lesson_date=None, time_slot: int | None = None) -> list[ScheduleProblemResponse]:
    query = select(Lesson).where(Lesson.room_id.is_not(None))
    if lesson_date is not None:
        query = query.where(Lesson.lesson_date == lesson_date)
    if time_slot is not None:
        query = query.where(Lesson.time_slot == time_slot)
    lessons = session.scalars(query.order_by(Lesson.lesson_date, Lesson.time_slot)).all()
    grouped: dict[tuple[int, object, int], list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault((lesson.room_id, lesson.lesson_date, lesson.time_slot), []).append(lesson)

    warnings: list[ScheduleProblemResponse] = []
    for (room_id, date_value, slot), slot_lessons in grouped.items():
        group_ids = {lesson.group_id for lesson in slot_lessons}
        if len(group_ids) <= 1:
            continue
        room = session.get(Room, room_id)
        warnings.append(
            ScheduleProblemResponse(
                severity="warning",
                code="room_double_booked",
                message=f"Кабинет {room.source_name if room else ''} стоит у двух групп в одну пару.",
                date=date_value,
                time_slot=slot,
                room_name=room.source_name if room else None,
                lesson_ids=[lesson.id for lesson in slot_lessons],
            )
        )
    return warnings


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
