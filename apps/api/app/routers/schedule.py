from __future__ import annotations

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.schedule_edit import LessonCreateRequest, LessonUpdateRequest
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.schedule_editor import ConflictError, LessonNotFoundError
from app.services.schedule_editor import create_lesson as create_lesson_service
from app.services.schedule_editor import delete_lesson as delete_lesson_service
from app.services.schedule_editor.service import list_lessons_by_slot, list_schedule_problems
from app.services.schedule_editor import update_lesson as update_lesson_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/lessons")
def get_lessons(
    request: Request,
    date: Date,
    time_slot: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [
            lesson.model_dump(mode="json")
            for lesson in list_lessons_by_slot(session, lesson_date=date, time_slot=time_slot)
        ]


@router.get("/problems")
def get_problems(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [problem.model_dump(mode="json") for problem in list_schedule_problems(session)]


@router.post("/lessons", status_code=status.HTTP_201_CREATED)
def create_lesson(
    request: Request,
    payload: LessonCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = create_lesson_service(session, payload, actor)
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.detail) from exc
    return {
        **result.lesson.model_dump(mode="json"),
        "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
    }


@router.patch("/lessons/{lesson_id}")
def update_lesson(
    request: Request,
    lesson_id: int,
    payload: LessonUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = update_lesson_service(session, lesson_id, payload, actor)
        except LessonNotFoundError as exc:
            raise HTTPException(status_code=404, detail="lesson not found") from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.detail) from exc
    return {
        **result.lesson.model_dump(mode="json"),
        "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
    }


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(
    request: Request,
    lesson_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> Response:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                delete_lesson_service(session, lesson_id, actor)
        except LessonNotFoundError as exc:
            raise HTTPException(status_code=404, detail="lesson not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
