from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.time_profile import (
    DayTimeProfileCreateRequest,
    DayTimeProfileResponse,
    DayTimeProfileUpdateRequest,
    WeekTimeProfileCreateRequest,
    WeekTimeProfileResponse,
    WeekTimeProfileUpdateRequest,
)
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.time_profiles import (
    DayProfileReferenceError,
    DuplicateTimeProfileError,
    TimeProfileInUseError,
    TimeProfileNotFoundError,
    create_day_profile,
    create_week_profile,
    delete_day_profile,
    delete_week_profile,
    list_day_profiles,
    list_week_profiles,
    update_day_profile,
    update_week_profile,
)

router = APIRouter(prefix="/time-profiles", tags=["time-profiles"])


@router.get("/day", response_model=list[DayTimeProfileResponse])
def get_day_profiles(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [profile.model_dump(mode="json") for profile in list_day_profiles(session)]


@router.post("/day", response_model=DayTimeProfileResponse, status_code=status.HTTP_201_CREATED)
def post_day_profile(
    payload: DayTimeProfileCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = create_day_profile(session, payload, actor)
    except DuplicateTimeProfileError as exc:
        raise HTTPException(status_code=409, detail="day profile already exists") from exc
    return result.model_dump(mode="json")


@router.patch("/day/{profile_id}", response_model=DayTimeProfileResponse)
def patch_day_profile(
    profile_id: int,
    payload: DayTimeProfileUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = update_day_profile(session, profile_id, payload, actor)
    except TimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day profile not found") from exc
    except DuplicateTimeProfileError as exc:
        raise HTTPException(status_code=409, detail="day profile already exists") from exc
    return result.model_dump(mode="json")


@router.delete("/day/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_day_profile(
    profile_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_day_profile(session, profile_id, actor)
    except TimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day profile not found") from exc
    except TimeProfileInUseError as exc:
        raise HTTPException(status_code=409, detail="day profile is used by week profile") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/week", response_model=list[WeekTimeProfileResponse])
def get_week_profiles(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [profile.model_dump(mode="json") for profile in list_week_profiles(session)]


@router.post("/week", response_model=WeekTimeProfileResponse, status_code=status.HTTP_201_CREATED)
def post_week_profile(
    payload: WeekTimeProfileCreateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = create_week_profile(session, payload, actor)
    except DuplicateTimeProfileError as exc:
        raise HTTPException(status_code=409, detail="week profile already exists") from exc
    except DayProfileReferenceError as exc:
        raise HTTPException(status_code=404, detail="day profile not found") from exc
    return result.model_dump(mode="json")


@router.patch("/week/{profile_id}", response_model=WeekTimeProfileResponse)
def patch_week_profile(
    profile_id: int,
    payload: WeekTimeProfileUpdateRequest,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            result = update_week_profile(session, profile_id, payload, actor)
    except TimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="week profile not found") from exc
    except DuplicateTimeProfileError as exc:
        raise HTTPException(status_code=409, detail="week profile already exists") from exc
    except DayProfileReferenceError as exc:
        raise HTTPException(status_code=404, detail="day profile not found") from exc
    return result.model_dump(mode="json")


@router.delete("/week/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_week_profile(
    profile_id: int,
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        with session.begin():
            delete_week_profile(session, profile_id, actor)
    except TimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="week profile not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
