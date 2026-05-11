from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import (
    ActionRequest,
    RealPolicyEvaluator,
    load_policies_from_dir,
    parse_policy_yaml,
)
from axiom.policy.dsl import PolicyParseError
from axiom.policy.predicates import contains_pii
from axiom.schema.models import AgentPassport, Base, Entity, WatchdogAlert


def _policy_yaml(when: str, then: str = "deny", **extra_then: Any) -> str:
    lines = [
        "rules:",
        "  - rule_id: test.rule",
        "    description: Test rule",
        "    severity: critical",
        f"    when: {when}",
        "    then:",
        f"      type: {then}",
        "      reason: \"Blocked {entity_id} for {agent_name}/{intent}\"",
    ]
    for key, value in extra_then.items():
        if value is None:
            continue
        lines.append(f"      {key}: {value!r}")
    return "\n".join(lines)


@pytest.fixture()
def policy_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'policy.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _passport(**overrides: Any) -> AgentPassport:
    now = datetime.utcnow()
    values = {
        "passport_id": "passport_1",
        "agent_name": "agent_a",
        "agent_class": "external_mcp",
        "owner_email": "agent@example.com",
        "scope_clusters": ["billing_payments"],
        "scope_intents": ["read", "write"],
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
        "idempotency_key": "idem_1",
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
        "composite_importance": 0.6,
        "data": {"title": "Billing issue"},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    values.update(overrides)
    return Entity(**values)


def test_parse_simple_allow_rule_from_yaml() -> None:
    rules = parse_policy_yaml(_policy_yaml('entity.type == "ticket"', then="allow"))
    assert [rule.rule_id for rule in rules] == ["test.rule"]
    assert rules[0].then.type == "allow"


def test_parse_correct_rule_with_guidance() -> None:
    rules = parse_policy_yaml(
        _policy_yaml(
            'data.payload contains_pii() == true',
            then="correct",
            guidance="Redact PII before retry",
            suggested_alternative={"redact": True},
        )
    )
    assert rules[0].then.type == "correct"
    assert rules[0].then.guidance == "Redact PII before retry"
    assert rules[0].then.suggested_alternative == {"redact": True}


def test_parse_deny_rule_with_reason_template() -> None:
    rules = parse_policy_yaml(_policy_yaml('passport.status == "revoked"'))
    assert rules[0].then.reason == "Blocked {entity_id} for {agent_name}/{intent}"


def test_parse_pause_rule_with_approval_role() -> None:
    rules = parse_policy_yaml(
        _policy_yaml(
            'watchdog.has_open_alert_on(entity) == true',
            then="pause",
            approval_required_role="ops",
            approval_timeout_seconds=600,
        )
    )
    assert rules[0].then.type == "pause"
    assert rules[0].then.approval_required_role == "ops"
    assert rules[0].then.approval_timeout_seconds == 600


def test_parse_complex_predicate_with_and_or_not() -> None:
    rules = parse_policy_yaml(
        _policy_yaml(
            '(entity.type == "ticket" and action.intent in ["delete", "destroy"]) '
            'or not passport.scope_clusters contains entity.cluster_id'
        )
    )
    assert rules[0].when.to_source()


def test_parse_invalid_yaml_raises_with_line_number() -> None:
    with pytest.raises(PolicyParseError, match="line"):
        parse_policy_yaml("rules:\n  - rule_id: bad\n    when: [")


def test_parse_unknown_predicate_raises() -> None:
    with pytest.raises(PolicyParseError, match="unknown predicate"):
        parse_policy_yaml(_policy_yaml("policy_magic(entity) == true"))


def test_load_policies_from_dir_orders_files_lexically(tmp_path: Path) -> None:
    (tmp_path / "10-second.yaml").write_text(
        _policy_yaml('entity.type == "document"').replace("test.rule", "second.rule"),
        encoding="utf-8",
    )
    (tmp_path / "00-first.yaml").write_text(
        _policy_yaml('entity.type == "ticket"').replace("test.rule", "first.rule"),
        encoding="utf-8",
    )
    assert [rule.rule_id for rule in load_policies_from_dir(tmp_path)] == [
        "first.rule",
        "second.rule",
    ]


def test_evaluate_returns_first_matching_rule(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(
        """
rules:
  - rule_id: first.match
    description: First
    severity: warning
    when: entity.cluster_id == "billing_payments"
    then: {type: correct, reason: "first", guidance: "use readonly"}
  - rule_id: second.match
    description: Second
    severity: critical
    when: entity.type == "ticket"
    then: {type: deny, reason: "second"}
"""
    )
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(_action(), _passport(), _entity())
    assert decision.mode == "correct"
    assert decision.policy_id == "first.match"
    assert decision.guidance == "use readonly"


def test_evaluate_allow_when_no_rule_matches_default(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(_policy_yaml('entity.type == "document"'))
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(_action(), _passport(), _entity())
    assert decision.mode == "allow"
    assert decision.policy_id == "default.allow"


def test_evaluate_deny_revoked_passport(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(_policy_yaml('passport.status == "revoked"'))
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(
        _action(), _passport(revoked_at=datetime.utcnow()), _entity()
    )
    assert decision.mode == "deny"
    assert decision.policy_id == "test.rule"


def test_evaluate_pause_for_billing_change_when_watchdog_alert_exists(
    policy_sf: sessionmaker[Session],
) -> None:
    with policy_sf() as session:
        session.add(_entity())
        session.add(
            WatchdogAlert(
                alert_id="alert_1",
                entity_id="ent_1",
                rule_id="R1",
                severity="critical",
                reason="billing alert",
                evidence={},
                suggested_action="pause",
                status="open",
            )
        )
        session.commit()
    rules = parse_policy_yaml(
        _policy_yaml(
            'entity.cluster_id == "billing_payments" and '
            'watchdog.alert_count(entity, severity="critical") > 0',
            then="pause",
            approval_required_role="ops",
        )
    )
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(_action(), _passport(), _entity())
    assert decision.mode == "pause"
    assert decision.policy_id == "test.rule"


def test_evaluate_correct_with_pii_redaction_guidance(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(
        _policy_yaml(
            "data.payload contains_pii() == true",
            then="correct",
            guidance="Redact personal data before retry",
        )
    )
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(
        _action(payload={"body": "call me at 415-555-1212"}), _passport(), _entity()
    )
    assert decision.mode == "correct"
    assert "Redact" in (decision.guidance or "")


def test_evaluate_handles_missing_entity_gracefully(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(_policy_yaml('entity.type == "ticket"'))
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(_action(), _passport(), None)
    assert decision.mode == "allow"


def test_evaluate_template_substitution_works(policy_sf: sessionmaker[Session]) -> None:
    rules = parse_policy_yaml(_policy_yaml('action.intent == "write"'))
    decision = RealPolicyEvaluator(rules, policy_sf).evaluate(_action(), _passport(), _entity())
    assert decision.reason == "Blocked ent_1 for agent_a/write"


def test_pii_detector_finds_email_ssn_phone_in_payload() -> None:
    assert contains_pii({"email": "person@example.com"})
    assert contains_pii({"ssn": "123-45-6789"})
    assert contains_pii({"phone": "(415) 555-1212"})
