from __future__ import annotations

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.db.session import get_session
from app.schemas.schedule_edit import (
    LessonCreateRequest,
    LessonMutationResponse,
    LessonUpdateRequest,
    PublicScheduleIndexResponse,
    PublicScheduleWeekResponse,
    ScheduleProblemResponse,
    ScheduleSlotRoomResponse,
)
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.schedule_editor import ConflictError, LessonNotFoundError, mappers
from app.services.schedule_editor import create_lesson as create_lesson_service
from app.services.schedule_editor import delete_lesson as delete_lesson_service
from app.services.schedule_editor.service import (
    CacheKey,
    get_latest_public_week,
    get_latest_week_number,
    get_public_schedule_index,
    get_public_week_for_entity,
    list_lessons_by_slot,
    list_schedule_problems,
)
from app.services.schedule_editor import update_lesson as update_lesson_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _invalidate(cache_keys: list[CacheKey]) -> None:
    """Invalidate exactly the per-entity keys the mutation touched, plus the
    single global latest-week key (still served for the default view)."""
    cache = get_cache()
    for entity_type, entity_id, week in cache_keys:
        cache.invalidate(entity_type, entity_id, week)
    cache.invalidate("latest", 0, 0)


def _public_entity_week(session: Session, entity_type: str, entity_id: int, week: int | None) -> dict:
    week_number = week if week is not None else get_latest_week_number(session)
    if week_number is None:
        return PublicScheduleWeekResponse().model_dump(mode="json")
    return get_cache().get_or_set(
        entity_type,
        entity_id,
        week_number,
        lambda: mappers.schedule_week_view_to_response(
            get_public_week_for_entity(session, entity_type, entity_id, week_number)
        ).model_dump(mode="json"),
    )


@router.get("/public/latest-week", response_model=PublicScheduleWeekResponse)
def get_public_latest_week(session: Annotated[Session, Depends(get_session)]) -> dict:
    cache = get_cache()
    return cache.get_or_set(
        "latest", 0, 0,
        lambda: mappers.schedule_week_view_to_response(get_latest_public_week(session)).model_dump(mode="json"),
    )


@router.get("/public/index", response_model=PublicScheduleIndexResponse)
def get_public_index(session: Annotated[Session, Depends(get_session)]) -> dict:
    return mappers.schedule_index_view_to_response(get_public_schedule_index(session)).model_dump(mode="json")


@router.get("/public/by-group", response_model=PublicScheduleWeekResponse)
def get_public_by_group(
    group_id: int,
    session: Annotated[Session, Depends(get_session)],
    week: int | None = None,
) -> dict:
    return _public_entity_week(session, "group", group_id, week)


@router.get("/public/by-teacher", response_model=PublicScheduleWeekResponse)
def get_public_by_teacher(
    teacher_id: int,
    session: Annotated[Session, Depends(get_session)],
    week: int | None = None,
) -> dict:
    return _public_entity_week(session, "teacher", teacher_id, week)


@router.get("/public/by-room", response_model=PublicScheduleWeekResponse)
def get_public_by_room(
    room_id: int,
    session: Annotated[Session, Depends(get_session)],
    week: int | None = None,
) -> dict:
    return _public_entity_week(session, "room", room_id, week)


@router.get("/lessons", response_model=list[ScheduleSlotRoomResponse])
def get_lessons(
    date: Date,
    time_slot: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.slot_room_view_to_response(row).model_dump(mode="json")
        for row in list_lessons_by_slot(session, lesson_date=date, time_slot=time_slot)
    ]


@router.get("/problems", response_model=list[ScheduleProblemResponse])
def get_problems(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.schedule_problem_to_response(problem).model_dump(mode="json")
        for problem in list_schedule_problems(session)
    ]


@router.post("/lessons", response_model=LessonMutationResponse, status_code=status.HTTP_201_CREATED)
def create_lesson(
    payload: LessonCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = create_lesson_service(
                session,
                group_name=payload.group_name,
                course=payload.course,
                faculty=payload.faculty,
                subject=payload.subject,
                source_teacher_id=payload.teacher_id,
                teacher_name=payload.teacher_name,
                teacher_post=payload.teacher_post,
                room_name=payload.room_name,
                lesson_date=payload.date,
                time_start=payload.time_start,
                time_end=payload.time_end,
                weekday=payload.weekday,
                week_number=payload.week_number,
                time_slot=payload.time_slot,
                subgroup=payload.subgroup,
                lesson_type=payload.lesson_type,
                audit_payload=payload.model_dump(mode="json"),
                actor=actor,
            )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    _invalidate(result.cache_keys)
    return {
        **mappers.lesson_view_to_response(result.lesson).model_dump(mode="json"),
        "warnings": [mappers.schedule_problem_to_response(warning).model_dump(mode="json") for warning in result.warnings],
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
            result = update_lesson_service(
                session,
                lesson_id,
                group_name=payload.group_name,
                course=payload.course,
                faculty=payload.faculty,
                subject=payload.subject,
                source_teacher_id=payload.teacher_id,
                teacher_name=payload.teacher_name,
                teacher_post=payload.teacher_post,
                room_name=payload.room_name,
                lesson_date=payload.date,
                time_start=payload.time_start,
                time_end=payload.time_end,
                weekday=payload.weekday,
                week_number=payload.week_number,
                time_slot=payload.time_slot,
                subgroup=payload.subgroup,
                lesson_type=payload.lesson_type,
                changed_fields=payload.model_fields_set,
                audit_payload=payload.model_dump(mode="json", exclude_unset=True),
                actor=actor,
            )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    _invalidate(result.cache_keys)
    return {
        **mappers.lesson_view_to_response(result.lesson).model_dump(mode="json"),
        "warnings": [mappers.schedule_problem_to_response(warning).model_dump(mode="json") for warning in result.warnings],
    }


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(
    lesson_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            cache_keys = delete_lesson_service(session, lesson_id, actor)
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    _invalidate(cache_keys)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
