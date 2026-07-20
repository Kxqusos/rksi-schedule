from __future__ import annotations

from app.models import AuditLog, Room
from app.services.auth.permissions import Actor
from app.services.rooms import repository


class DuplicateRoomError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class RoomNotFoundError(Exception):
    pass


def list_rooms(session) -> list[tuple[Room, int]]:
    lesson_counts = repository.get_room_lesson_counts(session)
    rooms = repository.get_all_rooms(session)
    return [(room, int(lesson_counts.get(room.id, 0))) for room in rooms]


def create_room(session, name: str, actor: Actor) -> Room:
    name = name.strip()
    if not name:
        raise DuplicateRoomError(name)
    if repository.find_room_by_name(session, name) is not None:
        raise DuplicateRoomError(name)

    room = Room(source_name=name)
    session.add(room)
    session.flush()
    _audit(session, action="create", room=room, actor=actor, payload={"name": name})
    return room


def delete_room(session, room_id: int, actor: Actor) -> None:
    room = repository.get_room_by_id(session, room_id)
    if room is None:
        raise RoomNotFoundError()

    lessons = repository.get_lessons_for_room(session, room_id)
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


def exclude_room(session, room_id: int, reason: str, actor: Actor) -> tuple[Room, int]:
    room = repository.get_room_by_id(session, room_id)
    if room is None:
        raise RoomNotFoundError()

    room.is_excluded = True
    room.exclusion_reason = reason.strip()
    session.flush()
    lesson_count = repository.get_room_lesson_count(session, room_id)
    _audit(
        session,
        action="exclude",
        room=room,
        actor=actor,
        payload={"name": room.source_name, "reason": room.exclusion_reason},
    )
    return room, lesson_count


def restore_room(session, room_id: int, actor: Actor) -> tuple[Room, int]:
    room = repository.get_room_by_id(session, room_id)
    if room is None:
        raise RoomNotFoundError()

    previous_reason = room.exclusion_reason
    room.is_excluded = False
    room.exclusion_reason = ""
    session.flush()
    lesson_count = repository.get_room_lesson_count(session, room_id)
    _audit(
        session,
        action="restore",
        room=room,
        actor=actor,
        payload={"name": room.source_name, "previous_reason": previous_reason},
    )
    return room, lesson_count


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
