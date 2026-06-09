from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.user import UserCreateRequest, UserPasswordUpdateRequest
from app.services.auth.permissions import Actor, require_admin_actor
from app.services.users import (
    DuplicateUserError,
    RoleNotFoundError,
    UserNotFoundError,
    change_user_password,
    create_user,
    get_user_credentials,
    list_users,
    revoke_user,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def get_users(
    request: Request,
    actor: Annotated[Actor, Depends(require_admin_actor)],
) -> list[dict]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        return [user.model_dump(mode="json") for user in list_users(session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def post_user(
    request: Request,
    payload: UserCreateRequest,
    actor: Annotated[Actor, Depends(require_admin_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = create_user(session, payload, actor)
        except DuplicateUserError as exc:
            raise HTTPException(status_code=409, detail=f"user '{exc.username}' already exists") from exc
        except RoleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"role '{exc.role}' not found") from exc
    return result.model_dump(mode="json")


@router.get("/{user_id}/credentials")
def get_credentials(
    request: Request,
    user_id: int,
    actor: Annotated[Actor, Depends(require_admin_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            result = get_user_credentials(session, user_id)
        except UserNotFoundError as exc:
            raise HTTPException(status_code=404, detail="user not found") from exc
    return result.model_dump(mode="json")


@router.post("/{user_id}/revoke")
def revoke(
    request: Request,
    user_id: int,
    actor: Annotated[Actor, Depends(require_admin_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = revoke_user(session, user_id, actor)
        except UserNotFoundError as exc:
            raise HTTPException(status_code=404, detail="user not found") from exc
    return result.model_dump(mode="json")


@router.post("/{user_id}/password")
def change_password(
    request: Request,
    user_id: int,
    payload: UserPasswordUpdateRequest,
    actor: Annotated[Actor, Depends(require_admin_actor)],
) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            with session.begin():
                result = change_user_password(session, user_id, payload.password, actor)
        except UserNotFoundError as exc:
            raise HTTPException(status_code=404, detail="user not found") from exc
    return result.model_dump(mode="json")
