from __future__ import annotations

from sqlalchemy import func, select

from app.models import Group, Lesson, Subject, Teacher


def get_all_groups(session) -> list[Group]:
    return session.scalars(select(Group).order_by(Group.source_name)).all()


def get_group_lesson_counts(session) -> dict[int, int]:
    return dict(
        session.execute(select(Lesson.group_id, func.count(Lesson.id)).group_by(Lesson.group_id)).all()
    )


def get_teachers_by_id(session) -> dict[int, Teacher]:
    return {teacher.id: teacher for teacher in session.scalars(select(Teacher)).all()}


def get_group_by_id(session, group_id: int) -> Group | None:
    return session.get(Group, group_id)


def find_group_by_name(session, name: str, *, exclude_id: int | None = None) -> Group | None:
    stmt = select(Group).where(Group.source_name == name)
    if exclude_id is not None:
        stmt = stmt.where(Group.id != exclude_id)
    return session.scalar(stmt)


def get_lessons_for_group(session, group_id: int) -> list[Lesson]:
    return session.scalars(select(Lesson).where(Lesson.group_id == group_id)).all()


def get_group_lesson_count(session, group_id: int) -> int:
    return session.scalar(select(func.count(Lesson.id)).where(Lesson.group_id == group_id)) or 0


def get_teacher_by_id(session, teacher_id: int) -> Teacher | None:
    return session.get(Teacher, teacher_id)


def get_class_hour_subject_id(session) -> int | None:
    return session.scalar(select(Subject.id).where(Subject.source_name == "Классный час"))


def get_class_hour_lessons(session, group_id: int, subject_id: int) -> list[Lesson]:
    return session.scalars(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.subject_id == subject_id)
    ).all()


def get_groups_by_homeroom_teacher(session, teacher_id: int) -> list[Group]:
    return session.scalars(select(Group).where(Group.homeroom_teacher_id == teacher_id)).all()
