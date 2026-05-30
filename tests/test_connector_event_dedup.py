"""Tests for connector webhook event idempotency (P1-4 / DEDUP).

A webhook retry that delivers the same (vendor, external_id) twice must result
in exactly one persisted row, and the second insert must be treated as a benign
skip (no exception bubbles, no brain re-apply).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.schema.models import Base, ConnectorEventRow
from axiom.studio.server import _persist_connector_event


@pytest.fixture
def session(tmp_path: Path) -> Session:
    db_url = f"sqlite:///{tmp_path / 'dedup.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s
    engine.dispose()


def _count(session: Session) -> int:
    return session.execute(select(func.count(ConnectorEventRow.id))).scalar_one()


def _insert(session: Session, *, vendor: str, external_id: str | None) -> bool:
    return _persist_connector_event(
        session,
        vendor=vendor,
        connector_state_id=None,
        event_type="message",
        external_id=external_id,
        payload={"k": "v"},
        signature_ok=True,
        received_at=datetime.utcnow(),
        event_timestamp=None,
    )


def test_persist_dedups_same_vendor_external_id(session: Session) -> None:
    first = _insert(session, vendor="github", external_id="gh-dup-1")
    session.commit()
    assert first is True
    assert _count(session) == 1

    # Retry of the same event: benign skip, returns False, no exception bubbles.
    second = _insert(session, vendor="github", external_id="gh-dup-1")
    session.commit()
    assert second is False
    assert _count(session) == 1


def test_in_batch_duplicate_is_skipped_before_commit(session: Session) -> None:
    # Two identical events queued in the SAME uncommitted batch: the second is
    # a benign skip, so committing the batch does not raise an IntegrityError.
    first = _insert(session, vendor="github", external_id="batch-dup")
    second = _insert(session, vendor="github", external_id="batch-dup")
    assert first is True
    assert second is False
    session.commit()
    assert _count(session) == 1


def test_distinct_external_ids_are_kept(session: Session) -> None:
    assert _insert(session, vendor="github", external_id="a") is True
    assert _insert(session, vendor="github", external_id="b") is True
    session.commit()
    assert _count(session) == 2


def test_same_external_id_different_vendor_is_kept(session: Session) -> None:
    assert _insert(session, vendor="github", external_id="shared") is True
    assert _insert(session, vendor="linear", external_id="shared") is True
    session.commit()
    assert _count(session) == 2


def test_missing_external_id_stored_as_null_does_not_collide(session: Session) -> None:
    # Two events with no external id must NOT collide (NULLs are distinct in a
    # SQLite UNIQUE index), so both rows persist and external_id is NULL.
    assert _insert(session, vendor="slack", external_id="") is True
    assert _insert(session, vendor="slack", external_id=None) is True
    session.commit()
    assert _count(session) == 2
    rows = session.execute(select(ConnectorEventRow)).scalars().all()
    assert all(row.external_id is None for row in rows)
