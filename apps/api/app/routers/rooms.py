from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.room import RoomCreateRequest
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.rooms import (
    DuplicateRoomError,
    RoomNotFoundError,
    create_room,
    delete_room,
    list_rooms,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("")
def get_rooms(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [room.model_dump(mode="json") for room in list_rooms(session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def post_room(
    request: Request,
    payload: RoomCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = create_room(session, payload, actor)
        except DuplicateRoomError as exc:
            raise HTTPException(status_code=409, detail=f"room '{exc.name}' already exists") from exc
    return result.model_dump(mode="json")


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_room(
    request: Request,
    room_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> Response:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                delete_room(session, room_id, actor)
        except RoomNotFoundError as exc:
            raise HTTPException(status_code=404, detail="room not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
