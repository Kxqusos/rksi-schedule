from __future__ import annotations

from sqlalchemy import select

from app.models import Role, User


def find_user_by_username(session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def get_user_with_role(session, *, user_id: int | None = None, username: str | None = None) -> tuple[User, str] | None:
    stmt = select(User, Role.name).join(Role, Role.id == User.role_id)
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    elif username is not None:
        stmt = stmt.where(User.username == username)
    row = session.execute(stmt).first()
    if row is None:
        return None
    return row.User, row[1]


def get_all_users_with_roles(session) -> list[tuple[User, str]]:
    rows = session.execute(
        select(User, Role.name).join(Role, Role.id == User.role_id).order_by(User.id)
    ).all()
    return [(row.User, row[1]) for row in rows]


def get_user_by_id(session, user_id: int) -> User | None:
    return session.get(User, user_id)


def find_role_by_name(session, name: str) -> Role | None:
    return session.scalar(select(Role).where(Role.name == name))


def get_role_name_for_user(session, user: User) -> str | None:
    return session.scalar(select(Role.name).where(Role.id == user.role_id))
