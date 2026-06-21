from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.group import GroupHomeroomTeacherRequest, GroupResponse, GroupUpdateRequest
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.groups import (
    DuplicateGroupError,
    GroupNotFoundError,
    HomeroomTeacherNotFoundError,
    delete_group,
    list_groups,
    set_homeroom_teacher,
    update_group,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupResponse])
def get_groups(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [group.model_dump(mode="json") for group in list_groups(session)]


@router.patch("/{group_id}", response_model=GroupResponse)
def patch_group(
    request: Request,
    group_id: int,
    payload: GroupUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = update_group(session, group_id, payload, actor)
        except GroupNotFoundError as exc:
            raise HTTPException(status_code=404, detail="group not found") from exc
        except DuplicateGroupError as exc:
            raise HTTPException(status_code=409, detail=f"group '{exc.name}' already exists") from exc
    return result.model_dump(mode="json")


@router.patch("/{group_id}/homeroom-teacher", response_model=GroupResponse)
def patch_group_homeroom_teacher(
    request: Request,
    group_id: int,
    payload: GroupHomeroomTeacherRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = set_homeroom_teacher(session, group_id, payload, actor)
        except GroupNotFoundError as exc:
            raise HTTPException(status_code=404, detail="group not found") from exc
        except HomeroomTeacherNotFoundError as exc:
            raise HTTPException(status_code=404, detail="teacher not found") from exc
    return result.model_dump(mode="json")


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group(
    request: Request,
    group_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> Response:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                delete_group(session, group_id, actor)
        except GroupNotFoundError as exc:
            raise HTTPException(status_code=404, detail="group not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
