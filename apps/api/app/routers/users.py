from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_database_url
from app.db.session import build_session_factory
from app.schemas.user import UserCreateRequest
from app.services.auth.permissions import Actor, require_admin_actor
from app.services.users import DuplicateUserError, RoleNotFoundError, create_user, list_users

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
