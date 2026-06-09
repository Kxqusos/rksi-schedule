from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.teacher import TeacherCreateRequest
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.teachers import (
    DuplicateTeacherError,
    TeacherNotFoundError,
    create_teacher,
    delete_teacher,
    list_teachers,
)

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("")
def get_teachers(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [teacher.model_dump(mode="json") for teacher in list_teachers(session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def post_teacher(
    request: Request,
    payload: TeacherCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = create_teacher(session, payload, actor)
        except DuplicateTeacherError as exc:
            raise HTTPException(status_code=409, detail=f"teacher '{exc.teacher_id}' already exists") from exc
    return result.model_dump(mode="json")


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_teacher(
    request: Request,
    teacher_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> Response:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                delete_teacher(session, teacher_id, actor)
        except TeacherNotFoundError as exc:
            raise HTTPException(status_code=404, detail="teacher not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
