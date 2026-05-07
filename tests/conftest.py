from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from axiom.schema.models import Base
from axiom.storage.db import init_engine, reset_engine


@pytest.fixture()
def db_session(tmp_path: Path) -> Iterator[Session]:
    db_path = tmp_path / "test.db"
    engine = init_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    from axiom.storage.db import get_session

    session = get_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        reset_engine()

