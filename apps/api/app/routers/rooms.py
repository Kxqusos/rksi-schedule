from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.room import RoomCreateRequest, RoomExclusionRequest, RoomResponse
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.rooms import (
    DuplicateRoomError,
    RoomNotFoundError,
    create_room,
    delete_room,
    exclude_room,
    list_rooms,
    restore_room,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomResponse])
def get_rooms(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [room.model_dump(mode="json") for room in list_rooms(session)]


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def post_room(
    payload: RoomCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = create_room(session, payload, actor)
    except DuplicateRoomError as exc:
        raise HTTPException(status_code=409, detail=f"room '{exc.name}' already exists") from exc
    return result.model_dump(mode="json")


@router.post("/{room_id}/exclusion", response_model=RoomResponse)
def post_room_exclusion(
    room_id: int,
    payload: RoomExclusionRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = exclude_room(session, room_id, payload, actor)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    return result.model_dump(mode="json")


@router.delete("/{room_id}/exclusion", response_model=RoomResponse)
def delete_room_exclusion(
    room_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = restore_room(session, room_id, actor)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    return result.model_dump(mode="json")


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_room(
    room_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_room(session, room_id, actor)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
