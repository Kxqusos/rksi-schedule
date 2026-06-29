from __future__ import annotations

from app.models import Room
from app.schemas.room import RoomResponse


def room_to_response(room: Room, lesson_count: int) -> RoomResponse:
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
