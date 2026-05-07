from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.schema.models import Base
from axiom.storage import crud
from axiom.studio.server import create_app


def _seeded_client(tmp_path: Path) -> TestClient:
    db_url = f"sqlite:///{tmp_path / 'search.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        refund = crud.create_entity(
            session,
            "decision",
            {"title": "Refund Policy 2026 (v3)"},
            source_id=None,
        )
        refunds = crud.create_entity(
            session,
            "document",
            {"title": "Refund Operations Playbook"},
            source_id=None,
        )
        onboarding = crud.create_entity(
            session,
            "process",
            {"name": "Customer Onboarding"},
            source_id=None,
        )
        roadmap = crud.create_entity(
            session,
            "thread",
            {"subject": "Roadmap Planning"},
            source_id=None,
        )
        support = crud.create_entity(
            session,
            "ticket",
            {"title": "Support SLA Audit"},
            source_id=None,
        )
        crud.add_edge(session, refund.id, refunds.id, "DECISION_REFERENCES_DOCUMENT")
        crud.add_edge(session, refund.id, onboarding.id, "DECISION_REFERENCES_PROCESS")
        crud.add_edge(session, support.id, refund.id, "TICKET_REFERENCES_DECISION")
        crud.add_edge(session, roadmap.id, onboarding.id, "THREAD_REFERENCES_PROCESS")
    engine.dispose()
    return TestClient(create_app(db_url=db_url))


def test_search_returns_empty_for_blank_query(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": ""})
    assert response.status_code == 200
    assert response.json() == []


def test_short_query_uses_prefix_match(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "ref"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["Refund Policy 2026 (v3)", "Refund Operations Playbook"]


def test_short_query_does_not_substring_match(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "fun"})
    assert response.status_code == 200
    assert response.json() == []


def test_long_query_uses_substring_match(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "policy"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Refund Policy 2026 (v3)"


def test_long_query_ranks_fuzzy_title_match(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "refnd"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Refund Policy 2026 (v3)"


def test_search_includes_connection_count_and_type(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "refund policy"})
    assert response.status_code == 200
    result = response.json()[0]
    assert result["type"] == "decision"
    assert result["connection_count"] == 3


def test_search_respects_limit(tmp_path: Path) -> None:
    with _seeded_client(tmp_path) as client:
        response = client.get("/api/entities/search", params={"q": "refund", "limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1
