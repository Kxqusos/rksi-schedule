from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request

from app.core.config import get_database_url
from app.db.engine import ensure_engine
from app.services.auth.security import InvalidTokenError, decode_access_token


EDITOR_ROLES = {"operator", "admin"}
ADMIN_ROLE = "admin"


@dataclass(frozen=True, slots=True)
class Actor:
    role: str
    name: str
    user_id: int | None = None


def require_editor_actor(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Actor:
    resolved_actor = _resolve_actor(request, authorization=authorization)
    if resolved_actor.role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="operator or admin role is required")
    return resolved_actor


def require_admin_actor(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Actor:
    resolved_actor = _resolve_actor(request, authorization=authorization)
    if resolved_actor.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="admin role is required")
    return resolved_actor


def _resolve_actor(request: Request, *, authorization: str | None) -> Actor:
    if not authorization:
        raise HTTPException(status_code=401, detail="authorization is required")

    auth_type, _, token = authorization.partition(" ")
    if auth_type.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="invalid authorization header")
    try:
        token_payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    session_factory = ensure_engine(database_url)
    from app.services.users import get_user_by_id

    with session_factory() as session:
        user = get_user_by_id(session, int(token_payload.get("sub", 0)))
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="user is inactive")
    return Actor(role=user.role, name=user.display_name, user_id=user.id)
