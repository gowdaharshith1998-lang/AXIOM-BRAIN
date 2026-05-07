"""Phase 5.7.D — organizer agent behaviour."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uuid_utils as _uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.organize.agent import OrganizerAgent
from axiom.organize.classifier import HybridClassifier
from axiom.schema.models import Base, Entity


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []

    async def publish(self, envelope: dict[str, Any]) -> int:
        self.envelopes.append(envelope)
        return len(self.envelopes)


class _StubClassifier(HybridClassifier):
    def __init__(self, mapping: dict[str, str | None]) -> None:
        super().__init__(api_key="")
        self._mapping = mapping
        self.calls: list[str] = []

    def classify(self, entity: Entity) -> str | None:  # type: ignore[override]
        self.calls.append(entity.id)
        return self._mapping.get(entity.id)


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    db_url = f"sqlite:///{tmp_path / 'organizer.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    try:
        yield session_local
    finally:
        engine.dispose()


def _seed(
    session_factory: sessionmaker[Session],
    entities: list[tuple[str, str | None]],
) -> list[str]:
    """Seed entities. Return the list of resulting ids."""

    ids: list[str] = []
    with session_factory() as session:
        for raw_id, cluster_id in entities:
            entity = Entity(
                id=_uuid.uuid7().hex,
                type="document",
                data={"title": f"doc {raw_id}"},
                cluster_id=cluster_id,
            )
            session.add(entity)
            ids.append(entity.id)
        session.commit()
    return ids


@pytest.mark.asyncio
async def test_classifies_unclassified_entity(session_factory: sessionmaker[Session]) -> None:
    [a_id] = _seed(session_factory, [("a", None)])
    classifier = _StubClassifier({a_id: "billing_payments"})
    agent = OrganizerAgent(session_factory=session_factory, classifier=classifier)

    count = await agent.classify_pending()
    assert count == 1

    with session_factory() as session:
        entity = session.execute(select(Entity).where(Entity.id == a_id)).scalar_one()
        assert entity.cluster_id == "billing_payments"


@pytest.mark.asyncio
async def test_skips_already_classified(session_factory: sessionmaker[Session]) -> None:
    [_a, _b, c_id] = _seed(
        session_factory,
        [
            ("a", "engineering_code"),
            ("b", "billing_payments"),
            ("c", None),
        ],
    )
    classifier = _StubClassifier({c_id: "incidents_ops"})
    agent = OrganizerAgent(session_factory=session_factory, classifier=classifier)

    count = await agent.classify_pending()
    assert count == 1
    # only the unclassified entity was visited
    assert classifier.calls == [c_id]


@pytest.mark.asyncio
async def test_handles_classifier_failure_gracefully(
    session_factory: sessionmaker[Session],
) -> None:
    [a_id] = _seed(session_factory, [("a", None)])

    class _BoomClassifier(HybridClassifier):
        def __init__(self) -> None:
            super().__init__(api_key="")

        def classify(self, entity: Entity) -> str | None:  # type: ignore[override]
            raise RuntimeError("bad classifier")

    agent = OrganizerAgent(session_factory=session_factory, classifier=_BoomClassifier())

    count = await agent.classify_pending()
    assert count == 0
    # The entity remains unclassified.
    with session_factory() as session:
        entity = session.execute(select(Entity).where(Entity.id == a_id)).scalar_one()
        assert entity.cluster_id is None


@pytest.mark.asyncio
async def test_emits_event_after_classification(session_factory: sessionmaker[Session]) -> None:
    [a_id] = _seed(session_factory, [("a", None)])
    broadcaster = _FakeBroadcaster()
    classifier = _StubClassifier({a_id: "growth_product"})
    agent = OrganizerAgent(
        session_factory=session_factory,
        broadcaster=broadcaster,
        classifier=classifier,
    )

    await agent.classify_pending()

    assert len(broadcaster.envelopes) == 1
    envelope = broadcaster.envelopes[0]
    assert envelope["type"] == "entity_classified"
    assert envelope["payload"] == {"entity_id": a_id, "cluster_id": "growth_product"}
    assert envelope["persisted_id"] == a_id


@pytest.mark.asyncio
async def test_loop_continues_after_db_error(session_factory: sessionmaker[Session]) -> None:
    [a_id] = _seed(session_factory, [("a", None)])
    classifier = _StubClassifier({a_id: "billing_payments"})

    sleeps: list[float] = []
    iterations = 0

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        nonlocal iterations
        iterations += 1
        if iterations >= 3:
            agent._stop = True  # type: ignore[attr-defined]

    failures = {"count": 0}

    def flaky_factory() -> Session:
        if failures["count"] == 0:
            failures["count"] += 1
            raise RuntimeError("transient db hiccup")
        return session_factory()

    agent = OrganizerAgent(
        session_factory=flaky_factory,
        classifier=classifier,
        classify_interval_sec=0.0,
        sleeper=fake_sleep,
    )

    await agent.classify_loop()

    # We hit the failure once, then succeeded, then exited via _stop.
    with session_factory() as session:
        entity = session.execute(select(Entity).where(Entity.id == a_id)).scalar_one()
        assert entity.cluster_id == "billing_payments"


@pytest.mark.asyncio
async def test_backfill_classifies_all_pending(session_factory: sessionmaker[Session]) -> None:
    n = 45  # > one classify batch (20)
    pairs = [(f"x{i}", None) for i in range(n)]
    ids = _seed(session_factory, pairs)
    mapping: dict[str, str | None] = dict.fromkeys(ids, "people_teams")
    classifier = _StubClassifier(mapping)
    agent = OrganizerAgent(session_factory=session_factory, classifier=classifier)

    total = await agent.backfill_once()
    assert total == n

    with session_factory() as session:
        rows = session.execute(select(Entity)).scalars().all()
        assert all(row.cluster_id == "people_teams" for row in rows)


@pytest.mark.asyncio
async def test_recompute_centrality_runs(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory, [("a", None), ("b", None)])
    agent = OrganizerAgent(session_factory=session_factory)
    written = await agent.recompute_centrality()
    assert written == 2


@pytest.mark.asyncio
async def test_start_and_cancel_idempotent(session_factory: sessionmaker[Session]) -> None:
    classifier = _StubClassifier({})
    agent = OrganizerAgent(
        session_factory=session_factory,
        classifier=classifier,
        classify_interval_sec=10_000,
        centrality_interval_sec=10_000,
    )

    tasks_first = agent.start()
    tasks_second = agent.start()
    assert tasks_first is tasks_second

    await asyncio.sleep(0)  # let tasks pick up the stop flag once cancelled
    await agent.cancel()

    # cancelling a stopped agent is fine
    await agent.cancel()
