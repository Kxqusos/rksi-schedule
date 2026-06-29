from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.models import Lesson, Teacher, TeacherAbsence


def get_all_teachers(session) -> list[Teacher]:
    return session.scalars(select(Teacher).order_by(Teacher.source_name)).all()


def get_teacher_lesson_counts(session) -> dict[int, int]:
    return dict(
        session.execute(select(Lesson.teacher_id, func.count(Lesson.id)).group_by(Lesson.teacher_id)).all()
    )


def get_absences_by_teacher(session) -> dict[int, list[TeacherAbsence]]:
    absences = session.scalars(
        select(TeacherAbsence).order_by(TeacherAbsence.absence_date.desc(), TeacherAbsence.time_slot_start)
    ).all()
    grouped: dict[int, list[TeacherAbsence]] = {}
    for absence in absences:
        grouped.setdefault(absence.teacher_id, []).append(absence)
    return grouped


def get_teacher_by_id(session, teacher_id: int) -> Teacher | None:
    return session.get(Teacher, teacher_id)


def find_teacher_by_source_id(session, source_teacher_id: str) -> Teacher | None:
    return session.scalar(select(Teacher).where(Teacher.source_teacher_id == source_teacher_id))


def get_lessons_for_teacher(session, teacher_id: int) -> list[Lesson]:
    return session.scalars(select(Lesson).where(Lesson.teacher_id == teacher_id)).all()


def get_absences_for_teacher(session, teacher_id: int) -> list[TeacherAbsence]:
    return session.scalars(select(TeacherAbsence).where(TeacherAbsence.teacher_id == teacher_id)).all()


def get_absence_by_id(session, absence_id: int) -> TeacherAbsence | None:
    return session.get(TeacherAbsence, absence_id)


def get_absence_for_slot(session, *, teacher_id: int, lesson_date: date, time_slot: int) -> TeacherAbsence | None:
    return session.scalar(
        select(TeacherAbsence)
        .where(
            TeacherAbsence.teacher_id == teacher_id,
            TeacherAbsence.absence_date == lesson_date,
            TeacherAbsence.time_slot_start <= time_slot,
            TeacherAbsence.time_slot_end >= time_slot,
        )
        .limit(1)
    )
