from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import ActionRequest, RealPolicyEvaluator, load_policies_from_dir
from axiom.schema.models import AgentPassport, Base, Entity, WatchdogAlert

STARTER_PACK = Path("policies/starter-pack")


@pytest.fixture()
def starter_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'starter.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture()
def starter_rules():
    return load_policies_from_dir(STARTER_PACK)


def _passport(**overrides: Any) -> AgentPassport:
    now = datetime.utcnow()
    values = {
        "passport_id": "passport_1",
        "agent_name": "agent_a",
        "agent_class": "external_mcp",
        "owner_email": "agent@example.com",
        "scope_clusters": ["billing_payments"],
        "scope_intents": ["read", "write", "skill:summarize_note"],
        "scope_skills": ["skill_1"],
        "issued_at": now,
        "expires_at": now + timedelta(hours=1),
        "not_before": None,
        "kill_switch": False,
        "revoked_at": None,
        "revocation_reason": None,
        "issuer_signature": "sig",
        "signing_scheme": "demo",
        "created_at": now,
    }
    values.update(overrides)
    return AgentPassport(**values)


def _action(**overrides: Any) -> ActionRequest:
    values: dict[str, Any] = {
        "agent_name": "agent_a",
        "intent": "write",
        "target_entity_id": "ent_1",
        "proposed_action": "update",
        "idempotency_key": None,
        "payload": {},
        "timestamp": datetime.utcnow(),
    }
    values.update(overrides)
    return ActionRequest(**values)


def _entity(**overrides: Any) -> Entity:
    values: dict[str, Any] = {
        "id": "ent_1",
        "type": "ticket",
        "cluster_id": "billing_payments",
        "source_id": "linear-main",
        "composite_importance": 0.8,
        "data": {"title": "Billing issue"},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    values.update(overrides)
    return Entity(**values)


def _decision(
    starter_rules,
    starter_sf: sessionmaker[Session],
    *,
    action: ActionRequest | None = None,
    passport: AgentPassport | None = None,
    entity: Entity | None = None,
):
    return RealPolicyEvaluator(starter_rules, starter_sf).evaluate(
        action or _action(),
        passport or _passport(),
        entity if entity is not None else _entity(),
    )


def test_starter_pack_loads_all_15_rules(starter_rules) -> None:
    assert len(starter_rules) == 15


def test_default_policy_root_includes_starter_pack_rules() -> None:
    rule_ids = {rule.rule_id for rule in load_policies_from_dir(Path("policies"))}
    assert "starter.passport.revoked" in rule_ids
    assert "starter.watchdog.cluster_outlier" in rule_ids


def test_starter_pack_rule_ids_are_namespaced(starter_rules) -> None:
    assert all(rule.rule_id.startswith("starter.") for rule in starter_rules)
    assert all(rule.metadata.get("customer_facing") is True for rule in starter_rules)


def test_starter_pack_passport_revoked_denies_action(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        passport=_passport(revoked_at=datetime.utcnow()),
    )
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.passport.revoked"


def test_starter_pack_passport_expired_denies_action(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        passport=_passport(expires_at=datetime.utcnow() - timedelta(seconds=1)),
    )
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.passport.expired"


def test_starter_pack_kill_switch_denies_action(starter_rules, starter_sf) -> None:
    decision = _decision(starter_rules, starter_sf, passport=_passport(kill_switch=True))
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.passport.kill_switch"


def test_starter_pack_scope_cluster_mismatch_corrects(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        passport=_passport(scope_clusters=["engineering_code"]),
    )
    assert decision.mode == "correct"
    assert decision.policy_id == "starter.scope.cluster_mismatch"


def test_starter_pack_scope_intent_denies(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        passport=_passport(scope_intents=["read"]),
    )
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.scope.intent_not_allowed"


def test_starter_pack_pii_in_payload_corrects_with_redaction(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        action=_action(intent="read", payload={"message": "email me person@example.com"}),
    )
    assert decision.mode == "correct"
    assert decision.policy_id == "starter.data.pii_in_payload"
    assert "redact" in (decision.guidance or "").lower()


def test_starter_pack_bulk_delete_pauses_above_threshold(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        action=_action(intent="delete", payload={"entity_count": 101}),
        passport=_passport(scope_intents=["delete"], scope_clusters=["billing_payments"]),
    )
    assert decision.mode == "pause"
    assert decision.policy_id == "starter.data.bulk_delete"


def test_starter_pack_off_hours_pauses_production_writes(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        action=_action(
            intent="write",
            payload={"environment": "production"},
            timestamp=datetime(2026, 5, 11, 22, 0, 0),
        ),
    )
    assert decision.mode == "pause"
    assert decision.policy_id == "starter.time.off_hours_production"


def test_starter_pack_rapid_repeat_denies_within_60_seconds(starter_rules, starter_sf) -> None:
    evaluator = RealPolicyEvaluator(starter_rules, starter_sf)
    first = _action(intent="read", timestamp=datetime(2026, 5, 11, 12, 0, 0))
    second = _action(intent="read", timestamp=datetime(2026, 5, 11, 12, 0, 30))
    assert evaluator.evaluate(first, _passport(), _entity()).mode == "allow"
    decision = evaluator.evaluate(second, _passport(), _entity())
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.time.rapid_repeat"


def test_starter_pack_low_confidence_corrects_with_warning(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        action=_action(intent="read", payload={"confidence": 0.2}),
    )
    assert decision.mode == "correct"
    assert decision.policy_id == "starter.confidence.low_decision"


def test_starter_pack_archived_entity_denies(starter_rules, starter_sf) -> None:
    decision = _decision(
        starter_rules,
        starter_sf,
        action=_action(intent="read"),
        entity=_entity(data={"archived": True}),
    )
    assert decision.mode == "deny"
    assert decision.policy_id == "starter.confidence.archived_entity"


def test_starter_pack_watchdog_critical_alert_pauses(
    starter_rules,
    starter_sf: sessionmaker[Session],
) -> None:
    with starter_sf() as session:
        session.add(_entity())
        session.add(
            WatchdogAlert(
                alert_id="alert_critical",
                entity_id="ent_1",
                rule_id="R1",
                severity="critical",
                reason="critical",
                evidence={},
                suggested_action="pause",
                status="open",
            )
        )
        session.commit()
    decision = _decision(starter_rules, starter_sf, action=_action(intent="read"))
    assert decision.mode == "pause"
    assert decision.policy_id == "starter.watchdog.critical_alert_on_target"


def test_starter_pack_watchdog_outlier_corrects(starter_rules, starter_sf: sessionmaker[Session]) -> None:
    with starter_sf() as session:
        session.add(_entity())
        session.add(
            WatchdogAlert(
                alert_id="alert_outlier",
                entity_id="ent_1",
                rule_id="R5",
                severity="warning",
                reason="outlier",
                evidence={},
                suggested_action="review",
                status="open",
            )
        )
        session.commit()
    decision = _decision(starter_rules, starter_sf, action=_action(intent="read"))
    assert decision.mode == "correct"
    assert decision.policy_id == "starter.watchdog.cluster_outlier"
