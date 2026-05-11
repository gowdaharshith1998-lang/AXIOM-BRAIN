from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.watchdog import WatchdogAgent, detect_for_entity
from axiom.policy import ActionRequest, RealPolicyEvaluator, load_policies, reload_policies
from axiom.policy.watchdog_integration import watchdog_rules_as_policies
from axiom.schema.models import Base, Entity, WatchdogAlert
from axiom.studio.server import create_app


class _Broadcaster:
    def __init__(self) -> None:
        self.current_seq = 0
        self.envelopes: list[dict[str, Any]] = []

    async def publish(self, envelope: dict[str, Any]) -> int:
        self.current_seq += 1
        self.envelopes.append({**envelope, "seq": self.current_seq})
        return self.current_seq

    async def subscribe(self, *, since: int = 0):  # type: ignore[no-untyped-def]
        if False:
            yield since


@pytest.fixture()
def watchdog_policy_sf(tmp_path: Path) -> tuple[sessionmaker[Session], str]:
    db_url = f"sqlite:///{tmp_path / 'watchdog_policy.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="billing_1",
                type="account",
                cluster_id="billing_payments",
                composite_importance=0.3,
                data={"title": "Billing Change"},
            )
        )
        session.commit()
    return sf, db_url


def _passport() -> object:
    return type(
        "Passport",
        (),
        {
            "passport_id": "passport_1",
            "agent_name": "agent_a",
            "scope_clusters": ["*"],
            "scope_intents": ["*"],
            "scope_skills": ["*"],
            "kill_switch": False,
            "revoked_at": None,
            "expires_at": datetime(2099, 1, 1),
        },
    )()


def test_watchdog_r1_fires_as_policy_pause_when_billing_alert_open(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = watchdog_policy_sf
    with sf() as session:
        session.add(
            WatchdogAlert(
                alert_id="alert_r1",
                entity_id="billing_1",
                rule_id="R1",
                severity="warning",
                reason="billing",
                evidence={},
                suggested_action="review",
                status="open",
            )
        )
        session.commit()
        entity = session.get(Entity, "billing_1")
    rules = watchdog_rules_as_policies()
    decision = RealPolicyEvaluator(rules, sf).evaluate(
        ActionRequest(
            agent_name="agent_a",
            intent="write",
            target_entity_id="billing_1",
            proposed_action="write billing",
            idempotency_key=None,
            payload={},
        ),
        _passport(),
        entity,
    )
    assert decision.mode == "pause"
    assert decision.policy_id == "watchdog.R1.billing_change_without_decision"


def test_watchdog_r2_fires_as_policy_pause_when_p1_ticket_no_runbook(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = watchdog_policy_sf
    with sf() as session:
        ticket = Entity(id="ticket_1", type="ticket", data={"priority": "p1"})
        session.add(ticket)
        session.add(
            WatchdogAlert(
                alert_id="alert_r2",
                entity_id="ticket_1",
                rule_id="R2",
                severity="critical",
                reason="p1",
                evidence={},
                suggested_action="attach runbook",
                status="open",
            )
        )
        session.commit()
    decision = RealPolicyEvaluator(watchdog_rules_as_policies(), sf).evaluate(
        ActionRequest("agent_a", "write", "ticket_1", "update", None, {}),
        _passport(),
        ticket,
    )
    assert decision.mode == "pause"
    assert decision.policy_id == "watchdog.R2.ticket_severity_mismatch_runbook"


def test_watchdog_rules_evaluate_before_user_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXIOM_POLICY_DIR", raising=False)
    reload_policies()
    rules = load_policies()
    assert rules[0].rule_id.startswith("watchdog.")


def test_watchdog_rules_appear_in_policy_list_endpoint(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    _sf, db_url = watchdog_policy_sf
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/policies?source=watchdog")
    assert response.status_code == 200
    assert response.json()["rules"][0]["rule_id"].startswith("watchdog.")


@pytest.mark.asyncio
async def test_watchdog_alert_raised_emits_policy_clause_activated_ws_event(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = watchdog_policy_sf
    broadcaster = _Broadcaster()
    agent = WatchdogAgent(
        session_factory=sf,
        broadcaster=broadcaster,
        debounce_sec=0.01,
        sweep_interval_sec=60,
    )
    with sf() as session:
        alerts = detect_for_entity(session, "billing_1", now=datetime.utcnow())
        assert alerts
    await agent._emit_alert(alerts[0])  # noqa: SLF001
    assert any(event["type"] == "policy_clause_activated" for event in broadcaster.envelopes)


def test_policy_list_filters_by_source(watchdog_policy_sf: tuple[sessionmaker[Session], str]) -> None:
    _sf, db_url = watchdog_policy_sf
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        starter = client.get("/api/internal/policies?source=starter_pack").json()["rules"]
        watchdog = client.get("/api/internal/policies?source=watchdog").json()["rules"]
    assert starter and all(rule["metadata"]["source"] == "starter_pack" for rule in starter)
    assert watchdog and all(rule["metadata"]["source"] == "watchdog" for rule in watchdog)


def test_active_policies_for_entity_returns_applicable_rules(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, db_url = watchdog_policy_sf
    with sf() as session:
        session.add(
            WatchdogAlert(
                alert_id="alert_r1",
                entity_id="billing_1",
                rule_id="R1",
                severity="warning",
                reason="billing",
                evidence={},
                suggested_action="review",
                status="open",
            )
        )
        session.commit()
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/policies/active?entity_id=billing_1")
    assert response.status_code == 200
    assert response.json()["rules"][0]["rule_id"].startswith("watchdog.R1")


def test_active_policies_recompute_on_entity_change(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, db_url = watchdog_policy_sf
    app = create_app(db_url=db_url, enable_organizer=False)
    with sf() as session:
        entity = session.get(Entity, "billing_1")
        assert entity is not None
        entity.data = {"archived": True}
        session.add(entity)
        session.commit()
    with TestClient(app) as client:
        before = client.get("/api/internal/policies/active?entity_id=billing_1").json()["rules"]
    assert any(rule["rule_id"] == "starter.confidence.archived_entity" for rule in before)


def test_active_policies_recompute_on_watchdog_alert(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, db_url = watchdog_policy_sf
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        before = client.get("/api/internal/policies/active?entity_id=billing_1").json()["rules"]
    with sf() as session:
        session.add(
            WatchdogAlert(
                alert_id="alert_r1",
                entity_id="billing_1",
                rule_id="R1",
                severity="warning",
                reason="billing",
                evidence={},
                suggested_action="review",
                status="open",
            )
        )
        session.commit()
    with TestClient(app) as client:
        after = client.get("/api/internal/policies/active?entity_id=billing_1").json()["rules"]
    assert len(after) > len(before)


def test_acknowledging_watchdog_alert_removes_policy_clause(
    watchdog_policy_sf: tuple[sessionmaker[Session], str],
) -> None:
    sf, db_url = watchdog_policy_sf
    with sf() as session:
        session.add(
            WatchdogAlert(
                alert_id="alert_r1",
                entity_id="billing_1",
                rule_id="R1",
                severity="warning",
                reason="billing",
                evidence={},
                suggested_action="review",
                status="resolved",
            )
        )
        session.commit()
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/policies/active?entity_id=billing_1")
    assert not [r for r in response.json()["rules"] if r["rule_id"].startswith("watchdog.R1")]
