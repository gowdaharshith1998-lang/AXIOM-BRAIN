from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Base, Edge, Entity, Source
from axiom.studio.server import create_app


def _make_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'studio.db'}"


def test_health_and_bootstrap_endpoints_empty(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["current_seq"] == 0

        assert client.get("/api/entities").json() == []
        assert client.get("/api/edges").json() == []


def test_cluster_health_endpoint_returns_cluster_snapshot(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        session.add(
            Entity(
                type="thread",
                data={},
                source_id=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                cluster_id="billing_payments",
                composite_importance=0.5,
            )
        )
        session.commit()
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        payload = client.get("/api/cluster_health").json()

    assert payload["billing_payments"]["cluster_id"] == "billing_payments"
    assert payload["billing_payments"]["total_entities"] == 1


def test_sources_endpoint_returns_real_groupby_counts(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        session.add_all(
            [
                Source(
                    id="synthetic-default",
                    source_type="synthetic",
                    display_name="Synthetic",
                    connected=True,
                ),
                Source(
                    id="linear-main",
                    source_type="linear",
                    display_name="Linear",
                    connected=True,
                ),
                Entity(type="thread", data={}, source_id="synthetic-default"),
                Entity(type="ticket", data={}, source_id="synthetic-default"),
                Entity(type="ticket", data={}, source_id="linear-main"),
            ]
        )
        session.commit()
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        payload = client.get("/api/sources").json()

    counts = {row["source_id"]: row["count"] for row in payload}
    assert counts == {"synthetic-default": 2, "linear-main": 1}
    assert {row["name"] for row in payload} == {"Synthetic", "Linear"}


def test_sources_endpoint_returns_empty_when_no_data(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        payload = client.get("/api/sources").json()

    assert payload == []


def test_synthetic_default_source_row_present_after_migration(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    engine = create_engine(db_url, future=True)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        row = session.get(Source, "synthetic-default")
        assert row is not None
        assert row.source_type == "synthetic"
        assert row.display_name == "Synthetic"
        assert row.connected is True


def test_entity_edges_endpoint_returns_both_directions(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        session.add_all(
            [
                Entity(id="center", type="ticket", data={"title": "Center"}),
                Entity(id="parent", type="doc", data={"title": "Parent"}),
                Entity(id="child", type="task", data={"title": "Child"}),
                Edge(
                    id="edge_in",
                    source_id="parent",
                    target_id="center",
                    relationship="blocks",
                    data={},
                ),
                Edge(
                    id="edge_out",
                    source_id="center",
                    target_id="child",
                    relationship="creates",
                    data={},
                ),
            ]
        )
        session.commit()
    engine.dispose()

    # enable_organizer=False: the organizer's EdgeProposer would inject
    # same_cluster_related edges during startup and break the exact-set asserts.
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/entities/center/edges")

    assert response.status_code == 200
    payload = response.json()
    assert {row["id"] for row in payload["incoming"]} == {"edge_in"}
    assert {row["id"] for row in payload["outgoing"]} == {"edge_out"}


def test_entity_lineage_endpoint_respects_depth(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        session.add_all(
            [
                Entity(id="leaf", type="ticket", data={"title": "Leaf"}),
                Entity(id="parent", type="doc", data={"title": "Parent"}),
                Entity(id="grandparent", type="doc", data={"title": "Grandparent"}),
                Entity(id="great", type="doc", data={"title": "Great"}),
                Edge(
                    id="edge_parent",
                    source_id="parent",
                    target_id="leaf",
                    relationship="informs",
                    data={},
                ),
                Edge(
                    id="edge_grandparent",
                    source_id="grandparent",
                    target_id="parent",
                    relationship="owns",
                    data={},
                ),
                Edge(
                    id="edge_great",
                    source_id="great",
                    target_id="grandparent",
                    relationship="owns",
                    data={},
                ),
            ]
        )
        session.commit()
    engine.dispose()

    # enable_organizer=False: the organizer's EdgeProposer would inject
    # same_cluster_related edges during startup and break the exact-set asserts.
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/entities/leaf/lineage?depth=2").json()

    assert {node["id"] for node in payload["nodes"]} == {"leaf", "parent", "grandparent"}
    assert {edge["id"] for edge in payload["edges"]} == {"edge_parent", "edge_grandparent"}


def test_entity_lineage_handles_cycles(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    with session_local() as session:
        session.add_all(
            [
                Entity(id="a", type="doc", data={"title": "A"}),
                Entity(id="b", type="doc", data={"title": "B"}),
                Edge(id="edge_ba", source_id="b", target_id="a", relationship="links", data={}),
                Edge(id="edge_ab", source_id="a", target_id="b", relationship="links", data={}),
            ]
        )
        session.commit()
    engine.dispose()

    # enable_organizer=False: the organizer's EdgeProposer would inject
    # same_cluster_related edges during startup and break the exact-set asserts.
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/entities/a/lineage?depth=5").json()

    assert {node["id"] for node in payload["nodes"]} == {"a", "b"}
    assert {edge["id"] for edge in payload["edges"]} == {"edge_ba", "edge_ab"}


def test_entities_p95_under_50ms_for_100_rows(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)

    # Seed 100 entities quickly without going through higher layers.
    from axiom.storage import crud

    with session_local() as s:
        for i in range(100):
            crud.create_entity(s, "thread", {"title": f"t{i}", "metadata": {}}, source_id=None)

    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            r = client.get("/api/entities")
            dt = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            assert len(r.json()) == 100
            times.append(dt)

    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    assert p95 < 50.0


def test_ws_replay_since_seq(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        broadcaster: EventBroadcaster = app.state.broadcaster

        # Publish a few envelopes.
        import asyncio

        async def publish_many() -> None:
            for i in range(10):
                await broadcaster.publish({"type": "entity_added", "payload": {"i": i}})

        asyncio.run(publish_many())

        with client.websocket_connect("/ws/brain?since=5") as ws:
            msg1 = ws.receive_json()
            assert msg1["seq"] == 6
            msg2 = ws.receive_json()
            assert msg2["seq"] == 7


def test_demo_simulator_disabled_by_default_emits_no_agent_action_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("AXIOM_DEMO_SIMULATOR", raising=False)
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app):
        time.sleep(9.0)
        assert app.state.agent_action_task is None
        assert app.state.broadcaster.current_seq == 0
