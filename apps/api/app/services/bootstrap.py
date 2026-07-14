from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_bootstrap_admin_config
from app.db.engine import get_session_factory
from app.models import Role, User
from app.services.auth.security import hash_password


def bootstrap_admin() -> None:
    config = get_bootstrap_admin_config()
    if config is None:
        return

    session_factory = get_session_factory()
    try:
        with session_factory() as session:
            with session.begin():
                admin_role = session.scalar(select(Role).where(Role.name == "admin"))
                if admin_role is None:
                    admin_role = Role(name="admin")
                    session.add(admin_role)
                    session.flush()

                user = session.scalar(select(User).where(User.username == config.username))
                if user is None:
                    user = User(
                        username=config.username,
                        display_name=config.display_name,
                        password_hash=hash_password(config.password),
                        is_active=True,
                        role_id=admin_role.id,
                    )
                    session.add(user)
                    return

                user.display_name = config.display_name
                user.password_hash = hash_password(config.password)
                user.is_active = True
                user.role_id = admin_role.id
    except SQLAlchemyError:
        # Database migrations are still explicit. If tables are absent on startup,
        # health checks should stay available and migrations can be run normally.
        return
