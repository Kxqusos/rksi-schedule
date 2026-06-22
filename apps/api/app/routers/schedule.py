from __future__ import annotations

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.schedule_edit import (
    LessonCreateRequest,
    LessonMutationResponse,
    LessonUpdateRequest,
    PublicScheduleWeekResponse,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.schedule_editor import ConflictError, LessonNotFoundError
from app.services.schedule_editor import create_lesson as create_lesson_service
from app.services.schedule_editor import delete_lesson as delete_lesson_service
from app.services.schedule_editor.service import get_latest_public_week, list_lessons_by_slot, list_schedule_problems
from app.services.schedule_editor import update_lesson as update_lesson_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/public/latest-week", response_model=PublicScheduleWeekResponse)
def get_public_latest_week(session: Annotated[Session, Depends(get_session)]) -> dict:
    return get_latest_public_week(session).model_dump(mode="json")


@router.get("/lessons", response_model=list[ScheduleSlotRoomResponse])
def get_lessons(
    date: Date,
    time_slot: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        lesson.model_dump(mode="json")
        for lesson in list_lessons_by_slot(session, lesson_date=date, time_slot=time_slot)
    ]


@router.get("/problems", response_model=list[ScheduleProblemResponse])
def get_problems(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [problem.model_dump(mode="json") for problem in list_schedule_problems(session)]


@router.post("/lessons", response_model=LessonMutationResponse, status_code=status.HTTP_201_CREATED)
def create_lesson(
    payload: LessonCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = create_lesson_service(session, payload, actor)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    return {
        **result.lesson.model_dump(mode="json"),
        "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
    }


@router.patch("/lessons/{lesson_id}", response_model=LessonMutationResponse)
def update_lesson(
    lesson_id: int,
    payload: LessonUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
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
    lesson_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_lesson_service(session, lesson_id, actor)
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
