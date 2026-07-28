from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.user import LoginRequest, LoginResponse, UserResponse
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.auth.security import create_access_token
from app.services.users import InvalidCredentialsError, authenticate_user, get_user_by_id, mappers

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> dict:
    try:
        user, role_name = authenticate_user(session, payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="invalid username or password") from exc

    response = LoginResponse(
        access_token=create_access_token({"sub": user.id}),
        user=mappers.user_to_response(user, role_name),
    )
    return response.model_dump(mode="json")


@router.get("/me", response_model=UserResponse)
def me(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    if actor.user_id is None:
        return {"role": actor.role, "display_name": actor.name}

    row = get_user_by_id(session, actor.user_id)
    if row is None:
        raise HTTPException(status_code=401, detail="user not found")
    user, role_name = row
    return mappers.user_to_response(user, role_name).model_dump(mode="json")
