"""P1-11 regression tests: Alembic is the single boot-time schema source.

Covers the two production-relevant DB states create_app must handle:

1. Fresh empty DB → boot migration runs ``alembic upgrade head``; the
   ``alembic_version`` table exists and the schema is usable.
2. Pre-existing ``Base.metadata.create_all`` DB (the shape the legacy test
   suite builds) → boot migration *stamps* head instead of re-creating tables,
   so create_app still works and the app is healthy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from axiom.schema.models import Base
from axiom.storage.db import build_engine, run_boot_migration
from axiom.studio.server import create_app


def _table_names(db_url: str) -> set[str]:
    engine = create_engine(db_url, future=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_fresh_db_boot_migration_creates_alembic_version_and_schema(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'fresh.db'}"
    assert _table_names(db_url) == set(), "DB should start empty"

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    tables = _table_names(db_url)
    assert "alembic_version" in tables, "boot migration must stamp/track via alembic_version"
    # Core ORM tables from the migrations must be present and queryable.
    assert "entities" in tables
    assert "receipts" in tables


def test_fresh_db_is_stamped_at_head(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'head.db'}"
    create_app(db_url=db_url, enable_organizer=False)

    engine = create_engine(db_url, future=True)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert version, "alembic_version must hold the head revision after boot migration"


def test_preexisting_create_all_db_is_stamped_not_recreated(tmp_path: Path) -> None:
    """A DB built by Base.metadata.create_all (no alembic_version) must be
    stamped, not upgraded-from-scratch, so create_app does not crash."""
    db_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    pre = _table_names(db_url)
    assert "alembic_version" not in pre
    assert "entities" in pre  # create_all already built the app schema

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        # Schema is usable end-to-end.
        assert client.get("/api/entities").json() == []

    post = _table_names(db_url)
    assert "alembic_version" in post, "create_all DB should be stamped on boot"


def test_auto_migrate_can_be_disabled(tmp_path: Path, monkeypatch: Any) -> None:
    """With AXIOM_AUTO_MIGRATE=0 the boot migration is a no-op (no
    alembic_version), but create_app's ensure_* safety net still serves."""
    monkeypatch.setenv("AXIOM_AUTO_MIGRATE", "0")
    db_url = f"sqlite:///{tmp_path / 'noauto.db'}"

    # run_boot_migration directly: must not create alembic_version.
    engine, _factory = build_engine(db_url)
    run_boot_migration(db_url, engine=engine)
    engine.dispose()
    assert "alembic_version" not in _table_names(db_url)

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
