from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uuid_utils as _uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.organize.edge_proposer import EdgeProposer
from axiom.schema.models import Base, Edge, Entity
from axiom.storage import crud


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []

    async def publish(self, envelope: dict[str, Any]) -> int:
        self.envelopes.append(envelope)
        return len(self.envelopes)


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'edges.db'}", future=True)
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    try:
        yield local
    finally:
        engine.dispose()


def _entity(cluster_id: str) -> Entity:
    return Entity(
        id=_uuid.uuid7().hex,
        type="document",
        data={"title": cluster_id},
        cluster_id=cluster_id,
        composite_importance=0.8,
    )


@pytest.mark.asyncio
async def test_edge_proposer_creates_edges_in_db(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add_all([_entity("billing_payments"), _entity("billing_payments")])
        session.commit()
        created = await EdgeProposer().propose_once(session)
        assert created == 1
        assert session.execute(select(Edge)).scalars().first() is not None


@pytest.mark.asyncio
async def test_edge_proposer_broadcasts_event(session_factory: sessionmaker[Session]) -> None:
    broadcaster = _FakeBroadcaster()
    with session_factory() as session:
        session.add_all([_entity("incidents_ops"), _entity("incidents_ops")])
        session.commit()
        await EdgeProposer(broadcaster=broadcaster).propose_once(session)

    assert broadcaster.envelopes
    envelope = broadcaster.envelopes[0]
    assert envelope["type"] == "entity_edge_created"
    assert envelope["payload"]["relation_type"] == "same_cluster_related"


@pytest.mark.asyncio
async def test_edge_proposer_only_proposes_within_same_cluster(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all([_entity("billing_payments"), _entity("engineering_code")])
        session.commit()
        created = await EdgeProposer().propose_once(session)
        assert created == 0


@pytest.mark.asyncio
async def test_edge_proposer_handles_db_error_gracefully(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("db down")

    monkeypatch.setattr(crud, "add_edge", boom)
    with session_factory() as session:
        session.add_all([_entity("people_teams"), _entity("people_teams")])
        session.commit()
        created = await EdgeProposer().propose_once(session)
        assert created == 0
