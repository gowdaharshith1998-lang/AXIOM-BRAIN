from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Base, Entity
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


def test_sources_endpoint_returns_synthetic_rows(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        payload = client.get("/api/sources").json()

    assert [row["name"] for row in payload] == [
        "Slack",
        "Linear",
        "GitHub",
        "Notion",
        "Email",
        "Meetings",
    ]
    assert payload[0]["live"] is True


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
