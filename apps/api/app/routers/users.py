from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.user import UserCreateRequest, UserPasswordUpdateRequest, UserResponse
from app.services.auth.permissions import Actor, require_admin_actor
from app.services.users import (
    DuplicateUserError,
    RoleNotFoundError,
    UserNotFoundError,
    change_user_password,
    create_user,
    get_user_credentials,
    list_users,
    mappers,
    revoke_user,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def get_users(
    actor: Annotated[Actor, Depends(require_admin_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    return [
        mappers.user_to_response(user, role_name).model_dump(mode="json")
        for user, role_name in list_users(session)
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def post_user(
    payload: UserCreateRequest,
    actor: Annotated[Actor, Depends(require_admin_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            user, role_name = create_user(
                session,
                payload.username,
                payload.display_name,
                payload.password,
                payload.role,
                actor,
            )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail=f"user '{exc.username}' already exists") from exc
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"role '{exc.role}' not found") from exc
    return mappers.user_to_response(user, role_name).model_dump(mode="json")


@router.get("/{user_id}/credentials", response_model=UserResponse)
def get_credentials(
    user_id: int,
    actor: Annotated[Actor, Depends(require_admin_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        user, role_name = get_user_credentials(session, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return mappers.user_to_response(user, role_name).model_dump(mode="json")


@router.post("/{user_id}/revoke", response_model=UserResponse)
def revoke(
    user_id: int,
    actor: Annotated[Actor, Depends(require_admin_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            user, role_name = revoke_user(session, user_id, actor)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return mappers.user_to_response(user, role_name).model_dump(mode="json")


@router.post("/{user_id}/password", response_model=UserResponse)
def change_password(
    user_id: int,
    payload: UserPasswordUpdateRequest,
    actor: Annotated[Actor, Depends(require_admin_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    try:
        with session.begin():
            user, role_name = change_user_password(session, user_id, payload.password, actor)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return mappers.user_to_response(user, role_name).model_dump(mode="json")
