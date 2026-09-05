"""Engine and session helpers. Connections are always closed via context managers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.logging import get_logger
from src.db.models import Base

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def get_engine(database_url: str | None = None) -> Engine:
    """Create or return the process-wide engine."""
    global _engine, _SessionLocal
    if database_url is not None:
        _engine = None
        _SessionLocal = None

    if _engine is None:
        if database_url is None:
            from src.config.config_loader import get_settings

            database_url = get_settings().database.sqlalchemy_url()

        if database_url.startswith("sqlite") and ":memory:" not in database_url:
            path = database_url.replace("sqlite:///", "", 1)
            if path.startswith("/") and len(path) > 2 and path[2] == ":":
                path = path.lstrip("/")
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        kwargs: dict = {"future": True}
        connect_args = _sqlite_connect_args(database_url)
        if ":memory:" in (database_url or ""):
            kwargs["poolclass"] = StaticPool
            connect_args["check_same_thread"] = False
        if connect_args:
            kwargs["connect_args"] = connect_args

        _engine = create_engine(database_url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        logger.info("Database engine created")
    return _engine


def init_db(database_url: str | None = None) -> None:
    """Create tables if they do not exist. Does not drop existing data."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    logger.info("Database schema ensured")


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope that always closes the session."""
    session = get_session()
    try:
        yield session
        session.commit()
    except ValueError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        logger.error("Database transaction rolled back")
        raise
    finally:
        session.close()


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
