from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.agent_registry import (
    backfill_agent_registry_from_receipts,
    upsert_agent_observation,
)
from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.mcp.server import AxiomMCPService
from axiom.schema.models import AgentRegistry, Base, Entity
from axiom.studio.server import create_app


def _session_factory(tmp_path: Path, name: str = "agent_registry.db") -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / name}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="low_1",
                type="task",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Low Importance"},
            )
        )
        session.commit()
    return sf


def _receipt_payload(
    index: int,
    *,
    agent_name: str,
    decision: str,
) -> ReceiptInsert:
    return ReceiptInsert(
        id=f"receipt_{index}",
        action_id=f"act_{index}",
        agent_name=agent_name,
        intent="read",
        target_entity_id="low_1",
        cluster_id="engineering_code",
        decision=decision,
        reason="test",
        policy_id="policy.test",
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature=f"sig_{index}",
        demo_flag=True,
    )


def test_upsert_agent_observation_counts_and_types(db_session: Session) -> None:
    now = datetime.utcnow()
    upsert_agent_observation(
        db_session,
        agent_name="organizer",
        decision="allow",
        intent="classify",
        action_id="act_1",
        observed_at=now,
    )
    upsert_agent_observation(
        db_session,
        agent_name="cursor",
        decision="deny",
        intent="write",
        action_id="act_2",
        observed_at=now + timedelta(seconds=1),
    )
    db_session.commit()

    rows = {row.agent_name: row for row in db_session.execute(select(AgentRegistry)).scalars()}
    assert rows["organizer"].agent_type == "internal"
    assert rows["organizer"].allow_count == 1
    assert rows["cursor"].agent_type == "external_mcp"
    assert rows["cursor"].deny_count == 1


def test_record_action_persists_agent_registry_row(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    service = AxiomMCPService(session_factory=sf)

    out = service.record_action(
        agent_name="claude",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read low entity",
        idempotency_key=None,
    )

    with sf() as session:
        row = session.get(AgentRegistry, "claude")
        assert row is not None
        assert row.total_actions == 1
        assert row.last_action_id == out["action_id"]
        assert row.agent_type == "external_mcp"


def test_backfill_agent_registry_from_receipts(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    chain_insert_receipt(sf, _receipt_payload(1, agent_name="agent_a", decision="allow"))
    chain_insert_receipt(sf, _receipt_payload(2, agent_name="agent_a", decision="deny"))
    with sf() as session:
        session.query(AgentRegistry).delete()
        session.commit()
        written = backfill_agent_registry_from_receipts(session)

    with sf() as session:
        row = session.get(AgentRegistry, "agent_a")
        assert written == 2
        assert row is not None
        assert row.total_actions == 2
        assert row.allow_count == 1
        assert row.deny_count == 1


def test_agent_registry_endpoint_filters_by_type_and_days(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'endpoint.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        upsert_agent_observation(
            session,
            agent_name="organizer",
            decision="allow",
            intent="classify",
            action_id="act_1",
        )
        upsert_agent_observation(
            session,
            agent_name="cursor",
            decision="correct",
            intent="edit",
            action_id="act_2",
        )
        session.commit()
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/agent-registry?days=30&type=external_mcp").json()

    assert [row["agent_name"] for row in payload["agents"]] == ["cursor"]
    assert payload["agents"][0]["correct_count"] == 1


def test_agent_registry_register_endpoint_issues_passport(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'register_endpoint.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/internal/agent-registry",
            json={
                "name": "builder",
                "agent_class": "external_mcp",
                "owner_email": "ops@example.com",
                "issue_new_passport": True,
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["agent_name"] == "builder"
        assert payload["passport_status"] == "active"
        assert payload["bearer_token"]

        listed = client.get("/api/internal/agent-registry").json()["agents"]
        assert listed[0]["agent_name"] == "builder"
        assert listed[0]["owner_email"] == "ops@example.com"


def test_agent_registry_register_endpoint_returns_validation_errors(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'register_validation.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/internal/agent-registry",
            json={
                "name": "qa_agent",
                "agent_class": "qa",
                "owner_email": "ops@example.com",
                "issue_new_passport": True,
            },
        )

    assert response.status_code == 422
    assert "invalid agent_class" in response.json()["detail"]


def test_mcp_stats_includes_observed_agents_from_registry(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'stats.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        upsert_agent_observation(
            session,
            agent_name="cursor",
            decision="allow",
            intent="read",
            action_id="act_1",
        )
        session.commit()
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/mcp-stats").json()

    assert payload["observed_agents"] == ["cursor"]


def test_agent_registry_smoke_three_actions_two_agents(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'smoke.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="low_1",
                type="task",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Low Importance"},
            )
        )
        session.commit()
    service = AxiomMCPService(session_factory=sf)
    service.record_action(
        agent_name="agent_a",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
        idempotency_key=None,
    )
    service.record_action(
        agent_name="agent_b",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
        idempotency_key=None,
    )
    service.record_action(
        agent_name="agent_a",
        intent="write",
        target_entity_id="low_1",
        proposed_action="write",
        idempotency_key=None,
    )
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/agent-registry?days=30&type=external_mcp").json()
    rows = {row["agent_name"]: row for row in payload["agents"]}

    assert set(rows) == {"agent_a", "agent_b"}
    assert rows["agent_a"]["total_actions"] == 2
    assert rows["agent_b"]["total_actions"] == 1
