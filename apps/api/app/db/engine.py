from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker | None = None
_engine_database_url: str | None = None


def init_engine(database_url: str) -> None:
    global _engine, _session_factory, _engine_database_url
    _engine = create_engine(
        database_url,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    _engine_database_url = database_url


def dispose_engine() -> None:
    global _engine, _session_factory, _engine_database_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _engine_database_url = None


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        raise RuntimeError("Engine not initialized; call init_engine() first")
    return _session_factory


def ensure_engine(database_url: str) -> sessionmaker:
    """Return the process-lifetime session factory, (re)initializing the
    engine if it hasn't been created yet or if the target database URL has
    changed (e.g. between test runs that each use their own SQLite file).
    """
    if _session_factory is None or _engine_database_url != database_url:
        init_engine(database_url)
    assert _session_factory is not None
    return _session_factory
