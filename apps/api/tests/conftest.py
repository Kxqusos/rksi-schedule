from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from app.db.engine import get_session_factory, init_engine, is_initialized

_bound_url: str | None = None


def migrate_database(database_url: str) -> None:
    """Migrate the test database and bind the process engine to it.

    Every test calls this once with its own SQLite URL before seeding or
    hitting the app, so it doubles as the single point where the per-process
    engine (``db/engine.py``) is pointed at the test DB. Production code keeps
    ``get_session`` a pure ``get_session_factory()`` call — the URL-rebinding
    convenience lives here in the test layer, not in the request path.
    """
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    bind_engine(database_url)


def bind_engine(database_url: str) -> sessionmaker:
    """Point the process-lifetime engine at a test database and return its
    session factory. Re-initialises when the URL changes or when the engine
    was disposed (a TestClient ``lifespan`` exit calls ``dispose_engine``).
    """
    global _bound_url
    if _bound_url != database_url or not is_initialized():
        init_engine(database_url)
        _bound_url = database_url
    return get_session_factory()
