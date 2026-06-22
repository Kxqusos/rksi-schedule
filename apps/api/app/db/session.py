from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_session_factory


def build_engine(database_url: str):
    return create_engine(database_url, future=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session
