"""P0-5 regression tests: every SQLite engine built through the central factory
must carry WAL journaling, a non-zero busy_timeout, and foreign-key enforcement.

These assert observable connection state (the PRAGMA read-back values), not the
listener internals, so they would catch any regression that drops the listener
or routes an ad-hoc ``create_engine`` around the factory.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from axiom.storage.db import build_engine


def _pragma(engine: Any, name: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(f"PRAGMA {name}")).scalar()


def test_factory_sets_wal_busy_timeout_and_foreign_keys(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'pragmas.db'}"
    engine, _factory = build_engine(db_url)
    try:
        assert str(_pragma(engine, "journal_mode")).lower() == "wal"
        assert int(_pragma(engine, "foreign_keys")) == 1
        assert int(_pragma(engine, "busy_timeout")) >= 5000
        # synchronous=NORMAL is value 1 in SQLite's enum.
        assert int(_pragma(engine, "synchronous")) == 1
    finally:
        engine.dispose()


def test_pragmas_apply_to_every_connection(tmp_path: Path) -> None:
    """The listener must fire on each new pooled connection, not just the first."""
    db_url = f"sqlite:///{tmp_path / 'pragmas_multi.db'}"
    engine, _factory = build_engine(db_url)
    try:
        for _ in range(3):
            with engine.connect() as conn:
                assert int(conn.execute(text("PRAGMA foreign_keys")).scalar()) == 1
                assert int(conn.execute(text("PRAGMA busy_timeout")).scalar()) >= 5000
    finally:
        engine.dispose()


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    """With foreign_keys=ON a violating insert must raise (proves it is wired)."""
    db_url = f"sqlite:///{tmp_path / 'fk.db'}"
    engine, _factory = build_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            conn.execute(
                text(
                    "CREATE TABLE child ("
                    "id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER REFERENCES parent(id))"
                )
            )
        violated = False
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))
        except Exception:  # noqa: BLE001 - any IntegrityError proves enforcement
            violated = True
        assert violated, "foreign_keys=ON should reject the orphaned child row"
    finally:
        engine.dispose()


def test_busy_timeout_lets_concurrent_writer_wait_not_fail(tmp_path: Path) -> None:
    """A second writer hitting a held lock must wait (busy_timeout), not fail
    immediately with 'database is locked'."""
    db_url = f"sqlite:///{tmp_path / 'busy.db'}"
    engine, _factory = build_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)"))

        hold_started = threading.Event()
        release = threading.Event()
        errors: list[str] = []

        def hold_write_lock() -> None:
            conn = engine.connect()
            try:
                trans = conn.begin()
                # Acquire a write lock and hold it until released.
                conn.execute(text("INSERT INTO t (id, v) VALUES (1, 1)"))
                hold_started.set()
                release.wait(timeout=5)
                trans.commit()
            finally:
                conn.close()

        holder = threading.Thread(target=hold_write_lock)
        holder.start()
        assert hold_started.wait(timeout=5)

        def second_writer() -> None:
            try:
                # Without busy_timeout this raises 'database is locked' at once;
                # with busy_timeout=5000 it blocks until the holder commits.
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO t (id, v) VALUES (2, 2)"))
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        writer = threading.Thread(target=second_writer)
        writer.start()
        # Give the second writer a moment to start blocking, then release.
        time.sleep(0.2)
        release.set()
        holder.join(timeout=5)
        writer.join(timeout=10)

        assert not errors, f"second writer failed instead of waiting: {errors}"
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM t")).scalar()
        assert count == 2
    finally:
        engine.dispose()


def test_busy_timeout_configurable_via_env(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("AXIOM_SQLITE_BUSY_TIMEOUT_MS", "9000")
    db_url = f"sqlite:///{tmp_path / 'env.db'}"
    engine, _factory = build_engine(db_url)
    try:
        assert int(_pragma(engine, "busy_timeout")) == 9000
    finally:
        engine.dispose()


def test_memory_sqlite_shares_one_database_across_threads() -> None:
    """Regression: in-memory SQLite must use StaticPool so all threads see the
    same database.

    Without it, the lifespan thread creates the schema on one connection while
    request handlers / background tasks get fresh empty databases on others —
    CI failed test_readyz_200_when_healthy with "no such table" precisely this
    way while local runs passed by thread-reuse luck.
    """
    import threading

    from sqlalchemy import text

    from axiom.storage.db import build_engine

    engine, session_factory = build_engine("sqlite://")
    try:
        # Create a table on the main thread.
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE shared_check (id INTEGER PRIMARY KEY)"))
            conn.execute(text("INSERT INTO shared_check (id) VALUES (1)"))

        # Every OTHER thread must see the same database. Reads run one thread
        # at a time: the property under test is cross-thread visibility (one
        # shared in-memory DB), not simultaneous-query handling on a single
        # connection (which pysqlite does not guarantee and the app never does
        # against in-memory DBs - they are test-only).
        results: list[int] = []

        def read_from_thread() -> None:
            with session_factory() as session:
                count = session.execute(text("SELECT COUNT(*) FROM shared_check")).scalar_one()
                results.append(int(count))

        for _ in range(8):
            worker = threading.Thread(target=read_from_thread)
            worker.start()
            worker.join()

        assert results == [1] * 8
    finally:
        engine.dispose()


def test_readyz_healthy_with_memory_sqlite_under_thread_pressure() -> None:
    """End-to-end version of the CI failure: an app on sqlite:// must report
    /readyz healthy because the schema its lifespan created is visible to the
    request-handling thread."""
    from fastapi.testclient import TestClient

    from axiom.studio.server import create_app

    # Repeat a few times to make thread-assignment luck irrelevant.
    for _ in range(3):
        with TestClient(create_app(db_url="sqlite://", enable_organizer=False)) as client:
            resp = client.get("/readyz")
            assert resp.status_code == 200, resp.json()
            assert resp.json()["checks"]["failed"] == []
