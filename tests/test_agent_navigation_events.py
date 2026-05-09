"""Tests for agent_navigation_step events from the OrganizerAgent centrality loop."""
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


def _seed_entities(session_factory, count: int = 5, with_edges: bool = True):
    now = datetime.now(UTC)
    session = session_factory()
    entities = []
    for i in range(count):
        e = Entity(
            id=f"ent_{i}",
            type="entity",
            source_id="test",
            cluster_id="company_knowledge",
            composite_importance=0.3,
            created_at=now,
            updated_at=now,
            data={"title": f"Entity {i}"},
        )
        session.add(e)
        entities.append(e)
    if with_edges and count >= 2:
        for i in range(count - 1):
            edge = Edge(
                id=f"edge_{i}",
                source_id=f"ent_{i}",
                target_id=f"ent_{i + 1}",
                relationship="related",
                created_at=now,
                data={},
            )
            session.add(edge)
    session.commit()
    session.close()
    return entities


def test_centrality_loop_emits_navigation_steps() -> None:
    sf = _make_session_factory()
    _seed_entities(sf, count=5)
    broadcaster = FakeBroadcaster()
    agent = OrganizerAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        scorer=CentralityScorer(),
    )
    asyncio.run(agent.recompute_centrality())

    nav_events = [e for e in broadcaster.events if e["type"] == "agent_navigation_step"]
    assert len(nav_events) > 0
    sample = nav_events[0]
    assert sample["payload"]["agent_name"] == "organizer"
    assert sample["payload"]["demo"] is False
    assert "from_id" in sample["payload"]
    assert "to_id" in sample["payload"]


def test_navigation_throttle_max_50() -> None:
    sf = _make_session_factory()
    _seed_entities(sf, count=80)
    session = sf()
    now = datetime.now(UTC)
    for i in range(80):
        for j in range(i + 1, min(i + 3, 80)):
            session.add(
                Edge(
                    id=f"edge_{i}_{j}",
                    source_id=f"ent_{i}",
                    target_id=f"ent_{j}",
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

    nav_events = [e for e in broadcaster.events if e["type"] == "agent_navigation_step"]
    assert len(nav_events) <= 50


def test_no_navigation_events_when_no_entities() -> None:
    sf = _make_session_factory()
    broadcaster = FakeBroadcaster()
    agent = OrganizerAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        scorer=CentralityScorer(),
    )
    asyncio.run(agent.recompute_centrality())

    nav_events = [e for e in broadcaster.events if e["type"] == "agent_navigation_step"]
    assert len(nav_events) == 0
