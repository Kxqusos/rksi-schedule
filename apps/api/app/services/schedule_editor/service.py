from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.models import AuditLog, Group, Lesson, Room, Subject, Teacher
from app.schemas.schedule_edit import (
    LessonCreateRequest,
    LessonResponse,
    LessonUpdateRequest,
    PublicScheduleDayResponse,
    PublicScheduleWeekResponse,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)
from app.services.auth.permissions import Actor
from app.services.teachers import teacher_absence_for_slot


MAX_GROUP_WEEK_LESSONS = 18
MAX_GROUP_DAY_LESSONS = 4
MIN_GROUP_DAY_LESSONS = 2
AGGREGATED_GROUP_PROBLEM_CODES = {
    "group_week_limit_exceeded",
    "group_day_limit_exceeded",
    "group_day_minimum_not_met",
    "group_day_window",
    "group_slot_multiple_teachers",
}


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
    original_room_id = lesson.room_id
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
    lesson.raw_payload = {**lesson.raw_payload, **payload.model_dump(mode="json", exclude_unset=True)}
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
    rooms = session.scalars(select(Room).where(Room.is_excluded.is_(False)).order_by(Room.source_name)).all()
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
        room = session.scalar(select(Room).where(Room.source_name == lesson.room_name)) if lesson.room_name else None
        rows.append(
            ScheduleSlotRoomResponse(
                room_name=lesson.room_name or "Без кабинета",
                building=_room_building(lesson.room_name or ""),
                room_is_excluded=room.is_excluded if room else False,
                room_exclusion_reason=room.exclusion_reason if room else "",
                lesson=lesson,
            )
        )
    return rows


def get_latest_public_week(session) -> PublicScheduleWeekResponse:
    latest_date = session.scalar(select(func.max(Lesson.lesson_date)))
    if latest_date is None:
        return PublicScheduleWeekResponse()

    week_start = latest_date - timedelta(days=latest_date.weekday())
    week_end = week_start + timedelta(days=6)
    latest_week_number = session.scalar(
        select(Lesson.week_number)
        .where(Lesson.lesson_date == latest_date)
        .order_by(Lesson.week_number.desc())
        .limit(1)
    )
    lessons = session.scalars(
        select(Lesson)
        .where(Lesson.lesson_date >= week_start, Lesson.lesson_date <= week_end)
        .order_by(Lesson.lesson_date, Lesson.time_slot, Lesson.subgroup)
    ).all()

    lessons_by_date = {week_start + timedelta(days=offset): [] for offset in range(7)}
    for lesson in lessons:
        lessons_by_date.setdefault(lesson.lesson_date, []).append(_lesson_response(session, lesson))

    return PublicScheduleWeekResponse(
        week_start=week_start,
        week_end=week_end,
        week_number=latest_week_number,
        days=[
            PublicScheduleDayResponse(
                date=day_date,
                weekday=index + 1,
                lessons=lessons_by_date.get(day_date, []),
            )
            for index, day_date in enumerate(week_start + timedelta(days=offset) for offset in range(7))
        ],
    )


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
    problems.extend(_absent_teacher_errors(session))
    problems.extend(_excluded_room_errors(session))
    problems = _aggregate_group_problems(problems)
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


def _aggregate_group_problems(problems: list[ScheduleProblemResponse]) -> list[ScheduleProblemResponse]:
    grouped: dict[str, list[ScheduleProblemResponse]] = {}
    result: list[ScheduleProblemResponse] = []
    for problem in problems:
        if problem.code in AGGREGATED_GROUP_PROBLEM_CODES and problem.group_name:
            grouped.setdefault(problem.code, []).append(problem)
        else:
            result.append(problem)

    for code, code_problems in grouped.items():
        if len(code_problems) == 1:
            result.append(code_problems[0])
            continue
        group_names = _unique_values(problem.group_name for problem in code_problems)
        lesson_ids: list[int] = []
        for problem in code_problems:
            lesson_ids.extend(problem.lesson_ids)
        result.append(
            ScheduleProblemResponse(
                severity=code_problems[0].severity,
                code=code,
                message=_aggregated_group_problem_message(code_problems),
                date=_single_value(problem.date for problem in code_problems),
                week_number=_single_value(problem.week_number for problem in code_problems),
                time_slot=_single_value(problem.time_slot for problem in code_problems),
                group_name=", ".join(group_names),
                lesson_ids=list(dict.fromkeys(lesson_ids)),
            )
        )
    return result


def _aggregated_group_problem_message(problems: list[ScheduleProblemResponse]) -> str:
    code = problems[0].code
    header = _aggregated_group_problem_header(code)
    lines = [_aggregated_group_problem_line(problem) for problem in problems]
    return "\n".join([header, *lines])


def _aggregated_group_problem_header(code: str) -> str:
    headers = {
        "group_week_limit_exceeded": (
            f"У перечисленных групп превышен максимум "
            f"{MAX_GROUP_WEEK_LESSONS} {_pair_word(MAX_GROUP_WEEK_LESSONS)} за неделю:"
        ),
        "group_day_limit_exceeded": (
            f"У перечисленных групп превышен максимум "
            f"{MAX_GROUP_DAY_LESSONS} {_pair_word(MAX_GROUP_DAY_LESSONS)} в день:"
        ),
        "group_day_minimum_not_met": f"У перечисленных групп меньше {MIN_GROUP_DAY_LESSONS} пар в день:",
        "group_day_window": "У перечисленных групп есть окно в расписании:",
        "group_slot_multiple_teachers": "У перечисленных групп два преподавателя на одну пару:",
    }
    return headers.get(code, "У перечисленных групп есть проблема:")


def _aggregated_group_problem_line(problem: ScheduleProblemResponse) -> str:
    group_name = problem.group_name or "Без группы"
    detail = _aggregated_group_problem_detail(problem)
    return f"{group_name}: {detail}"


def _aggregated_group_problem_detail(problem: ScheduleProblemResponse) -> str:
    if problem.code in {"group_week_limit_exceeded", "group_day_limit_exceeded"}:
        return problem.message.split(": ", 1)[1] if ": " in problem.message else problem.message
    if problem.code == "group_day_minimum_not_met":
        return f"{_problem_location(problem)}меньше {MIN_GROUP_DAY_LESSONS} пар."
    if problem.code == "group_day_window":
        return _problem_location(problem).removesuffix(". ")
    if problem.code == "group_slot_multiple_teachers":
        return f"{_problem_location(problem)}два преподавателя."
    return problem.message


def _problem_location(problem: ScheduleProblemResponse) -> str:
    parts = []
    if problem.date is not None:
        parts.append(_format_display_date(problem.date))
    if problem.week_number is not None:
        parts.append(f"{problem.week_number} неделя")
    if problem.time_slot is not None:
        parts.append(f"{problem.time_slot} пара")
    return f"{', '.join(parts)}. " if parts else ""


def _format_display_date(value) -> str:
    return value.strftime("%d.%m.%Y")


def _unique_values(values) -> list:
    return list(dict.fromkeys(value for value in values if value is not None and value != ""))


def _single_value(values):
    unique_values = _unique_values(values)
    return unique_values[0] if len(unique_values) == 1 else None


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

    if room_id is not None:
        room = session.get(Room, room_id)
        if room is not None and room.is_excluded:
            raise ConflictError("room is excluded from schedule")

    if teacher_id is not None and teacher_absence_for_slot(
        session,
        teacher_id=teacher_id,
        lesson_date=lesson_date,
        time_slot=time_slot,
    ):
        raise ConflictError("teacher is absent in this slot")


def _first_conflict(session, *conditions, exclude_lesson_id: int | None):
    query = select(Lesson).where(*conditions)
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.limit(1))


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
    query = select(Lesson).where(
        Lesson.room_id == room_id,
        Lesson.lesson_date == lesson_date,
        Lesson.time_slot == time_slot,
    )
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.order_by(Lesson.subgroup, Lesson.id).limit(1))


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
        "absent_teacher_scheduled": "teacher is absent in this slot",
        "excluded_room_scheduled": "room is excluded from schedule",
    }
    return details.get(problem.code, problem.message)


def _group_week_errors(session, group_id: int, week_number: int) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.week_number == week_number).order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()
    counted_lessons = [lesson for lesson in lessons if _counts_toward_group_pair_limits(session, lesson)]
    actual_count = _weekly_pair_count(counted_lessons)
    if actual_count <= MAX_GROUP_WEEK_LESSONS:
        return []
    group = session.get(Group, group_id)
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
            lesson_ids=[lesson.id for lesson in counted_lessons],
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
    counted_lessons = [lesson for lesson in lessons if _counts_toward_group_pair_limits(session, lesson)]
    lesson_ids = [lesson.id for lesson in lessons]
    counted_lesson_ids = [lesson.id for lesson in counted_lessons]
    actual_count = _daily_pair_count(counted_lessons)
    problems: list[ScheduleProblemResponse] = []
    if actual_count > MAX_GROUP_DAY_LESSONS:
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
                lesson_ids=counted_lesson_ids,
            )
        )
    if actual_count < MIN_GROUP_DAY_LESSONS:
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


def _daily_pair_count(lessons: list[Lesson]) -> int:
    return len({lesson.time_slot for lesson in lessons})


def _weekly_pair_count(lessons: list[Lesson]) -> int:
    return len({(lesson.lesson_date, lesson.time_slot) for lesson in lessons})


def _counts_toward_group_pair_limits(session, lesson: Lesson) -> bool:
    return not _is_additional_lesson(session, lesson) and not _is_class_hour_lesson(session, lesson)


def _is_additional_lesson(session, lesson: Lesson) -> bool:
    subject = session.get(Subject, lesson.subject_id)
    raw_payload = lesson.raw_payload if isinstance(lesson.raw_payload, dict) else {}
    labels = [
        lesson.lesson_type,
        raw_payload.get("type", ""),
        raw_payload.get("subject", ""),
        subject.source_name if subject else "",
    ]
    return any(_is_additional_lesson_label(str(label)) for label in labels if label is not None)


def _is_class_hour_lesson(session, lesson: Lesson) -> bool:
    subject = session.get(Subject, lesson.subject_id)
    raw_payload = lesson.raw_payload if isinstance(lesson.raw_payload, dict) else {}
    labels = [
        lesson.lesson_type,
        raw_payload.get("type", ""),
        raw_payload.get("subject", ""),
        subject.source_name if subject else "",
    ]
    return any(_is_class_hour_lesson_label(str(label)) for label in labels if label is not None)


def _is_additional_lesson_label(label: str) -> bool:
    normalized = "".join(character for character in label.casefold() if character.isalnum())
    return normalized.startswith("доп") and "занят" in normalized


def _is_class_hour_lesson_label(label: str) -> bool:
    normalized = "".join(character for character in label.casefold() if character.isalnum())
    return normalized == "классныйчас"


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


def _group_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "группа"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "группы"
    return "групп"


def _warnings_for_lesson(session, lesson: Lesson) -> list[ScheduleProblemResponse]:
    warnings = _double_booked_teacher_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot)
    warnings.extend(_double_booked_room_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot))
    lesson_warnings = []
    for warning in warnings:
        if lesson.id in warning.lesson_ids:
            lesson_warnings.append(warning)
    return lesson_warnings


def _absent_teacher_errors(session) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.teacher_id.is_not(None)).order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()
    problems: list[ScheduleProblemResponse] = []
    for lesson in lessons:
        if lesson.teacher_id is None:
            continue
        absence = teacher_absence_for_slot(
            session,
            teacher_id=lesson.teacher_id,
            lesson_date=lesson.lesson_date,
            time_slot=lesson.time_slot,
        )
        if absence is None:
            continue
        teacher = session.get(Teacher, lesson.teacher_id)
        reason_suffix = f" Причина: {absence.reason}." if absence.reason else ""
        problems.append(
            ScheduleProblemResponse(
                severity="error",
                code="absent_teacher_scheduled",
                message=(
                    f"Преподаватель {teacher.source_name if teacher else ''} отсутствует, "
                    f"но стоит в расписании на {lesson.time_slot} пару.{reason_suffix}"
                ),
                date=lesson.lesson_date,
                time_slot=lesson.time_slot,
                teacher_name=teacher.source_name if teacher else None,
                lesson_ids=[lesson.id],
            )
        )
    return problems


def _excluded_room_errors(session) -> list[ScheduleProblemResponse]:
    lessons = session.scalars(
        select(Lesson).where(Lesson.room_id.is_not(None)).order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()
    problems: list[ScheduleProblemResponse] = []
    for lesson in lessons:
        if lesson.room_id is None:
            continue
        room = session.get(Room, lesson.room_id)
        if room is None or not room.is_excluded:
            continue
        reason_suffix = f" Причина: {room.exclusion_reason}." if room.exclusion_reason else ""
        problems.append(
            ScheduleProblemResponse(
                severity="error",
                code="excluded_room_scheduled",
                message=(
                    f"Кабинет {room.source_name} исключён из расписания, "
                    f"но стоит на {lesson.time_slot} пару.{reason_suffix}"
                ),
                date=lesson.lesson_date,
                time_slot=lesson.time_slot,
                room_name=room.source_name,
                lesson_ids=[lesson.id],
            )
        )
    return problems


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
    return LessonResponse(
        id=lesson.id,
        group_name=group.source_name if group else "",
        subject=subject.source_name if subject else "",
        teacher_name=teacher.source_name if teacher else None,
        teacher_is_absent=teacher_absence is not None,
        teacher_absence_reason=teacher_absence.reason if teacher_absence else "",
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
