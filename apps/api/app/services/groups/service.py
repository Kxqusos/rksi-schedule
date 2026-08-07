from __future__ import annotations

from app.models import AuditLog, Group, Teacher
from app.services.auth.permissions import Actor
from app.services.groups import repository


class DuplicateGroupError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class GroupNotFoundError(Exception):
    pass


class HomeroomTeacherNotFoundError(Exception):
    pass


def list_groups(session) -> list[tuple[Group, int, Teacher | None]]:
    lesson_counts = repository.get_group_lesson_counts(session)
    teachers = repository.get_teachers_by_id(session)
    groups = repository.get_all_groups(session)
    return [
        (group, int(lesson_counts.get(group.id, 0)), teachers.get(group.homeroom_teacher_id))
        for group in groups
    ]


def update_group(session, group_id: int, name: str, actor: Actor) -> tuple[Group, int, Teacher | None]:
    group = repository.get_group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError()

    stripped_name = name.strip()
    if not stripped_name:
        raise DuplicateGroupError(name)
    if repository.find_group_by_name(session, stripped_name, exclude_id=group.id) is not None:
        raise DuplicateGroupError(stripped_name)

    old_name = group.source_name
    group.source_name = stripped_name
    session.flush()
    lesson_count = repository.get_group_lesson_count(session, group.id)
    teacher = repository.get_teacher_by_id(session, group.homeroom_teacher_id) if group.homeroom_teacher_id else None
    _audit(session, action="rename", group=group, actor=actor, payload={"old_name": old_name, "name": stripped_name})
    return group, lesson_count, teacher


def set_homeroom_teacher(session, group_id: int, teacher_id: int | None, actor: Actor) -> tuple[Group, int, Teacher | None]:
    group = repository.get_group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError()

    teacher = None
    if teacher_id is not None:
        teacher = repository.get_teacher_by_id(session, teacher_id)
        if teacher is None:
            raise HomeroomTeacherNotFoundError()

    group.homeroom_teacher_id = teacher.id if teacher else None
    _update_class_hours(session, group, teacher)
    session.flush()
    lesson_count = repository.get_group_lesson_count(session, group.id)
    _audit(
        session,
        action="set_homeroom_teacher",
        group=group,
        actor=actor,
        payload={
            "group_name": group.source_name,
            "teacher_id": teacher.id if teacher else None,
            "teacher_name": teacher.source_name if teacher else None,
        },
    )
    return group, lesson_count, teacher


def delete_group(session, group_id: int, actor: Actor) -> None:
    group = repository.get_group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError()

    lessons = repository.get_lessons_for_group(session, group_id)
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


def clear_homeroom_teacher(session, teacher_id: int, *, teacher_name: str, actor: Actor) -> int:
    groups = repository.get_groups_by_homeroom_teacher(session, teacher_id)
    for group in groups:
        group.homeroom_teacher_id = None
        _audit(
            session,
            action="clear_homeroom_teacher",
            group=group,
            actor=actor,
            payload={"group_name": group.source_name, "teacher_name": teacher_name},
        )
    return len(groups)


def _update_class_hours(session, group: Group, teacher: Teacher | None) -> None:
    subject_id = repository.get_class_hour_subject_id(session)
    if subject_id is None:
        return
    for lesson in repository.get_class_hour_lessons(session, group.id, subject_id):
        lesson.teacher_id = teacher.id if teacher else None


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
