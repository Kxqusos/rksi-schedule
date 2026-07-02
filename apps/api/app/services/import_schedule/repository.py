from __future__ import annotations

from sqlalchemy import select

from app.models import Group, Lesson, Room, Subject, Teacher


def find_lesson_by_source_id(session, source_lesson_id: str) -> Lesson | None:
    return session.scalar(select(Lesson).where(Lesson.source_lesson_id == source_lesson_id))


def get_teacher_by_id(session, teacher_id: int) -> Teacher | None:
    return session.get(Teacher, teacher_id)


def find_group_by_name(session, name: str) -> Group | None:
    return session.scalar(select(Group).where(Group.source_name == name))


def find_subject_by_name(session, name: str) -> Subject | None:
    return session.scalar(select(Subject).where(Subject.source_name == name))


def find_teacher_by_source_id(session, source_teacher_id: str) -> Teacher | None:
    return session.scalar(select(Teacher).where(Teacher.source_teacher_id == source_teacher_id))


def find_room_by_name(session, name: str) -> Room | None:
    return session.scalar(select(Room).where(Room.source_name == name))
