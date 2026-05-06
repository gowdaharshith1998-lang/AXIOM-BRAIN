from __future__ import annotations

import os
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL: Final[str] = "sqlite:///./axiom.db"

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str | None = None) -> Engine:
    """Initialize global engine + SessionLocal.

    Tests can call this with an in-memory or temp-file URL.
    """
    global _engine, SessionLocal

    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    _engine = create_engine(url, future=True)
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session() -> Session:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    return SessionLocal()


def reset_engine() -> None:
    """Test helper to drop global engine/sessionmaker."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None

