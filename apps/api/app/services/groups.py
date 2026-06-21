from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditLog, Group, Lesson, Subject, Teacher
from app.schemas.group import GroupHomeroomTeacherRequest, GroupResponse, GroupUpdateRequest
from app.services.auth.permissions import Actor

CLASS_HOUR_SUBJECT = "Классный час"


class DuplicateGroupError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class GroupNotFoundError(Exception):
    pass


class HomeroomTeacherNotFoundError(Exception):
    pass


def list_groups(session) -> list[GroupResponse]:
    lesson_counts = dict(
        session.execute(select(Lesson.group_id, func.count(Lesson.id)).group_by(Lesson.group_id)).all()
    )
    teachers = {teacher.id: teacher for teacher in session.scalars(select(Teacher)).all()}
    groups = session.scalars(select(Group).order_by(Group.source_name)).all()
    return [_group_response(group, int(lesson_counts.get(group.id, 0)), teachers.get(group.homeroom_teacher_id)) for group in groups]


def update_group(session, group_id: int, payload: GroupUpdateRequest, actor: Actor) -> GroupResponse:
    group = session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError()

    name = payload.name.strip()
    if not name:
        raise DuplicateGroupError(payload.name)
    existing = session.scalar(select(Group).where(Group.source_name == name, Group.id != group.id))
    if existing is not None:
        raise DuplicateGroupError(name)

    old_name = group.source_name
    group.source_name = name
    session.flush()
    lesson_count = session.scalar(select(func.count(Lesson.id)).where(Lesson.group_id == group.id)) or 0
    teacher = session.get(Teacher, group.homeroom_teacher_id) if group.homeroom_teacher_id else None
    _audit(session, action="rename", group=group, actor=actor, payload={"old_name": old_name, "name": name})
    return _group_response(group, int(lesson_count), teacher)


def set_homeroom_teacher(session, group_id: int, payload: GroupHomeroomTeacherRequest, actor: Actor) -> GroupResponse:
    group = session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError()

    teacher = None
    if payload.teacher_id is not None:
        teacher = session.get(Teacher, payload.teacher_id)
        if teacher is None:
            raise HomeroomTeacherNotFoundError()

    group.homeroom_teacher_id = teacher.id if teacher else None
    _update_class_hours(session, group, teacher)
    session.flush()
    lesson_count = session.scalar(select(func.count(Lesson.id)).where(Lesson.group_id == group.id)) or 0
    _audit(
        session,
        action="set_homeroom_teacher",
        group=group,
        actor=actor,
        payload={"teacher_id": teacher.id if teacher else None, "teacher_name": teacher.source_name if teacher else None},
    )
    return _group_response(group, int(lesson_count), teacher)


def delete_group(session, group_id: int, actor: Actor) -> None:
    group = session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError()

    lessons = session.scalars(select(Lesson).where(Lesson.group_id == group.id)).all()
    for lesson in lessons:
        session.delete(lesson)
    _audit(
        session,
        action="delete",
        group=group,
        actor=actor,
        payload={"name": group.source_name, "deleted_lesson_count": len(lessons)},
    )
    session.delete(group)


def clear_homeroom_teacher(session, teacher_id: int) -> int:
    groups = session.scalars(select(Group).where(Group.homeroom_teacher_id == teacher_id)).all()
    for group in groups:
        group.homeroom_teacher_id = None
    return len(groups)


def _update_class_hours(session, group: Group, teacher: Teacher | None) -> None:
    class_hour_subject_id = session.scalar(select(Subject.id).where(Subject.source_name == CLASS_HOUR_SUBJECT))
    if class_hour_subject_id is None:
        return
    lessons = session.scalars(
        select(Lesson).where(
            Lesson.group_id == group.id,
            Lesson.subject_id == class_hour_subject_id,
        )
    ).all()
    for lesson in lessons:
        lesson.teacher_id = teacher.id if teacher else None


def _group_response(group: Group, lesson_count: int, teacher: Teacher | None) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.source_name,
        course=group.course,
        faculty=group.faculty,
        lesson_count=lesson_count,
        homeroom_teacher_id=teacher.id if teacher else None,
        homeroom_teacher_name=teacher.source_name if teacher else None,
    )


def _audit(session, *, action: str, group: Group, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type="group",
            entity_id=group.id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )
