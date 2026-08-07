from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as Date
from functools import lru_cache

from app.models import Group, Lesson, Subject
from app.services.schedule_editor import repository
from app.services.teachers import absence_matches_slot, teacher_absences_by_teacher

# Resolves a subject_id to its Subject (or None). Backed by a preloaded dict in
# the bulk linter and by repository.get_subject_by_id in the per-mutation path.
SubjectLookup = Callable[[int], "Subject | None"]


@dataclass(frozen=True, slots=True)
class ScheduleProblem:
    """Domain view of a schedule problem. Mirrors ScheduleProblemResponse; the
    router maps it to the response schema via mappers.schedule_problem_to_response."""

    severity: str
    code: str
    message: str
    date: Date | None = None
    week_number: int | None = None
    time_slot: int | None = None
    group_name: str | None = None
    teacher_name: str | None = None
    room_name: str | None = None
    lesson_ids: list[int] = field(default_factory=list)
    # How many problems this one stands for once its class is aggregated.
    count: int = 1


MAX_GROUP_WEEK_LESSONS = 18
MAX_GROUP_DAY_LESSONS = 4
MIN_GROUP_DAY_LESSONS = 2
# Errors that no single edit can avoid, so they are reported by a mutation
# instead of blocking it. The first lesson of a day is always below the daily
# minimum: the second one would satisfy the rule, but it can never be reached
# because the first save would be rejected. The linter still lists them.
NON_BLOCKING_EDIT_CODES = {"group_day_minimum_not_met"}
# One notification per problem class, one line per entity inside it. The entity
# differs by class, so each code declares which field names its rows: a group
# limit is listed by group, a double booking by the teacher or room it is about.
PROBLEM_SUBJECT_FIELDS = {
    "group_week_limit_exceeded": "group_name",
    "group_day_limit_exceeded": "group_name",
    "group_day_minimum_not_met": "group_name",
    "group_day_window": "group_name",
    "group_slot_multiple_teachers": "group_name",
    "absent_teacher_scheduled": "teacher_name",
    "teacher_double_booked": "teacher_name",
    "excluded_room_scheduled": "room_name",
    "room_double_booked": "room_name",
}


def list_schedule_problems(session) -> list[ScheduleProblem]:
    problems: list[ScheduleProblem] = []
    groups = repository.get_all_groups_ordered(session)

    # Preload everything once instead of querying per (group, week) / (group,
    # date): on a full year that inner loop was O(groups x dates) round-trips.
    all_lessons = repository.get_all_lessons(session)
    subjects_by_id = {subject.id: subject for subject in repository.get_all_subjects(session)}
    subject_lookup = subjects_by_id.get

    week_numbers = {
        int(week_number)
        for week_number in repository.get_distinct_week_numbers(session)
        if week_number is not None
    }
    dates = set(repository.get_distinct_lesson_dates(session))

    lessons_by_group_week: dict[tuple[int, int], list[Lesson]] = {}
    lessons_by_group_date: dict[tuple[int, object], list[Lesson]] = {}
    for lesson in all_lessons:
        lessons_by_group_week.setdefault((lesson.group_id, lesson.week_number), []).append(lesson)
        lessons_by_group_date.setdefault((lesson.group_id, lesson.lesson_date), []).append(lesson)

    for group in groups:
        for week_number in week_numbers:
            week_lessons = lessons_by_group_week.get((group.id, week_number), [])
            problems.extend(_group_week_problems(group, week_number, week_lessons, subject_lookup))
        for lesson_date in dates:
            day_lessons = lessons_by_group_date.get((group.id, lesson_date), [])
            problems.extend(_group_day_problems(group, lesson_date, day_lessons, subject_lookup))
            problems.extend(_group_slot_teacher_problems(group, lesson_date, day_lessons, subject_lookup))

    problems.extend(_double_booked_teacher_warnings(session))
    problems.extend(_double_booked_room_warnings(session))
    problems.extend(_absent_teacher_errors(session))
    problems.extend(_excluded_room_errors(session))
    problems = _aggregate_problems(problems)
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


def _aggregate_problems(problems: list[ScheduleProblem]) -> list[ScheduleProblem]:
    grouped: dict[str, list[ScheduleProblem]] = {}
    result: list[ScheduleProblem] = []
    for problem in problems:
        if _problem_subject(problem):
            grouped.setdefault(problem.code, []).append(problem)
        else:
            result.append(problem)

    for code, code_problems in grouped.items():
        if len(code_problems) == 1:
            result.append(code_problems[0])
            continue
        subjects = _unique_values(_problem_subject(problem) for problem in code_problems)
        lesson_ids: list[int] = []
        for problem in code_problems:
            lesson_ids.extend(problem.lesson_ids)
        # Every field but the one naming the rows keeps its value only while the
        # aggregated problems agree on it.
        names = {
            "group_name": _single_value(problem.group_name for problem in code_problems),
            "teacher_name": _single_value(problem.teacher_name for problem in code_problems),
            "room_name": _single_value(problem.room_name for problem in code_problems),
        }
        names[PROBLEM_SUBJECT_FIELDS[code]] = ", ".join(subjects)
        result.append(
            ScheduleProblem(
                severity=code_problems[0].severity,
                code=code,
                message=_aggregated_problem_message(code_problems),
                date=_single_value(problem.date for problem in code_problems),
                week_number=_single_value(problem.week_number for problem in code_problems),
                time_slot=_single_value(problem.time_slot for problem in code_problems),
                lesson_ids=list(dict.fromkeys(lesson_ids)),
                count=len(code_problems),
                **names,
            )
        )
    return result


def _problem_subject(problem: ScheduleProblem) -> str | None:
    """The entity this problem is listed by inside its aggregated notification."""
    field_name = PROBLEM_SUBJECT_FIELDS.get(problem.code)
    return getattr(problem, field_name) if field_name else None


def _aggregated_problem_message(problems: list[ScheduleProblem]) -> str:
    code = problems[0].code
    header = _aggregated_problem_header(code)
    lines = [_aggregated_problem_line(problem) for problem in problems]
    return "\n".join([header, *lines])


def _aggregated_problem_header(code: str) -> str:
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
        "absent_teacher_scheduled": "Перечисленные преподаватели отсутствуют, но стоят в расписании:",
        "teacher_double_booked": "Перечисленные преподаватели стоят у двух групп в одну пару:",
        "excluded_room_scheduled": "Перечисленные кабинеты исключены из расписания, но стоят в нём:",
        "room_double_booked": "Перечисленные кабинеты стоят у двух групп в одну пару:",
    }
    return headers.get(code, "Перечисленные позиции требуют внимания:")


def _aggregated_problem_line(problem: ScheduleProblem) -> str:
    subject = _problem_subject(problem) or "Без названия"
    return f"{subject}: {_aggregated_problem_detail(problem)}"


def _aggregated_problem_detail(problem: ScheduleProblem) -> str:
    if problem.code in {"group_week_limit_exceeded", "group_day_limit_exceeded"}:
        return problem.message.split(": ", 1)[1] if ": " in problem.message else problem.message
    if problem.code == "group_day_minimum_not_met":
        return f"{_problem_location(problem)}меньше {MIN_GROUP_DAY_LESSONS} пар."
    if problem.code == "group_day_window":
        return _problem_location(problem).removesuffix(". ")
    if problem.code == "group_slot_multiple_teachers":
        return f"{_problem_location(problem)}два преподавателя."
    if problem.code in {"teacher_double_booked", "room_double_booked"}:
        return _problem_location(problem).removesuffix(". ")
    if problem.code in {"absent_teacher_scheduled", "excluded_room_scheduled"}:
        location = _problem_location(problem).removesuffix(". ")
        reason = problem.message.split("Причина: ", 1)[1].rstrip(".") if "Причина: " in problem.message else ""
        return f"{location}, причина: {reason}" if reason else location
    return problem.message


def _problem_location(problem: ScheduleProblem) -> str:
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


def _blocking_detail(problem: ScheduleProblem) -> str:
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


def _group_week_errors(session, group_id: int, week_number: int) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_for_group_and_week(session, group_id, week_number)
    group = repository.get_group_by_id(session, group_id)
    return _group_week_problems(group, week_number, lessons, lambda sid: repository.get_subject_by_id(session, sid))


def _group_week_problems(
    group: Group | None,
    week_number: int,
    lessons: list[Lesson],
    subject_lookup: SubjectLookup,
) -> list[ScheduleProblem]:
    counted_lessons = [lesson for lesson in lessons if _counts_toward_group_pair_limits(lesson, subject_lookup)]
    actual_count = _weekly_pair_count(counted_lessons)
    if actual_count <= MAX_GROUP_WEEK_LESSONS:
        return []
    overage = actual_count - MAX_GROUP_WEEK_LESSONS
    return [
        ScheduleProblem(
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


def _group_day_errors(session, group_id: int, lesson_date) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_for_group_and_date(session, group_id, lesson_date)
    group = repository.get_group_by_id(session, group_id)
    return _group_day_problems(group, lesson_date, lessons, lambda sid: repository.get_subject_by_id(session, sid))


def _group_day_problems(
    group: Group | None,
    lesson_date,
    lessons: list[Lesson],
    subject_lookup: SubjectLookup,
) -> list[ScheduleProblem]:
    if not lessons:
        return []

    group_name = group.source_name if group else None
    counted_lessons = [lesson for lesson in lessons if _counts_toward_group_pair_limits(lesson, subject_lookup)]
    lesson_ids = [lesson.id for lesson in lessons]
    counted_lesson_ids = [lesson.id for lesson in counted_lessons]
    actual_count = _daily_pair_count(counted_lessons)
    problems: list[ScheduleProblem] = []
    if actual_count > MAX_GROUP_DAY_LESSONS:
        overage = actual_count - MAX_GROUP_DAY_LESSONS
        problems.append(
            ScheduleProblem(
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
            ScheduleProblem(
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
                ScheduleProblem(
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


def _counts_toward_group_pair_limits(lesson: Lesson, subject_lookup: SubjectLookup) -> bool:
    return not _is_additional_lesson(lesson, subject_lookup) and not _is_class_hour_lesson(lesson, subject_lookup)


def _is_additional_lesson(lesson: Lesson, subject_lookup: SubjectLookup) -> bool:
    subject = subject_lookup(lesson.subject_id)
    labels = [lesson.lesson_type, subject.source_name if subject else ""]
    return any(_is_additional_lesson_label(str(label)) for label in labels if label is not None)


def _is_class_hour_lesson(lesson: Lesson, subject_lookup: SubjectLookup) -> bool:
    subject = subject_lookup(lesson.subject_id)
    labels = [lesson.lesson_type, subject.source_name if subject else ""]
    return any(_is_class_hour_lesson_label(str(label)) for label in labels if label is not None)


@lru_cache(maxsize=1024)
def _normalized_label(label: str) -> str:
    # Pure and called once per lesson per rule pass; the linter reuses the same
    # handful of subject names / lesson types across ~100k lessons, so memoizing
    # collapses the string normalization from per-lesson to per-distinct-label.
    return "".join(character for character in label.casefold() if character.isalnum())


def _is_additional_lesson_label(label: str) -> bool:
    normalized = _normalized_label(label)
    return normalized.startswith("доп") and "занят" in normalized


def _is_class_hour_lesson_label(label: str) -> bool:
    return _normalized_label(label) == "классныйчас"


def _group_slot_teacher_errors(session, group_id: int, lesson_date) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_for_group_and_date(session, group_id, lesson_date)
    group = repository.get_group_by_id(session, group_id)
    return _group_slot_teacher_problems(
        group, lesson_date, lessons, lambda sid: repository.get_subject_by_id(session, sid)
    )


def _group_slot_teacher_problems(
    group: Group | None,
    lesson_date,
    lessons: list[Lesson],
    subject_lookup: SubjectLookup,
) -> list[ScheduleProblem]:
    problems: list[ScheduleProblem] = []
    lessons_by_slot: dict[int, list[Lesson]] = {}
    for lesson in lessons:
        lessons_by_slot.setdefault(lesson.time_slot, []).append(lesson)
    for slot, slot_lessons in lessons_by_slot.items():
        teacher_ids = {lesson.teacher_id for lesson in slot_lessons if lesson.teacher_id is not None}
        if len(teacher_ids) <= 1:
            continue
        if _is_foreign_language_subgroup_split(slot_lessons, subject_lookup):
            continue
        problems.append(
            ScheduleProblem(
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


def _is_foreign_language_subgroup_split(lessons: list[Lesson], subject_lookup: SubjectLookup) -> bool:
    if len(lessons) < 2 or any(lesson.subgroup <= 0 for lesson in lessons):
        return False
    subjects = [subject_lookup(lesson.subject_id) for lesson in lessons]
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


def _warnings_for_lesson(session, lesson: Lesson) -> list[ScheduleProblem]:
    warnings = _double_booked_teacher_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot)
    warnings.extend(_double_booked_room_warnings(session, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot))
    lesson_warnings = []
    for warning in warnings:
        if lesson.id in warning.lesson_ids:
            lesson_warnings.append(warning)
    return lesson_warnings


def _absent_teacher_errors(session) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_with_teacher(session)
    # Preload absences and teachers once instead of a per-lesson absence query.
    absences_by_teacher = teacher_absences_by_teacher(session)
    teachers_by_id = {teacher.id: teacher for teacher in repository.get_all_teachers(session)}
    problems: list[ScheduleProblem] = []
    for lesson in lessons:
        if lesson.teacher_id is None:
            continue
        absence = next(
            (
                candidate
                for candidate in absences_by_teacher.get(lesson.teacher_id, [])
                if absence_matches_slot(candidate, lesson_date=lesson.lesson_date, time_slot=lesson.time_slot)
            ),
            None,
        )
        if absence is None:
            continue
        teacher = teachers_by_id.get(lesson.teacher_id)
        reason_suffix = f" Причина: {absence.reason}." if absence.reason else ""
        problems.append(
            ScheduleProblem(
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


def _excluded_room_errors(session) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_with_room(session)
    rooms_by_id = {room.id: room for room in repository.get_all_rooms(session)}
    problems: list[ScheduleProblem] = []
    for lesson in lessons:
        if lesson.room_id is None:
            continue
        room = rooms_by_id.get(lesson.room_id)
        if room is None or not room.is_excluded:
            continue
        reason_suffix = f" Причина: {room.exclusion_reason}." if room.exclusion_reason else ""
        problems.append(
            ScheduleProblem(
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


def _double_booked_teacher_warnings(session, *, lesson_date=None, time_slot: int | None = None) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_with_teacher(session, lesson_date=lesson_date, time_slot=time_slot)
    teachers_by_id = {teacher.id: teacher for teacher in repository.get_all_teachers(session)}
    grouped: dict[tuple[int, object, int], list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault((lesson.teacher_id, lesson.lesson_date, lesson.time_slot), []).append(lesson)

    warnings: list[ScheduleProblem] = []
    for (teacher_id, date_value, slot), slot_lessons in grouped.items():
        group_ids = {lesson.group_id for lesson in slot_lessons}
        if len(group_ids) <= 1:
            continue
        teacher = teachers_by_id.get(teacher_id)
        warnings.append(
            ScheduleProblem(
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


def _double_booked_room_warnings(session, *, lesson_date=None, time_slot: int | None = None) -> list[ScheduleProblem]:
    lessons = repository.get_lessons_with_room(session, lesson_date=lesson_date, time_slot=time_slot)
    rooms_by_id = {room.id: room for room in repository.get_all_rooms(session)}
    grouped: dict[tuple[int, object, int], list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault((lesson.room_id, lesson.lesson_date, lesson.time_slot), []).append(lesson)

    warnings: list[ScheduleProblem] = []
    for (room_id, date_value, slot), slot_lessons in grouped.items():
        group_ids = {lesson.group_id for lesson in slot_lessons}
        if len(group_ids) <= 1:
            continue
        room = rooms_by_id.get(room_id)
        warnings.append(
            ScheduleProblem(
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
