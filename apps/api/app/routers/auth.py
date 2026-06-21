from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.user import LoginRequest, LoginResponse, UserResponse
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.auth.security import create_access_token
from app.services.users import InvalidCredentialsError, authenticate_user, get_user_by_id

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: Request, payload: LoginRequest) -> dict:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        try:
            user = authenticate_user(session, payload.username, payload.password)
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=401, detail="invalid username or password") from exc

    response = LoginResponse(
        access_token=create_access_token({"sub": user.id}),
        user=user,
    )
    return response.model_dump(mode="json")


@router.get("/me", response_model=UserResponse)
def me(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    if actor.user_id is None:
        return {"role": actor.role, "display_name": actor.name}

    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    _engine, session_factory = build_session_factory(database_url)
    with session_factory() as session:
        user = get_user_by_id(session, actor.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user.model_dump(mode="json")
