from __future__ import annotations

from datetime import date as Date

from app.models import Lesson, Room, TeacherAbsence
from app.schemas.schedule_edit import (
    LessonResponse,
    PublicScheduleDayResponse,
    PublicScheduleWeekResponse,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)


def lesson_to_response(
    lesson: Lesson,
    *,
    group_name: str,
    subject_name: str,
    teacher_name: str | None,
    teacher_absence: TeacherAbsence | None,
    room_name: str | None,
) -> LessonResponse:
    return LessonResponse(
        id=lesson.id,
        group_name=group_name,
        subject=subject_name,
        teacher_name=teacher_name,
        teacher_is_absent=teacher_absence is not None,
        teacher_absence_reason=teacher_absence.reason if teacher_absence else "",
        room_name=room_name,
        date=lesson.lesson_date,
        time_start=lesson.start_time,
        time_end=lesson.end_time,
        weekday=lesson.weekday,
        week_number=lesson.week_number,
        time_slot=lesson.time_slot,
        subgroup=lesson.subgroup,
        lesson_type=lesson.lesson_type,
    )


def schedule_slot_room_response(
    *,
    room_name: str,
    building: str,
    room_is_excluded: bool,
    room_exclusion_reason: str,
    lesson: LessonResponse | None,
) -> ScheduleSlotRoomResponse:
    return ScheduleSlotRoomResponse(
        room_name=room_name,
        building=building,
        room_is_excluded=room_is_excluded,
        room_exclusion_reason=room_exclusion_reason,
        lesson=lesson,
    )


def public_schedule_week_response(
    *,
    week_start: Date,
    week_end: Date,
    week_number: int | None,
    days: list[PublicScheduleDayResponse],
) -> PublicScheduleWeekResponse:
    return PublicScheduleWeekResponse(
        week_start=week_start,
        week_end=week_end,
        week_number=week_number,
        days=days,
    )


def public_schedule_day_response(
    *,
    date: Date,
    weekday: int,
    lessons: list[LessonResponse],
) -> PublicScheduleDayResponse:
    return PublicScheduleDayResponse(date=date, weekday=weekday, lessons=lessons)


def problem_to_response(
    *,
    severity: str,
    code: str,
    message: str,
    date: Date | None = None,
    week_number: int | None = None,
    time_slot: int | None = None,
    group_name: str | None = None,
    teacher_name: str | None = None,
    room_name: str | None = None,
    lesson_ids: list[int] | None = None,
) -> ScheduleProblemResponse:
    return ScheduleProblemResponse(
        severity=severity,
        code=code,
        message=message,
        date=date,
        week_number=week_number,
        time_slot=time_slot,
        group_name=group_name,
        teacher_name=teacher_name,
        room_name=room_name,
        lesson_ids=lesson_ids if lesson_ids is not None else [],
    )
