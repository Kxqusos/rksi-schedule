from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditLog, Lesson, Room
from app.schemas.room import RoomCreateRequest, RoomExclusionRequest, RoomResponse
from app.services.auth.permissions import Actor


class DuplicateRoomError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class RoomNotFoundError(Exception):
    pass


def list_rooms(session) -> list[RoomResponse]:
    lesson_counts = dict(
        session.execute(select(Lesson.room_id, func.count(Lesson.id)).group_by(Lesson.room_id)).all()
    )
    rooms = session.scalars(select(Room).order_by(Room.source_name)).all()
    return [_room_response(room, int(lesson_counts.get(room.id, 0))) for room in rooms]


def create_room(session, payload: RoomCreateRequest, actor: Actor) -> RoomResponse:
    name = payload.name.strip()
    if not name:
        raise DuplicateRoomError(payload.name)

    existing = session.scalar(select(Room).where(Room.source_name == name))
    if existing is not None:
        raise DuplicateRoomError(name)

    room = Room(source_name=name)
    session.add(room)
    session.flush()
    _audit(session, action="create", room=room, actor=actor, payload={"name": name})
    return _room_response(room, 0)


def delete_room(session, room_id: int, actor: Actor) -> None:
    room = session.get(Room, room_id)
    if room is None:
        raise RoomNotFoundError()

    lessons = session.scalars(select(Lesson).where(Lesson.room_id == room.id)).all()
    for lesson in lessons:
        lesson.room_id = None

    _audit(
        session,
        action="delete",
        room=room,
        actor=actor,
        payload={"name": room.source_name, "unassigned_lesson_count": len(lessons)},
    )
    session.delete(room)


def exclude_room(session, room_id: int, payload: RoomExclusionRequest, actor: Actor) -> RoomResponse:
    room = session.get(Room, room_id)
    if room is None:
        raise RoomNotFoundError()

    room.is_excluded = True
    room.exclusion_reason = payload.reason.strip()
    session.flush()
    lesson_count = session.scalar(select(func.count(Lesson.id)).where(Lesson.room_id == room.id)) or 0
    _audit(
        session,
        action="exclude",
        room=room,
        actor=actor,
        payload={"name": room.source_name, "reason": room.exclusion_reason},
    )
    return _room_response(room, int(lesson_count))


def restore_room(session, room_id: int, actor: Actor) -> RoomResponse:
    room = session.get(Room, room_id)
    if room is None:
        raise RoomNotFoundError()

    previous_reason = room.exclusion_reason
    room.is_excluded = False
    room.exclusion_reason = ""
    session.flush()
    lesson_count = session.scalar(select(func.count(Lesson.id)).where(Lesson.room_id == room.id)) or 0
    _audit(
        session,
        action="restore",
        room=room,
        actor=actor,
        payload={"name": room.source_name, "previous_reason": previous_reason},
    )
    return _room_response(room, int(lesson_count))


def _room_response(room: Room, lesson_count: int) -> RoomResponse:
    return RoomResponse(
        id=room.id,
        name=room.source_name,
        building=_room_building(room.source_name),
        lesson_count=lesson_count,
        is_excluded=room.is_excluded,
        exclusion_reason=room.exclusion_reason,
    )


def _room_building(room_name: str) -> str:
    parts = [part for part in room_name.split("/") if part]
    if len(parts) >= 2 and parts[-1].isdigit():
        return f"Корпус {parts[-1]}"
    return "Без корпуса"


def _audit(session, *, action: str, room: Room, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type="room",
            entity_id=room.id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )
