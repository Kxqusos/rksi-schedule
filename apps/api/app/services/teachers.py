from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditLog, Lesson, Teacher, TeacherAbsence
from app.schemas.teacher import TeacherAbsenceCreateRequest, TeacherAbsenceResponse, TeacherCreateRequest, TeacherResponse
from app.services.auth.permissions import Actor
from app.services.groups import clear_homeroom_teacher


class DuplicateTeacherError(Exception):
    def __init__(self, teacher_id: str) -> None:
        super().__init__(teacher_id)
        self.teacher_id = teacher_id


class TeacherNotFoundError(Exception):
    pass


class TeacherAbsenceNotFoundError(Exception):
    pass


def list_teachers(session) -> list[TeacherResponse]:
    lesson_counts = dict(
        session.execute(select(Lesson.teacher_id, func.count(Lesson.id)).group_by(Lesson.teacher_id)).all()
    )
    teachers = session.scalars(select(Teacher).order_by(Teacher.source_name)).all()
    absences_by_teacher = _absences_by_teacher(session)
    return [
        _teacher_response(teacher, int(lesson_counts.get(teacher.id, 0)), absences_by_teacher.get(teacher.id, []))
        for teacher in teachers
    ]


def list_available_teachers(session, *, lesson_date, time_slot: int) -> list[TeacherResponse]:
    teachers = list_teachers(session)
    return [
        teacher
        for teacher in teachers
        if not any(
            absence.date == lesson_date and absence.time_slot_start <= time_slot <= absence.time_slot_end
            for absence in teacher.absences
        )
    ]


def create_teacher(session, payload: TeacherCreateRequest, actor: Actor) -> TeacherResponse:
    name = payload.name.strip()
    source_teacher_id = (payload.teacher_id or name).strip()
    if not name or not source_teacher_id:
        raise DuplicateTeacherError(source_teacher_id)

    existing = session.scalar(select(Teacher).where(Teacher.source_teacher_id == source_teacher_id))
    if existing is not None:
        raise DuplicateTeacherError(source_teacher_id)

    teacher = Teacher(
        source_teacher_id=source_teacher_id,
        source_name=name,
        post=payload.post.strip(),
    )
    session.add(teacher)
    session.flush()
    _audit(session, action="create", teacher=teacher, actor=actor, payload={"teacher_id": source_teacher_id, "name": name})
    return _teacher_response(teacher, 0, [])


def delete_teacher(session, teacher_id: int, actor: Actor) -> None:
    teacher = session.get(Teacher, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()

    lessons = session.scalars(select(Lesson).where(Lesson.teacher_id == teacher.id)).all()
    for lesson in lessons:
        lesson.teacher_id = None
    absences = session.scalars(select(TeacherAbsence).where(TeacherAbsence.teacher_id == teacher.id)).all()
    for absence in absences:
        session.delete(absence)
    cleared_group_count = clear_homeroom_teacher(session, teacher.id)

    _audit(
        session,
        action="delete",
        teacher=teacher,
        actor=actor,
        payload={
            "teacher_id": teacher.source_teacher_id,
            "name": teacher.source_name,
            "unassigned_lesson_count": len(lessons),
            "deleted_absence_count": len(absences),
            "cleared_group_count": cleared_group_count,
        },
    )
    session.delete(teacher)


def create_teacher_absence(session, teacher_id: int, payload: TeacherAbsenceCreateRequest, actor: Actor) -> TeacherAbsenceResponse:
    teacher = session.get(Teacher, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()

    absence = TeacherAbsence(
        teacher_id=teacher.id,
        absence_date=payload.date,
        all_day=payload.all_day,
        time_slot_start=payload.time_slot_start or 1,
        time_slot_end=payload.time_slot_end or 7,
        reason=payload.reason.strip(),
    )
    session.add(absence)
    session.flush()
    _audit(
        session,
        action="mark_absent",
        teacher=teacher,
        actor=actor,
        payload=_absence_response(absence).model_dump(mode="json"),
    )
    return _absence_response(absence)


def delete_teacher_absence(session, teacher_id: int, absence_id: int, actor: Actor) -> None:
    teacher = session.get(Teacher, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()
    absence = session.get(TeacherAbsence, absence_id)
    if absence is None or absence.teacher_id != teacher.id:
        raise TeacherAbsenceNotFoundError()

    _audit(
        session,
        action="clear_absence",
        teacher=teacher,
        actor=actor,
        payload=_absence_response(absence).model_dump(mode="json"),
    )
    session.delete(absence)


def teacher_absence_for_slot(session, *, teacher_id: int, lesson_date, time_slot: int) -> TeacherAbsence | None:
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


def _teacher_response(teacher: Teacher, lesson_count: int, absences: list[TeacherAbsence]) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        teacher_id=teacher.source_teacher_id,
        name=teacher.source_name,
        post=teacher.post,
        lesson_count=lesson_count,
        absences=[_absence_response(absence) for absence in absences],
    )


def _absence_response(absence: TeacherAbsence) -> TeacherAbsenceResponse:
    return TeacherAbsenceResponse(
        id=absence.id,
        date=absence.absence_date,
        all_day=absence.all_day,
        time_slot_start=absence.time_slot_start,
        time_slot_end=absence.time_slot_end,
        reason=absence.reason,
    )


def _absences_by_teacher(session) -> dict[int, list[TeacherAbsence]]:
    absences = session.scalars(
        select(TeacherAbsence).order_by(TeacherAbsence.absence_date.desc(), TeacherAbsence.time_slot_start)
    ).all()
    grouped: dict[int, list[TeacherAbsence]] = {}
    for absence in absences:
        grouped.setdefault(absence.teacher_id, []).append(absence)
    return grouped


def _audit(session, *, action: str, teacher: Teacher, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type="teacher",
            entity_id=teacher.id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )
