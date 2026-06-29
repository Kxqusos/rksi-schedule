from __future__ import annotations

from app.models import Teacher, TeacherAbsence
from app.schemas.teacher import TeacherAbsenceResponse, TeacherResponse


def teacher_to_response(teacher: Teacher, lesson_count: int, absences: list[TeacherAbsence]) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        teacher_id=teacher.source_teacher_id,
        name=teacher.source_name,
        post=teacher.post,
        lesson_count=lesson_count,
        absences=[absence_to_response(absence) for absence in absences],
    )


def absence_to_response(absence: TeacherAbsence) -> TeacherAbsenceResponse:
    return TeacherAbsenceResponse(
        id=absence.id,
        date=absence.absence_date,
        all_day=absence.all_day,
        time_slot_start=absence.time_slot_start,
        time_slot_end=absence.time_slot_end,
        reason=absence.reason,
    )
