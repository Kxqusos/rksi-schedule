from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.group import GroupHomeroomTeacherRequest, GroupResponse, GroupUpdateRequest
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.groups import (
    DuplicateGroupError,
    GroupNotFoundError,
    HomeroomTeacherNotFoundError,
    delete_group,
    list_groups,
    mappers,
    set_homeroom_teacher,
    update_group,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupResponse])
def get_groups(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.group_to_response(group, lesson_count, teacher).model_dump(mode="json")
        for group, lesson_count, teacher in list_groups(session)
    ]


@router.patch("/{group_id}", response_model=GroupResponse)
def patch_group(
    group_id: int,
    payload: GroupUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            group, lesson_count, teacher = update_group(session, group_id, payload.name, actor)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail="group not found") from exc
    except DuplicateGroupError as exc:
        raise HTTPException(status_code=409, detail=f"group '{exc.name}' already exists") from exc
    return mappers.group_to_response(group, lesson_count, teacher).model_dump(mode="json")


@router.patch("/{group_id}/homeroom-teacher", response_model=GroupResponse)
def patch_group_homeroom_teacher(
    group_id: int,
    payload: GroupHomeroomTeacherRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            group, lesson_count, teacher = set_homeroom_teacher(
                session, group_id, payload.teacher_id, actor
            )
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail="group not found") from exc
    except HomeroomTeacherNotFoundError as exc:
        raise HTTPException(status_code=404, detail="teacher not found") from exc
    return mappers.group_to_response(group, lesson_count, teacher).model_dump(mode="json")


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group(
    group_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_group(session, group_id, actor)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail="group not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
