from __future__ import annotations

from app.models import AuditLog, User
from app.schemas.user import UserCreateRequest
from app.services.auth.permissions import Actor
from app.services.auth.security import hash_password, verify_password
from app.services.users import mappers, repository


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


class UserNotFoundError(Exception):
    def __init__(self, user_id: int) -> None:
        super().__init__(user_id)
        self.user_id = user_id


def create_user(session, payload: UserCreateRequest, actor: Actor):
    username = payload.username.strip()
    if repository.find_user_by_username(session, username) is not None:
        raise DuplicateUserError(username)

    role = repository.find_role_by_name(session, payload.role)
    if role is None:
        raise RoleNotFoundError(payload.role)

    display_name = payload.display_name.strip()
    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(payload.password),
        is_active=True,
        role_id=role.id,
    )
    session.add(user)
    session.flush()
    _audit(session, action="create", user=user, actor=actor, payload={"username": username, "display_name": display_name, "role": role.name})
    return mappers.user_to_response(user, role.name)


def authenticate_user(session, username: str, password: str):
    row = repository.get_user_with_role(session, username=username.strip())
    if row is None:
        raise InvalidCredentialsError()
    user, role_name = row
    if not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return mappers.user_to_response(user, role_name)


def get_user_by_id(session, user_id: int):
    row = repository.get_user_with_role(session, user_id=user_id)
    if row is None:
        return None
    return mappers.user_to_response(*row)


def list_users(session) -> list:
    return [mappers.user_to_response(user, role_name) for user, role_name in repository.get_all_users_with_roles(session)]


def get_user_credentials(session, user_id: int):
    user = repository.get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    role_name = repository.get_role_name_for_user(session, user)
    if role_name is None:
        raise UserNotFoundError(user_id)
    return mappers.user_to_response(user, role_name)


def revoke_user(session, user_id: int, actor: Actor):
    user = repository.get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    if not user.is_active:
        return get_user_credentials(session, user_id)

    user.is_active = False
    session.flush()
    role_name = repository.get_role_name_for_user(session, user)
    if role_name is None:
        raise UserNotFoundError(user_id)
    _audit(session, action="revoke", user=user, actor=actor, payload={"username": user.username})
    return mappers.user_to_response(user, role_name)


def change_user_password(session, user_id: int, password: str, actor: Actor):
    user = repository.get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    user.password_hash = hash_password(password)
    session.flush()
    role_name = repository.get_role_name_for_user(session, user)
    if role_name is None:
        raise UserNotFoundError(user_id)
    _audit(session, action="change_password", user=user, actor=actor, payload={"username": user.username})
    return mappers.user_to_response(user, role_name)


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
