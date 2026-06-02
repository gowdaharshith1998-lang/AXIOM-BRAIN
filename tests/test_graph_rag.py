"""Tests for graph RAG: Personalized PageRank retrieval + agentic axiom_walk."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.mcp.server import AxiomMCPService
from axiom.retrieval.graph_rank import personalized_pagerank_search
from axiom.retrieval.search import hybrid_search
from axiom.schema.models import Base, Edge, Entity


def _seed(tmp_path: Path, db_name: str) -> sessionmaker[Session]:
    db_url = f"sqlite:///{tmp_path / db_name}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add_all(
            [
                Entity(
                    id="e1",
                    type="person",
                    cluster_id="company_knowledge",
                    composite_importance=0.95,
                    data={"title": "Alice Founder", "summary": "Founder and CEO."},
                ),
                Entity(
                    id="e2",
                    type="project",
                    cluster_id="company_knowledge",
                    composite_importance=0.9,
                    data={"title": "Alpha Platform", "summary": "Core product line."},
                ),
                Entity(
                    id="e3",
                    type="document",
                    cluster_id="growth_product",
                    composite_importance=0.8,
                    data={"title": "Refund Policy", "body": "Refunds within 30 days."},
                ),
                Entity(
                    id="e4",
                    type="person",
                    cluster_id="company_knowledge",
                    composite_importance=0.6,
                    data={"title": "Alicia Ops", "summary": "Operations lead."},
                ),
                Entity(
                    id="iso",
                    type="note",
                    cluster_id="company_knowledge",
                    composite_importance=0.5,
                    data={"title": "Founder offsite jotting"},
                ),
            ]
        )
        session.add_all(
            [
                Edge(id="ed1", source_id="e1", target_id="e2", relationship="owns", data={}),
                Edge(
                    id="ed2",
                    source_id="e2",
                    target_id="e3",
                    relationship="references",
                    data={},
                ),
                Edge(id="ed3", source_id="e1", target_id="e4", relationship="manages", data={}),
            ]
        )
        session.commit()
    engine.dispose()
    engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


# --- Personalized PageRank ----------------------------------------------------


def test_ppr_surfaces_associated_entities(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "ppr.db")
    with sf() as session:
        results = personalized_pagerank_search(session, "founder", top_k=10)
    ids = [row["id"] for row in results]
    # "founder" matches e1 (and the isolated note) lexically; PPR must also
    # surface e1's graph neighbors that never matched the query text.
    assert "e1" in ids
    assert "e2" in ids, "PPR should propagate to a connected neighbor of the seed"
    seed_rows = [r for r in results if r["matched_on"] == "ppr_seed"]
    assoc_rows = [r for r in results if r["matched_on"] == "ppr_assoc"]
    assert seed_rows, "expected at least one seed-tagged result"
    assert assoc_rows, "expected at least one association-tagged result"


def test_ppr_associative_score_beats_unreachable(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "ppr-iso.db")
    with sf() as session:
        # An entity that neither matches "founder" nor connects to any seed.
        session.add(
            Entity(
                id="orphan",
                type="note",
                cluster_id="company_knowledge",
                composite_importance=0.5,
                data={"title": "Quarterly logistics memo"},
            )
        )
        session.commit()
    with sf() as session:
        results = personalized_pagerank_search(session, "founder", top_k=10)
    ids = [row["id"] for row in results]
    scores = {row["id"]: row["score"] for row in results}
    # e2 never matched the query text but is reachable from seed e1 — PPR must
    # surface it with a positive associative score. The unreachable non-seed
    # "orphan" must get no PPR mass at all.
    assert scores.get("e2", 0.0) > 0.0
    assert "orphan" not in ids


def test_ppr_blank_query_returns_empty(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "ppr-empty.db")
    with sf() as session:
        assert personalized_pagerank_search(session, "   ", top_k=5) == []
        assert personalized_pagerank_search(session, "", top_k=5) == []


def test_ppr_mode_via_hybrid_search(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "ppr-hybrid.db")
    with sf() as session:
        out = hybrid_search(session, "founder", mode="ppr", top_k=10)
    assert out["mode"] == "ppr"
    assert out["count"] == len(out["results"])
    assert all(row["methods"] == ["ppr"] for row in out["results"])


def test_ppr_mode_via_internal_search_api(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from axiom.studio.server import create_app

    db_url = f"sqlite:///{tmp_path / 'ppr-api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add_all(
            [
                Entity(id="a1", type="person", data={"title": "Alice Founder"}),
                Entity(id="a2", type="project", data={"title": "Alpha Platform"}),
            ]
        )
        session.add(Edge(id="ae1", source_id="a1", target_id="a2", relationship="owns", data={}))
        session.commit()
    engine.dispose()

    with TestClient(create_app(db_url=db_url, enable_organizer=False)) as client:
        response = client.post(
            "/api/internal/search", json={"query": "founder", "mode": "ppr", "top_k": 5}
        )
    assert response.status_code == 200
    assert response.json()["mode"] == "ppr"


# --- Agentic axiom_walk -------------------------------------------------------


def test_walk_returns_ranked_neighbors_with_content(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk.db")
    service = AxiomMCPService(session_factory=sf)
    out = service.walk("platform", ["e1"], direction="outgoing")
    hop_ids = [hop["id"] for hop in out["next_hops"]]
    assert set(hop_ids) == {"e2", "e4"}
    # inline content present — agent does not need follow-up get_entity calls
    e2_hop = next(hop for hop in out["next_hops"] if hop["id"] == "e2")
    assert e2_hop["title"] == "Alpha Platform"
    assert e2_hop["snippet"] == "Core product line."
    assert e2_hop["relationship"] == "owns"
    assert e2_hop["from_id"] == "e1"
    # "platform" is relevant to e2, not e4 — e2 must rank first
    assert hop_ids[0] == "e2"
    assert out["exhausted"] is False


def test_walk_respects_edge_type_filter(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk-edge.db")
    service = AxiomMCPService(session_factory=sf)
    out = service.walk("", ["e1"], edge_types=["manages"], direction="outgoing")
    assert [hop["id"] for hop in out["next_hops"]] == ["e4"]


def test_walk_respects_direction(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk-dir.db")
    service = AxiomMCPService(session_factory=sf)
    # e3 only has an incoming edge (e2 -> e3); outgoing walk finds nothing.
    outgoing = service.walk("", ["e3"], direction="outgoing")
    assert outgoing["exhausted"] is True
    incoming = service.walk("", ["e3"], direction="incoming")
    assert [hop["id"] for hop in incoming["next_hops"]] == ["e2"]


def test_walk_skips_unknown_frontier_ids(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk-skip.db")
    service = AxiomMCPService(session_factory=sf)
    out = service.walk("platform", ["e1", "ghost"], direction="outgoing")
    assert out["frontier"] == ["e1"]
    assert out["skipped"] == ["ghost"]


def test_walk_all_unknown_raises(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk-raise.db")
    service = AxiomMCPService(session_factory=sf)
    with pytest.raises(LookupError):
        service.walk("platform", ["ghost1", "ghost2"])


def test_walk_excludes_frontier_from_its_own_results(tmp_path: Path) -> None:
    sf = _seed(tmp_path, "walk-self.db")
    service = AxiomMCPService(session_factory=sf)
    # walking from {e1, e2}: e2 is reachable from e1 but is in the frontier,
    # so it must not be returned as a next hop.
    out = service.walk("", ["e1", "e2"], direction="outgoing")
    hop_ids = {hop["id"] for hop in out["next_hops"]}
    assert "e1" not in hop_ids and "e2" not in hop_ids
    assert hop_ids == {"e3", "e4"}
