from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def build_engine(database_url: str):
    return create_engine(database_url, future=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
