from __future__ import annotations

import struct
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.demo_flag import is_demo_target
from axiom.govern.watchdog import WatchdogAgent, detect_for_entity, list_open_alerts
from axiom.schema.models import Base, Edge, Entity, EntityEmbedding, Receipt, Source
from axiom.studio.server import create_app


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []
        self.current_seq = 0

    async def publish(self, envelope: dict[str, Any]) -> int:
        self.current_seq += 1
        self.envelopes.append({**envelope, "seq": self.current_seq})
        return self.current_seq

    async def subscribe(self, *, since: int = 0):  # type: ignore[no-untyped-def]
        if False:
            yield since


@pytest.fixture()
def watchdog_sf(tmp_path: Path) -> Iterator[tuple[sessionmaker[Session], str]]:
    db_url = f"sqlite:///{tmp_path / 'watchdog.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield sf, db_url
    engine.dispose()


def _entity(
    entity_id: str,
    *,
    type_: str = "document",
    cluster_id: str | None = None,
    source_id: str | None = None,
    data: dict[str, Any] | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    importance: float = 0.0,
) -> Entity:
    now = datetime.utcnow()
    return Entity(
        id=entity_id,
        type=type_,
        cluster_id=cluster_id,
        source_id=source_id,
        data=data or {"title": entity_id},
        created_at=created_at or now,
        updated_at=updated_at or created_at or now,
        composite_importance=importance,
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relationship: str = "related",
    **data: Any,
) -> Edge:
    return Edge(
        id=edge_id,
        source_id=source,
        target_id=target,
        relationship=relationship,
        data=data,
    )


def _embedding(entity_id: str, values: list[float]) -> EntityEmbedding:
    return EntityEmbedding(
        entity_id=entity_id,
        embedding=struct.pack(f"{len(values)}f", *values),
        content_hash=f"hash_{entity_id}",
        model="test",
    )


def _detect_rules(session: Session, entity_id: str, now: datetime) -> set[str]:
    return {alert.rule_id for alert in detect_for_entity(session, entity_id, now=now)}


def test_r1_billing_change_without_decision_positive(db_session: Session) -> None:
    now = datetime.utcnow()
    db_session.add(_entity("bill_change", cluster_id="billing_payments"))
    db_session.commit()
    assert "R1" in _detect_rules(db_session, "bill_change", now)


def test_r1_billing_change_with_recent_decision_negative(db_session: Session) -> None:
    now = datetime.utcnow()
    db_session.add_all(
        [
            _entity("bill_change", cluster_id="billing_payments"),
            _entity("decision_recent", type_="decision", updated_at=now),
            _edge("edge_decision", "bill_change", "decision_recent"),
        ]
    )
    db_session.commit()
    assert "R1" not in _detect_rules(db_session, "bill_change", now)


def test_r2_p1_ticket_without_runbook_positive(db_session: Session) -> None:
    db_session.add(_entity("ticket_p1", type_="ticket", data={"priority": "p1", "title": "Down"}))
    db_session.commit()
    assert "R2" in _detect_rules(db_session, "ticket_p1", datetime.utcnow())


def test_r2_p1_ticket_with_incident_runbook_negative(db_session: Session) -> None:
    db_session.add_all(
        [
            _entity("ticket_p1", type_="ticket", data={"priority": "p1"}),
            _entity(
                "runbook",
                type_="document",
                cluster_id="incidents_ops",
                data={"doc_type": "runbook"},
            ),
            _edge("edge_runbook", "ticket_p1", "runbook"),
        ]
    )
    db_session.commit()
    assert "R2" not in _detect_rules(db_session, "ticket_p1", datetime.utcnow())


def test_r3_policy_doc_orphaned_positive(db_session: Session) -> None:
    old = datetime.utcnow() - timedelta(days=45)
    db_session.add(_entity("policy_old", type_="policy", created_at=old, updated_at=old))
    db_session.commit()
    assert "R3" in _detect_rules(db_session, "policy_old", datetime.utcnow())


def test_r3_policy_doc_with_inbound_edge_negative(db_session: Session) -> None:
    old = datetime.utcnow() - timedelta(days=45)
    db_session.add_all(
        [
            _entity("policy_old", type_="policy", created_at=old, updated_at=old),
            _entity("owner_process", type_="process"),
            _edge("edge_policy", "owner_process", "policy_old"),
        ]
    )
    db_session.commit()
    assert "R3" not in _detect_rules(db_session, "policy_old", datetime.utcnow())


def test_r4_confidence_drift_high_positive(db_session: Session) -> None:
    db_session.add(
        _entity(
            "drifted",
            data={"previous_composite_importance": 0.82},
            importance=0.42,
        )
    )
    db_session.commit()
    assert "R4" in _detect_rules(db_session, "drifted", datetime.utcnow())


def test_r4_confidence_drift_low_negative(db_session: Session) -> None:
    db_session.add(
        _entity(
            "steady",
            data={"previous_composite_importance": 0.7},
            importance=0.45,
        )
    )
    db_session.commit()
    assert "R4" not in _detect_rules(db_session, "steady", datetime.utcnow())


def test_r5_cluster_outlier_positive(db_session: Session) -> None:
    db_session.add_all(
        [
            _entity("peer_a", cluster_id="billing_payments"),
            _entity("peer_b", cluster_id="billing_payments"),
            _entity("outlier", cluster_id="billing_payments"),
            _embedding("peer_a", [1.0, 0.0]),
            _embedding("peer_b", [1.0, 0.0]),
            _embedding("outlier", [-1.0, 0.0]),
        ]
    )
    db_session.commit()
    assert "R5" in _detect_rules(db_session, "outlier", datetime.utcnow())


def test_r5_cluster_member_near_centroid_negative(db_session: Session) -> None:
    db_session.add_all(
        [
            _entity("peer_a", cluster_id="billing_payments"),
            _entity("peer_b", cluster_id="billing_payments"),
            _entity("nearby", cluster_id="billing_payments"),
            _embedding("peer_a", [1.0, 0.0]),
            _embedding("peer_b", [1.0, 0.0]),
            _embedding("nearby", [0.9, 0.1]),
        ]
    )
    db_session.commit()
    assert "R5" not in _detect_rules(db_session, "nearby", datetime.utcnow())


def test_r6_stale_decision_referenced_positive(db_session: Session) -> None:
    old = datetime.utcnow() - timedelta(days=120)
    db_session.add_all(
        [
            _entity("dependent", type_="process"),
            _entity("old_decision", type_="decision", updated_at=old, created_at=old),
            _edge(
                "edge_old_decision", "dependent", "old_decision", "depends_on", load_bearing=True
            ),
        ]
    )
    db_session.commit()
    assert "R6" in _detect_rules(db_session, "dependent", datetime.utcnow())


def test_r6_fresh_decision_reference_negative(db_session: Session) -> None:
    db_session.add_all(
        [
            _entity("dependent", type_="process"),
            _entity("fresh_decision", type_="decision"),
            _edge(
                "edge_fresh_decision",
                "dependent",
                "fresh_decision",
                "depends_on",
                load_bearing=True,
            ),
        ]
    )
    db_session.commit()
    assert "R6" not in _detect_rules(db_session, "dependent", datetime.utcnow())


@pytest.mark.asyncio
async def test_watchdog_loop_emits_ws_and_receipt(
    watchdog_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = watchdog_sf
    with sf() as session:
        session.add(_entity("bill_change", cluster_id="billing_payments"))
        session.commit()

    broadcaster = _FakeBroadcaster()
    agent: WatchdogAgent

    async def sleeper(_delay: float) -> None:
        agent._stop = True  # type: ignore[attr-defined]

    agent = WatchdogAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        debounce_sec=0.0,
        sleeper=sleeper,
    )
    await agent.handle_entity_event("bill_change")
    await agent._debounce_loop()  # type: ignore[attr-defined]

    assert any(event["type"] == "watchdog_alert_raised" for event in broadcaster.envelopes)
    with sf() as session:
        assert session.execute(select(Receipt)).scalar_one().decision == "advise"


@pytest.mark.asyncio
async def test_watchdog_receipt_demo_flag_follows_entity_source(
    watchdog_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = watchdog_sf
    with sf() as session:
        session.add(
            Source(id="linear-main", source_type="linear", display_name="Linear", connected=True)
        )
        session.add(
            _entity(
                "bill_change_real",
                cluster_id="billing_payments",
                source_id="linear-main",
            )
        )
        session.commit()

    broadcaster = _FakeBroadcaster()
    agent = WatchdogAgent(session_factory=sf, broadcaster=broadcaster)
    created = await agent.detect_entity("bill_change_real")

    assert created == 1
    with sf() as session:
        alert = session.execute(select(Receipt)).scalar_one()
    assert alert.demo_flag is False


def test_is_demo_target_handles_missing_entity(db_session: Session) -> None:
    assert is_demo_target(db_session, "missing") is True


def test_watchdog_ack_and_resolve_endpoints(watchdog_sf: tuple[sessionmaker[Session], str]) -> None:
    sf, db_url = watchdog_sf
    with sf() as session:
        session.add(_entity("bill_change", cluster_id="billing_payments"))
        session.commit()
        [alert] = detect_for_entity(session, "bill_change")
        alert_id = alert.alert_id

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        acknowledged = client.post(f"/api/internal/watchdog/alerts/{alert_id}/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "acknowledged"
        resolved = client.post(
            f"/api/internal/watchdog/alerts/{alert_id}/resolve",
            json={"resolution_note": "Linked to DEC-1"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["evidence"]["resolution_note"] == "Linked to DEC-1"


def test_watchdog_deduplicates_active_alerts(db_session: Session) -> None:
    db_session.add(_entity("bill_change", cluster_id="billing_payments"))
    db_session.commit()

    first = detect_for_entity(db_session, "bill_change")
    second = detect_for_entity(db_session, "bill_change")

    assert len(first) == 1
    assert second == []


def test_watchdog_lists_open_alerts_by_cluster(db_session: Session) -> None:
    db_session.add_all(
        [
            _entity("bill_change", cluster_id="billing_payments"),
            _entity(
                "ticket_p1", type_="ticket", cluster_id="incidents_ops", data={"priority": "p1"}
            ),
        ]
    )
    db_session.commit()
    detect_for_entity(db_session, "bill_change")
    detect_for_entity(db_session, "ticket_p1")

    rows = list_open_alerts(db_session, cluster_id="billing_payments")

    assert [row.entity_id for row in rows] == ["bill_change"]
