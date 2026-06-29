from __future__ import annotations

from sqlalchemy import func, select

from app.models import Lesson, Room


def get_all_rooms(session) -> list[Room]:
    return session.scalars(select(Room).order_by(Room.source_name)).all()


def get_room_lesson_counts(session) -> dict[int, int]:
    return dict(
        session.execute(select(Lesson.room_id, func.count(Lesson.id)).group_by(Lesson.room_id)).all()
    )


def get_room_by_id(session, room_id: int) -> Room | None:
    return session.get(Room, room_id)


def find_room_by_name(session, name: str) -> Room | None:
    return session.scalar(select(Room).where(Room.source_name == name))


def get_lessons_for_room(session, room_id: int) -> list[Lesson]:
    return session.scalars(select(Lesson).where(Lesson.room_id == room_id)).all()


def get_room_lesson_count(session, room_id: int) -> int:
    return session.scalar(select(func.count(Lesson.id)).where(Lesson.room_id == room_id)) or 0
