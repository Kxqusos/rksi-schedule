from __future__ import annotations

from datetime import date

from app.models import AuditLog, Teacher, TeacherAbsence
from app.services.auth.permissions import Actor
from app.services.groups import clear_homeroom_teacher
from app.services.teachers import repository


class DuplicateTeacherError(Exception):
    def __init__(self, teacher_id: str) -> None:
        super().__init__(teacher_id)
        self.teacher_id = teacher_id


class TeacherNotFoundError(Exception):
    pass


class TeacherAbsenceNotFoundError(Exception):
    pass


def list_teachers(session) -> list[tuple[Teacher, int, list[TeacherAbsence]]]:
    lesson_counts = repository.get_teacher_lesson_counts(session)
    teachers = repository.get_all_teachers(session)
    absences_by_teacher = repository.get_absences_by_teacher(session)
    return [
        (
            teacher,
            int(lesson_counts.get(teacher.id, 0)),
            absences_by_teacher.get(teacher.id, []),
        )
        for teacher in teachers
    ]


def list_available_teachers(
    session, *, lesson_date: date, time_slot: int
) -> list[tuple[Teacher, int, list[TeacherAbsence]]]:
    return [
        (teacher, lesson_count, absences)
        for teacher, lesson_count, absences in list_teachers(session)
        if not any(
            absence.absence_date == lesson_date and absence.time_slot_start <= time_slot <= absence.time_slot_end
            for absence in absences
        )
    ]


def create_teacher(session, *, name: str, teacher_id: str | None, post: str, actor: Actor) -> Teacher:
    name = name.strip()
    source_teacher_id = (teacher_id or name).strip()
    if not name or not source_teacher_id:
        raise DuplicateTeacherError(source_teacher_id)
    if repository.find_teacher_by_source_id(session, source_teacher_id) is not None:
        raise DuplicateTeacherError(source_teacher_id)

    teacher = Teacher(source_teacher_id=source_teacher_id, source_name=name, post=post.strip())
    session.add(teacher)
    session.flush()
    _audit(session, action="create", teacher=teacher, actor=actor, payload={"teacher_id": source_teacher_id, "name": name})
    return teacher


def delete_teacher(session, teacher_id: int, actor: Actor) -> None:
    teacher = repository.get_teacher_by_id(session, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()

    lessons = repository.get_lessons_for_teacher(session, teacher_id)
    for lesson in lessons:
        lesson.teacher_id = None
    absences = repository.get_absences_for_teacher(session, teacher_id)
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


def create_teacher_absence(
    session,
    teacher_id: int,
    *,
    absence_date: date,
    all_day: bool,
    time_slot_start: int | None,
    time_slot_end: int | None,
    reason: str,
    actor: Actor,
) -> TeacherAbsence:
    teacher = repository.get_teacher_by_id(session, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()

    absence = TeacherAbsence(
        teacher_id=teacher.id,
        absence_date=absence_date,
        all_day=all_day,
        time_slot_start=time_slot_start or 1,
        time_slot_end=time_slot_end or 7,
        reason=reason.strip(),
    )
    session.add(absence)
    session.flush()
    _audit(
        session,
        action="mark_absent",
        teacher=teacher,
        actor=actor,
        payload=_absence_audit_payload(absence),
    )
    return absence


def delete_teacher_absence(session, teacher_id: int, absence_id: int, actor: Actor) -> None:
    teacher = repository.get_teacher_by_id(session, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()
    absence = repository.get_absence_by_id(session, absence_id)
    if absence is None or absence.teacher_id != teacher.id:
        raise TeacherAbsenceNotFoundError()

    _audit(
        session,
        action="clear_absence",
        teacher=teacher,
        actor=actor,
        payload=_absence_audit_payload(absence),
    )
    session.delete(absence)


def teacher_absence_for_slot(session, *, teacher_id: int, lesson_date: date, time_slot: int) -> TeacherAbsence | None:
    return repository.get_absence_for_slot(session, teacher_id=teacher_id, lesson_date=lesson_date, time_slot=time_slot)


def teacher_absences_by_teacher(session) -> dict[int, list[TeacherAbsence]]:
    """All absences grouped by teacher_id, for bulk in-memory slot matching
    (avoids a per-lesson absence query in the schedule linter)."""
    return repository.get_absences_by_teacher(session)


def absence_matches_slot(absence: TeacherAbsence, *, lesson_date: date, time_slot: int) -> bool:
    return (
        absence.absence_date == lesson_date
        and absence.time_slot_start <= time_slot
        and absence.time_slot_end >= time_slot
    )


def _absence_audit_payload(absence: TeacherAbsence) -> dict:
    return {
        "id": absence.id,
        "date": absence.absence_date.isoformat(),
        "all_day": absence.all_day,
        "time_slot_start": absence.time_slot_start,
        "time_slot_end": absence.time_slot_end,
        "reason": absence.reason,
    }


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
