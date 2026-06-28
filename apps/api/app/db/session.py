from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.db.engine import ensure_engine


def get_session(request: Request) -> Generator[Session, None, None]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    session_factory = ensure_engine(database_url)
    with session_factory() as session:
        yield session
