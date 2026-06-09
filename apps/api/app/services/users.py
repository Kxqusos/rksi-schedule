from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, Role, User
from app.schemas.user import UserCreateRequest, UserResponse
from app.services.auth.permissions import Actor


class DuplicateUserError(Exception):
    def __init__(self, username: str) -> None:
        super().__init__(username)
        self.username = username


class RoleNotFoundError(Exception):
    def __init__(self, role: str) -> None:
        super().__init__(role)
        self.role = role


def create_user(session, payload: UserCreateRequest, actor: Actor) -> UserResponse:
    username = payload.username.strip()
    existing_user = session.scalar(select(User).where(User.username == username))
    if existing_user is not None:
        raise DuplicateUserError(username)

    role = session.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise RoleNotFoundError(payload.role)

    user = User(username=username, role_id=role.id)
    session.add(user)
    session.flush()
    _audit(session, action="create", user=user, actor=actor, payload={"username": username, "role": role.name})
    return _user_response(user, role.name)


def list_users(session) -> list[UserResponse]:
    rows = session.execute(
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .order_by(User.id)
    ).all()
    return [_user_response(user, role_name) for user, role_name in rows]


def _user_response(user: User, role_name: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=role_name,
        created_at=user.created_at,
    )


def _audit(session, *, action: str, user: User, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type="user",
            entity_id=user.id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )
