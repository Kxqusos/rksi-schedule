from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.auth.security import InvalidTokenError, decode_access_token


EDITOR_ROLES = {"operator", "admin"}
ADMIN_ROLE = "admin"

# auto_error=False so a missing/malformed header surfaces as our own 401 with a
# descriptive detail (and keeps 401 rather than HTTPBearer's default 403). The
# scheme is still emitted into the OpenAPI contract as an http bearer scheme.
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Actor:
    role: str
    name: str
    user_id: int | None = None


def require_editor_actor(
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> Actor:
    resolved_actor = _resolve_actor(session, credentials)
    if resolved_actor.role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="operator or admin role is required")
    return resolved_actor


def require_admin_actor(
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> Actor:
    resolved_actor = _resolve_actor(session, credentials)
    if resolved_actor.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="admin role is required")
    return resolved_actor


def _resolve_actor(session: Session, credentials: HTTPAuthorizationCredentials | None) -> Actor:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="authorization is required")

    try:
        token_payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    from app.services.users import get_user_by_id

    # Read the actor inside its own transaction so the request session is
    # handed to the route with no open transaction — routes open their own
    # `with session.begin()`, which errors if one is already active. The engine
    # uses expire_on_commit=False, so the user's attributes stay usable after
    # this block commits. Single session per request (no extra pool checkout).
    with session.begin():
        user = get_user_by_id(session, int(token_payload.get("sub", 0)))
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="user is inactive")
    return Actor(role=user.role, name=user.display_name, user_id=user.id)
