from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditLog, Lesson, Teacher
from app.schemas.teacher import TeacherCreateRequest, TeacherResponse
from app.services.auth.permissions import Actor


class DuplicateTeacherError(Exception):
    def __init__(self, teacher_id: str) -> None:
        super().__init__(teacher_id)
        self.teacher_id = teacher_id


class TeacherNotFoundError(Exception):
    pass


def list_teachers(session) -> list[TeacherResponse]:
    lesson_counts = dict(
        session.execute(select(Lesson.teacher_id, func.count(Lesson.id)).group_by(Lesson.teacher_id)).all()
    )
    teachers = session.scalars(select(Teacher).order_by(Teacher.source_name)).all()
    return [_teacher_response(teacher, int(lesson_counts.get(teacher.id, 0))) for teacher in teachers]


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
    return _teacher_response(teacher, 0)


def delete_teacher(session, teacher_id: int, actor: Actor) -> None:
    teacher = session.get(Teacher, teacher_id)
    if teacher is None:
        raise TeacherNotFoundError()

    lessons = session.scalars(select(Lesson).where(Lesson.teacher_id == teacher.id)).all()
    for lesson in lessons:
        lesson.teacher_id = None

    _audit(
        session,
        action="delete",
        teacher=teacher,
        actor=actor,
        payload={
            "teacher_id": teacher.source_teacher_id,
            "name": teacher.source_name,
            "unassigned_lesson_count": len(lessons),
        },
    )
    session.delete(teacher)


def _teacher_response(teacher: Teacher, lesson_count: int) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        teacher_id=teacher.source_teacher_id,
        name=teacher.source_name,
        post=teacher.post,
        lesson_count=lesson_count,
    )


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
