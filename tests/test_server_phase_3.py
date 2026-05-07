from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Base
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

