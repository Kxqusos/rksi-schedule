from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, Role, User
from app.schemas.user import UserCreateRequest, UserResponse
from app.services.auth.permissions import Actor
from app.services.auth.security import hash_password, verify_password


class DuplicateUserError(Exception):
    def __init__(self, username: str) -> None:
        super().__init__(username)
        self.username = username


class RoleNotFoundError(Exception):
    def __init__(self, role: str) -> None:
        super().__init__(role)
        self.role = role


class InvalidCredentialsError(Exception):
    pass


def create_user(session, payload: UserCreateRequest, actor: Actor) -> UserResponse:
    username = payload.username.strip()
    existing_user = session.scalar(select(User).where(User.username == username))
    if existing_user is not None:
        raise DuplicateUserError(username)

    role = session.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise RoleNotFoundError(payload.role)

    display_name = payload.display_name.strip()
    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(payload.password),
        role_id=role.id,
    )
    session.add(user)
    session.flush()
    _audit(session, action="create", user=user, actor=actor, payload={"username": username, "display_name": display_name, "role": role.name})
    return _user_response(user, role.name)


def authenticate_user(session, username: str, password: str) -> UserResponse:
    row = session.execute(
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .where(User.username == username.strip())
    ).first()
    if row is None:
        raise InvalidCredentialsError()

    user, role_name = row
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return _user_response(user, role_name)


def get_user_by_id(session, user_id: int) -> UserResponse | None:
    row = session.execute(
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .where(User.id == user_id)
    ).first()
    if row is None:
        return None

    user, role_name = row
    return _user_response(user, role_name)


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
        display_name=user.display_name,
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
