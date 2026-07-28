from __future__ import annotations

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.teacher import TeacherAbsenceCreateRequest, TeacherAbsenceResponse, TeacherCreateRequest, TeacherResponse
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.teachers import (
    DuplicateTeacherError,
    TeacherAbsenceNotFoundError,
    TeacherNotFoundError,
    create_teacher_absence,
    create_teacher,
    delete_teacher_absence,
    delete_teacher,
    list_available_teachers,
    list_teachers,
    mappers,
)

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("", response_model=list[TeacherResponse])
def get_teachers(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.teacher_to_response(teacher, lesson_count, absences).model_dump(mode="json")
        for teacher, lesson_count, absences in list_teachers(session)
    ]


@router.get("/available", response_model=list[TeacherResponse])
def get_available_teachers(
    date: Date,
    time_slot: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.teacher_to_response(teacher, lesson_count, absences).model_dump(mode="json")
        for teacher, lesson_count, absences in list_available_teachers(
            session, lesson_date=date, time_slot=time_slot
        )
    ]


@router.post("", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def post_teacher(
    payload: TeacherCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            teacher = create_teacher(
                session,
                name=payload.name,
                teacher_id=payload.teacher_id,
                post=payload.post,
                actor=actor,
            )
    except DuplicateTeacherError as exc:
        raise HTTPException(status_code=409, detail=f"teacher '{exc.teacher_id}' already exists") from exc
    return mappers.teacher_to_response(teacher, 0, []).model_dump(mode="json")


@router.post("/{teacher_id}/absences", response_model=TeacherAbsenceResponse, status_code=status.HTTP_201_CREATED)
def post_teacher_absence(
    teacher_id: int,
    payload: TeacherAbsenceCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            absence = create_teacher_absence(
                session,
                teacher_id,
                absence_date=payload.date,
                all_day=payload.all_day,
                time_slot_start=payload.time_slot_start,
                time_slot_end=payload.time_slot_end,
                reason=payload.reason,
                actor=actor,
            )
    except TeacherNotFoundError as exc:
        raise HTTPException(status_code=404, detail="teacher not found") from exc
    return mappers.absence_to_response(absence).model_dump(mode="json")


@router.delete("/{teacher_id}/absences/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_teacher_absence(
    teacher_id: int,
    absence_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_teacher_absence(session, teacher_id, absence_id, actor)
    except TeacherNotFoundError as exc:
        raise HTTPException(status_code=404, detail="teacher not found") from exc
    except TeacherAbsenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="teacher absence not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_teacher(
    teacher_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_teacher(session, teacher_id, actor)
    except TeacherNotFoundError as exc:
        raise HTTPException(status_code=404, detail="teacher not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
