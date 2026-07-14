from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def init_engine(database_url: str) -> None:
    global _engine, _session_factory
    _engine = create_engine(
        database_url,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def is_initialized() -> bool:
    return _session_factory is not None


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        raise RuntimeError("Engine not initialized; call init_engine() first")
    return _session_factory
