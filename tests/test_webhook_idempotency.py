"""P1-4 completion: webhook/event ingest idempotency.

Re-delivery is the default for at-least-once webhook providers. These tests pin
the three guarantees:

* replaying the same delivery twice persists exactly one ``ConnectorEventRow``
  (the (vendor, external_id) UniqueConstraint + ``begin_nested`` SAVEPOINT),
* the brain is applied to only once (the duplicate is not re-applied), and
* ``crud.add_edge`` is idempotent, so a replayed event never double-creates the
  same (source, target, relationship) edge.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.schema.models import Base, ConnectorEventRow, Edge, Entity
from axiom.storage import crud


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    from axiom.studio.server import create_app

    db_url = f"sqlite:///{tmp_path / 'webhook_idem.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("AXIOM_CONNECTOR_GITHUB_ENABLED", "1")
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_ID", "github_client")
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_SECRET", "github_secret")
    monkeypatch.setenv("AXIOM_GITHUB_WEBHOOK_SECRET", "github_webhook")
    app = create_app(db_url=db_url, enable_organizer=False)
    return app, db_url


def _github_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _github_issue_body() -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "issue": {"id": 99, "number": 7, "title": "Idempotency bug"},
            "repository": {"id": 1, "full_name": "octo/repo", "name": "repo"},
        }
    ).encode()


def _post_webhook(client: TestClient, body: bytes) -> Any:
    return client.post(
        "/api/internal/connectors/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery_dup",
            "X-Hub-Signature-256": _github_signature("github_webhook", body),
        },
    )


def test_replayed_webhook_persists_one_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, db_url = _make_app(tmp_path, monkeypatch)
    body = _github_issue_body()

    with TestClient(app) as client:
        first = _post_webhook(client, body)
        second = _post_webhook(client, body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    with Session(create_engine(db_url, future=True)) as session:
        count = session.execute(
            select(func.count(ConnectorEventRow.id)).where(ConnectorEventRow.vendor == "github")
        ).scalar_one()
    assert count == 1, "re-delivery must not create a second connector_events row"


def test_replayed_webhook_applies_to_brain_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, db_url = _make_app(tmp_path, monkeypatch)
    body = _github_issue_body()

    with TestClient(app) as client:
        first = _post_webhook(client, body)
        second = _post_webhook(client, body)

    # The first delivery applies to the brain; the duplicate must not.
    assert first.json()["ingested"] >= 1
    assert second.json()["ingested"] == 0, "duplicate delivery must not re-apply to the brain"

    # And the issue entity exists exactly once.
    with Session(create_engine(db_url, future=True)) as session:
        entities = (
            session.execute(select(Entity).where(Entity.source_id == "github:issue:99"))
            .scalars()
            .all()
        )
    assert len(entities) == 1


def test_add_edge_is_idempotent(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'edge_idem.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with sf() as session:
        a = crud.create_entity(session, "doc", {"title": "A"})
        b = crud.create_entity(session, "doc", {"title": "B"})
        first = crud.add_edge(session, a.id, b.id, "REFERENCES")
        second = crud.add_edge(session, a.id, b.id, "REFERENCES")

    # Same logical edge returned, not a duplicate row.
    assert first.id == second.id
    with sf() as session:
        edge_count = session.execute(
            select(func.count(Edge.id)).where(
                Edge.source_id == a.id,
                Edge.target_id == b.id,
                Edge.relationship == "REFERENCES",
            )
        ).scalar_one()
    assert edge_count == 1


def test_add_edge_distinct_relationship_not_deduped(tmp_path: Path) -> None:
    """A different relationship between the same nodes is a distinct edge."""
    db_url = f"sqlite:///{tmp_path / 'edge_distinct.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with sf() as session:
        a = crud.create_entity(session, "doc", {"title": "A"})
        b = crud.create_entity(session, "doc", {"title": "B"})
        crud.add_edge(session, a.id, b.id, "REFERENCES")
        crud.add_edge(session, a.id, b.id, "MENTIONS")
        total = session.execute(
            select(func.count(Edge.id)).where(Edge.source_id == a.id, Edge.target_id == b.id)
        ).scalar_one()
    assert total == 2
