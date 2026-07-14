from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.engine import get_session_factory


def get_session() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
