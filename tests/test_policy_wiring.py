from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.passports import issue_passport
from axiom.govern.policy_evaluator import DemoPolicyEvaluator, get_policy_evaluator
from axiom.mcp.server import AxiomMCPService
from axiom.policy import RealPolicyEvaluator, load_policies, reload_policies
from axiom.schema.models import Base, Entity, Receipt, SkillRun
from axiom.skills.registry import register_skill_with_session
from axiom.skills.runner import run_skill
from axiom.studio.server import create_app


def _write_policy(root: Path, when: str, action: str = "deny", rule_id: str = "test.real") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "00-test.yaml").write_text(
        f"""
rules:
  - rule_id: {rule_id}
    description: Test real policy
    severity: critical
    when: {when}
    then:
      type: {action}
      reason: "real policy blocked {{intent}}"
      guidance: "real guidance"
""",
        encoding="utf-8",
    )


@pytest.fixture()
def wiring_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'policy_wiring.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="billing_1",
                type="account",
                cluster_id="billing_payments",
                composite_importance=0.3,
                data={"title": "Billing"},
            )
        )
        session.commit()
    return sf


def _register_skill(sf: sessionmaker[Session]) -> str:
    with sf() as session:
        skill = register_skill_with_session(
            session,
            name="summarize_note",
            description="Summarize",
            intent="summarize",
            prompt_template="Summarize {note}",
            llm_provider="anthropic",
            llm_model="claude-3-haiku",
        )
        return skill.id


def _issue_token(
    sf: sessionmaker[Session],
    *,
    intents: list[str],
    skills: list[str] | None = None,
) -> str:
    _row, token = issue_passport(
        sf,
        agent_name="agent_a",
        agent_class="external_mcp",
        owner_email="ops@example.com",
        scope_clusters=["billing_payments", "external_mcp"],
        scope_intents=intents,
        scope_skills=skills or [],
        ttl_hours=1,
    )
    return token


def _clear_policy_cache(monkeypatch: pytest.MonkeyPatch, policy_dir: Path | None) -> None:
    if policy_dir is None:
        monkeypatch.delenv("AXIOM_POLICY_DIR", raising=False)
    else:
        monkeypatch.setenv("AXIOM_POLICY_DIR", str(policy_dir))
    reload_policies()


def test_default_evaluator_loads_from_policies_dir_at_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"')
    _clear_policy_cache(monkeypatch, policy_dir)

    evaluator = get_policy_evaluator(wiring_sf)

    assert isinstance(evaluator, RealPolicyEvaluator)


def test_evaluator_factory_loads_watchdog_clauses_if_policies_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    _clear_policy_cache(monkeypatch, tmp_path / "missing")

    evaluator = get_policy_evaluator(wiring_sf)

    assert isinstance(evaluator, RealPolicyEvaluator)
    assert evaluator.rules
    assert evaluator.rules[0].rule_id.startswith("watchdog.")


def test_real_evaluator_falls_back_to_demo_on_invalid_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "invalid.yaml").write_text("rules:\n  - rule_id:", encoding="utf-8")
    monkeypatch.setenv("AXIOM_POLICY_DIR", str(policy_dir))
    load_policies.cache_clear()

    evaluator = get_policy_evaluator(wiring_sf)

    assert isinstance(evaluator, DemoPolicyEvaluator)


def test_mcp_record_action_uses_real_evaluator_when_passport_provided(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'entity.cluster_id == "billing_payments"')
    _clear_policy_cache(monkeypatch, policy_dir)
    service = AxiomMCPService(session_factory=wiring_sf)
    token = _issue_token(wiring_sf, intents=["write"])

    with pytest.raises(ToolError, match="policy_id=test.real"):
        service.record_action(
            agent_name="agent_a",
            intent="write",
            target_entity_id="billing_1",
            proposed_action="write billing",
            idempotency_key=None,
            passport_token=token,
        )


def test_mcp_record_action_deny_returns_real_policy_id_not_demo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"', rule_id="custom.deny")
    _clear_policy_cache(monkeypatch, policy_dir)
    service = AxiomMCPService(session_factory=wiring_sf)
    token = _issue_token(wiring_sf, intents=["write"])

    with pytest.raises(ToolError, match="policy_id=custom.deny"):
        service.record_action(
            agent_name="agent_a",
            intent="write",
            target_entity_id="billing_1",
            proposed_action="write billing",
            idempotency_key=None,
            passport_token=token,
        )


def test_skill_run_pre_flight_uses_real_evaluator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "skill:summarize_note"')
    _clear_policy_cache(monkeypatch, policy_dir)
    skill_id = _register_skill(wiring_sf)
    service = AxiomMCPService(session_factory=wiring_sf)
    token = _issue_token(wiring_sf, intents=["invoke_skill"], skills=[skill_id])

    with pytest.raises(ToolError, match="policy_id=test.real"):
        service.run_skill(skill_id=skill_id, input_payload={"note": "x"}, passport_token=token)


def test_skill_run_blocked_by_real_policy_returns_deny_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "skill:summarize_note"')
    _clear_policy_cache(monkeypatch, policy_dir)
    skill_id = _register_skill(wiring_sf)
    service = AxiomMCPService(session_factory=wiring_sf)
    token = _issue_token(wiring_sf, intents=["invoke_skill"], skills=[skill_id])

    with pytest.raises(ToolError):
        service.run_skill(skill_id=skill_id, input_payload={"note": "x"}, passport_token=token)

    with wiring_sf() as session:
        receipt = session.query(Receipt).one()
        assert receipt.policy_id == "test.real"
        assert receipt.decision == "deny"
        assert session.query(SkillRun).count() == 0


def test_run_skill_direct_pre_flight_uses_real_evaluator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "skill:summarize_note"')
    _clear_policy_cache(monkeypatch, policy_dir)
    skill_id = _register_skill(wiring_sf)

    out = run_skill(
        skill_id,
        {"note": "x"},
        "agent_a",
        session_factory=wiring_sf,
        policy_evaluator=get_policy_evaluator(wiring_sf),
    )

    assert out["status"] == "denied"
    assert out["policy_id"] == "test.real"


def test_policies_endpoint_lists_current_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"', rule_id="api.rule")
    _clear_policy_cache(monkeypatch, policy_dir)
    db_url = f"sqlite:///{tmp_path / 'api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app) as client:
        response = client.get("/api/internal/policies?source=custom")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["rules"][0]["rule_id"] == "api.rule"


def test_reload_policies_endpoint_picks_up_new_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"', rule_id="api.before")
    _clear_policy_cache(monkeypatch, policy_dir)
    db_url = f"sqlite:///{tmp_path / 'reload.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app) as client:
        _write_policy(policy_dir, 'action.intent == "delete"', rule_id="api.after")
        response = client.post("/api/internal/policies/reload")

    assert response.status_code == 200
    custom_rules = [
        rule for rule in response.json()["rules"] if rule["metadata"]["source"] == "custom"
    ]
    assert len(custom_rules) == 1
    assert custom_rules[0]["rule_id"] == "api.after"


def test_policy_detail_endpoint_fetches_one_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"', rule_id="api.detail")
    _clear_policy_cache(monkeypatch, policy_dir)
    db_url = f"sqlite:///{tmp_path / 'detail.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app) as client:
        response = client.get("/api/internal/policies/api.detail")

    assert response.status_code == 200
    assert response.json()["rule_id"] == "api.detail"


def test_evaluation_includes_real_policy_id_in_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wiring_sf: sessionmaker[Session],
) -> None:
    policy_dir = tmp_path / "policies"
    _write_policy(policy_dir, 'action.intent == "write"', rule_id="receipt.real")
    _clear_policy_cache(monkeypatch, policy_dir)
    service = AxiomMCPService(session_factory=wiring_sf)
    token = _issue_token(wiring_sf, intents=["write"])

    with pytest.raises(ToolError):
        service.record_action(
            agent_name="agent_a",
            intent="write",
            target_entity_id="billing_1",
            proposed_action="write billing",
            idempotency_key=None,
            passport_token=token,
        )

    with wiring_sf() as session:
        assert session.query(Receipt).one().policy_id == "receipt.real"
