from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.mcp.server import AxiomMCPService
from axiom.schema.models import Base, Edge, Entity
from axiom.studio.server import create_app


@pytest.fixture()
def mcp_service(tmp_path: Path) -> AxiomMCPService:
    db_url = f"sqlite:///{tmp_path / 'mcp.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with sf() as session:
        entities = [
            Entity(
                id="e1",
                type="person",
                cluster_id="company_knowledge",
                composite_importance=0.95,
                data={"title": "Alice Founder"},
            ),
            Entity(
                id="e2",
                type="project",
                cluster_id="company_knowledge",
                composite_importance=0.9,
                data={"title": "Alpha Platform"},
            ),
            Entity(
                id="e3",
                type="doc",
                cluster_id="growth_product",
                composite_importance=0.8,
                data={"title": "Refund Policy"},
            ),
            Entity(
                id="e4",
                type="person",
                cluster_id="company_knowledge",
                composite_importance=0.6,
                data={"title": "Alicia Ops"},
            ),
        ]
        session.add_all(entities)
        session.add_all(
            [
                Edge(id="ed1", source_id="e1", target_id="e2", relationship="owns", data={}),
                Edge(id="ed2", source_id="e2", target_id="e3", relationship="references", data={}),
                Edge(id="ed3", source_id="e1", target_id="e4", relationship="manages", data={}),
            ]
        )
        session.commit()

    return AxiomMCPService(session_factory=sf)


def test_query_brain_returns_ranked_results(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.query_brain("ali", max_results=5)
    assert out["count"] >= 2
    assert out["results"][0]["id"] == "e1"
    assert "matched_on" in out["results"][0]


def test_query_brain_expands_neighbors(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.query_brain("founde", max_results=10)
    ids = {row["id"] for row in out["results"]}
    assert "e2" in ids
    e2 = next(row for row in out["results"] if row["id"] == "e2")
    assert str(e2["matched_on"]).startswith("neighbor_of:")


def test_query_brain_filters_by_type(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.query_brain("ali", max_results=10, entity_types=["person"])
    assert out["count"] >= 1
    assert all(row["type"] == "person" for row in out["results"])


def test_query_brain_filters_by_cluster(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.query_brain("policy", max_results=10, cluster_id="growth_product")
    assert out["count"] == 1
    assert out["results"][0]["id"] == "e3"


def test_query_brain_empty_query(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.query_brain("   ", max_results=10)
    assert out == {"results": [], "count": 0}


def test_get_entity_found(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.get_entity("e1")
    assert out["entity"]["id"] == "e1"
    assert out["entity"]["title"] == "Alice Founder"


def test_get_entity_unknown_raises(mcp_service: AxiomMCPService) -> None:
    with pytest.raises(LookupError):
        mcp_service.get_entity("missing")


def test_get_entity_with_neighbors(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.get_entity("e1", include_neighbors=True, hops=2)
    neighbor_ids = {n["id"] for n in out["neighbors"]}
    assert "e2" in neighbor_ids
    assert "e4" in neighbor_ids


def test_traverse_basic(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.traverse("e1", max_depth=2, direction="outgoing")
    assert out["root_id"] == "e1"
    assert len(out["nodes"]) >= 2
    assert any(edge["to_id"] == "e2" for edge in out["edges"])


def test_traverse_unknown_raises(mcp_service: AxiomMCPService) -> None:
    with pytest.raises(LookupError):
        mcp_service.traverse("missing")


def test_traverse_edge_type_filter(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.traverse("e1", edge_types=["manages"], direction="outgoing")
    assert out["edges"]
    assert all(edge["relationship"] == "manages" for edge in out["edges"])


def test_list_sources_shape(mcp_service: AxiomMCPService) -> None:
    out = mcp_service.list_sources()
    assert out["count"] > 0
    assert all(row["is_demo"] is True for row in out["sources"])


def test_internal_agent_navigation_endpoint_caps_to_50(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'server.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        steps = [{"from_id": "a", "to_id": f"b{i}", "edge_id": None} for i in range(80)]
        resp = client.post(
            "/api/internal/agent-navigation",
            json={"agent_name": "external_mcp_client", "steps": steps},
        )
        assert resp.status_code == 200
        assert resp.json()["emitted"] == 50


def test_query_brain_latency_budget(mcp_service: AxiomMCPService) -> None:
    start = time.perf_counter()
    out = mcp_service.query_brain("alice", max_results=10)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["count"] >= 1
    assert elapsed_ms < 200


def test_get_entity_latency_budget(mcp_service: AxiomMCPService) -> None:
    start = time.perf_counter()
    out = mcp_service.get_entity("e1")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["entity"]["id"] == "e1"
    assert elapsed_ms < 50


def test_traverse_latency_budget(mcp_service: AxiomMCPService) -> None:
    start = time.perf_counter()
    out = mcp_service.traverse("e1", max_depth=3)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["root_id"] == "e1"
    assert elapsed_ms < 500
