"""Tests for confidence_changed events from the OrganizerAgent centrality loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.organize.agent import OrganizerAgent
from axiom.organize.centrality import CentralityScorer
from axiom.schema.models import Base, Edge, Entity


class FakeBroadcaster:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, envelope: dict[str, Any]) -> int:
        self.events.append(envelope)
        return len(self.events)


def _make_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_emits_when_delta_exceeds_threshold() -> None:
    """Initial composite_importance=0.0 → recomputed value should trigger event."""
    sf = _make_session_factory()
    now = datetime.now(UTC)
    session = sf()
    for i in range(3):
        session.add(
            Entity(
                id=f"ent_{i}",
                type="entity",
                source_id="test",
                cluster_id="company_knowledge",
                composite_importance=0.0,
                created_at=now,
                updated_at=now,
                data={"title": f"Entity {i}"},
            )
        )
    for i in range(2):
        session.add(
            Edge(
                id=f"edge_{i}",
                source_id=f"ent_{i}",
                target_id=f"ent_{i + 1}",
                relationship="related",
                created_at=now,
                data={},
            )
        )
    session.commit()
    session.close()

    broadcaster = FakeBroadcaster()
    agent = OrganizerAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        scorer=CentralityScorer(),
    )
    asyncio.run(agent.recompute_centrality())

    conf_events = [e for e in broadcaster.events if e["type"] == "confidence_changed"]
    assert len(conf_events) > 0
    for ev in conf_events:
        assert ev["payload"]["demo"] is False
        assert "entity_id" in ev["payload"]
        assert "direction" in ev["payload"]


def test_no_event_on_tiny_delta() -> None:
    """If importance barely changes (< 0.05), no event should fire."""
    sf = _make_session_factory()
    now = datetime.now(UTC)
    session = sf()
    session.add(
        Entity(
            id="stable",
            type="entity",
            source_id="test",
            cluster_id="company_knowledge",
            composite_importance=0.20,
            created_at=now,
            updated_at=now,
            data={"title": "Stable entity"},
        )
    )
    session.commit()
    session.close()

    broadcaster = FakeBroadcaster()
    agent = OrganizerAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        scorer=CentralityScorer(),
    )
    asyncio.run(agent.recompute_centrality())

    conf_events = [e for e in broadcaster.events if e["type"] == "confidence_changed"]
    for ev in conf_events:
        assert abs(ev["payload"]["delta"]) >= 0.05


def test_direction_is_correct() -> None:
    sf = _make_session_factory()
    now = datetime.now(UTC)
    session = sf()
    session.add(
        Entity(
            id="rising_ent",
            type="entity",
            source_id="test",
            cluster_id="company_knowledge",
            composite_importance=0.0,
            created_at=now,
            updated_at=now,
            data={"title": "Should rise"},
        )
    )
    session.add(
        Entity(
            id="connected",
            type="entity",
            source_id="test",
            cluster_id="company_knowledge",
            composite_importance=0.0,
            created_at=now,
            updated_at=now,
            data={"title": "Connected"},
        )
    )
    session.add(
        Edge(
            id="e1",
            source_id="rising_ent",
            target_id="connected",
            relationship="related",
            created_at=now,
            data={},
        )
    )
    session.commit()
    session.close()

    broadcaster = FakeBroadcaster()
    agent = OrganizerAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        scorer=CentralityScorer(),
    )
    asyncio.run(agent.recompute_centrality())

    conf_events = [e for e in broadcaster.events if e["type"] == "confidence_changed"]
    rising = [e for e in conf_events if e["payload"]["direction"] == "rising"]
    assert len(rising) > 0
    for ev in rising:
        assert ev["payload"]["delta"] > 0
