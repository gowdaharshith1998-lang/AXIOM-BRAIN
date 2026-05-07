from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.schema.models import Edge, Entity
from axiom.sources.base import IngestEvent
from axiom.sources.synthetic import SyntheticSource
from axiom.storage import crud


@pytest.mark.asyncio
async def test_pipeline_round_trip_inserts_entities_and_edges(db_session) -> None:  # type: ignore[no-untyped-def]
    broadcaster = EventBroadcaster()
    src = SyntheticSource()
    pipeline = IngestPipeline(source=src, session=db_session, broadcaster=broadcaster)

    count = await pipeline.run()
    assert count >= 250

    entity_count = db_session.execute(select(func.count(Entity.id))).scalar_one()
    edge_count = db_session.execute(select(func.count(Edge.id))).scalar_one()

    assert entity_count == 100
    assert edge_count >= 150

    # All 7 types present
    types = dict(db_session.execute(select(Entity.type, func.count()).group_by(Entity.type)).all())
    assert set(types.keys()) == {
        "code",
        "people",
        "decision",
        "thread",
        "ticket",
        "document",
        "process",
    }


def test_entities_preserve_metadata_subdict(db_session) -> None:  # type: ignore[no-untyped-def]
    fixture_path = Path(__file__).parent.parent / "fixtures" / "synthetic_company.json"
    d = json.loads(fixture_path.read_text(encoding="utf-8"))
    e0 = d["entities"][0]
    dto = crud.create_entity(
        db_session, e0["type"], {"metadata": e0["metadata"]}, source_id="synthetic-default"
    )

    fetched = crud.get_entity(db_session, dto.id)
    assert fetched is not None
    assert fetched.data["metadata"]["calibra_state"] is None
    assert fetched.data["metadata"]["calibra_confidence"] is None


@pytest.mark.asyncio
async def test_pipeline_broadcasts_persisted_ids(db_session) -> None:  # type: ignore[no-untyped-def]
    broadcaster = EventBroadcaster()
    src = SyntheticSource()
    pipeline = IngestPipeline(source=src, session=db_session, broadcaster=broadcaster)

    # Subscribe from seq 0 and collect a few envelopes while ingest runs.
    envelopes: list[dict] = []

    async def collect() -> None:
        async for env in broadcaster.subscribe(since=0):
            envelopes.append(env)
            if len(envelopes) >= 10:
                return

    import asyncio

    await asyncio.gather(pipeline.run(), collect())

    assert envelopes[0]["seq"] == 1
    # entity_added envelopes must have persisted_id set
    entity_envs = [e for e in envelopes if e["type"] == "entity_added"]
    assert entity_envs and all(e["persisted_id"] for e in entity_envs)


@pytest.mark.asyncio
async def test_pipeline_skips_edges_when_nick_missing(db_session) -> None:  # type: ignore[no-untyped-def]
    class MinimalSource:
        source_id = "synthetic-default"
        source_type = "synthetic"

        async def discover(self):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        async def ingest(self, since=None):  # type: ignore[no-untyped-def]
            yield IngestEvent(
                event_id="e1",
                event_type="entity_added",
                source_id=self.source_id,
                occurred_at=__import__("datetime").datetime.utcnow(),
                entity={"nick": "x", "type": "thread", "data": {}, "metadata": {}},
            )
            yield IngestEvent(
                event_id="e2",
                event_type="edge_added",
                source_id=self.source_id,
                occurred_at=__import__("datetime").datetime.utcnow(),
                edge={
                    "source_nick": "missing",
                    "target_nick": "x",
                    "relationship": "THREAD_REFERENCES_DOCUMENT",
                    "data": {},
                },
            )

        def metadata(self):  # type: ignore[no-untyped-def]
            return {}

        async def watch(self, on_event):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        async def disconnect(self) -> None:
            return None

    broadcaster = EventBroadcaster()
    pipeline = IngestPipeline(source=MinimalSource(), session=db_session, broadcaster=broadcaster)  # type: ignore[arg-type]
    count = await pipeline.run()
    assert count == 2

    edge_count = db_session.execute(select(func.count(Edge.id))).scalar_one()
    assert edge_count == 0

