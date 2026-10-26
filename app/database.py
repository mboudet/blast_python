"""SQLAlchemy setup.

Supports any SQLAlchemy database URL. By default a local SQLite file is used;
a remote database (PostgreSQL, MySQL, ...) can be configured through
``DATABASE_URL`` or the ``DB_*`` variables.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_options(url: str) -> dict:
    opts: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        # Allow concurrent reads from the scheduler status endpoint.
        opts["connect_args"] = {"check_same_thread": False}
    return opts


def make_engine(url: str | None = None):
    settings = get_settings()
    url = url or settings.effective_database_url
    return create_engine(url, **_engine_options(url))


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  ensure models are registered

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
