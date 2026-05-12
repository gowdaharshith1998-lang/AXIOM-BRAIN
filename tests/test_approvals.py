from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.approvals import (
    approve_request,
    create_approval_request,
    deny_request,
    expire_old_requests,
    list_pending_approvals,
)
from axiom.govern.policy_evaluator import get_policy_evaluator
from axiom.mcp.server import AxiomMCPService
from axiom.policy import ActionRequest, PolicyDecision, reload_policies
from axiom.schema.models import ApprovalRequest, Base, Entity, Receipt
from axiom.skills.registry import register_skill_with_session
from axiom.skills.runner import run_skill
from axiom.studio.server import create_app


def _write_pause_policy(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "00-pause.yaml").write_text(
        """
rules:
  - rule_id: test.pause.billing
    description: Pause billing writes
    severity: critical
    when: entity.cluster_id == "billing_payments" or action.intent == "skill:summarize_note"
    then:
      type: pause
      reason: "pause {intent} for {entity_id}"
      approval_required_role: ops
      approval_timeout_seconds: 60
""",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _allow_demo_passport_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_MCP_ALLOW_SYSTEM_PASSPORT", "1")


@pytest.fixture()
def approval_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'approvals.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="billing_1",
                type="account",
                cluster_id="billing_payments",
                composite_importance=0.2,
                data={"title": "Billing"},
            )
        )
        session.commit()
    return sf


@pytest.fixture()
def pause_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    policy_dir = tmp_path / "policies"
    _write_pause_policy(policy_dir)
    monkeypatch.setenv("AXIOM_POLICY_DIR", str(policy_dir))
    reload_policies()
    return policy_dir


def _action(**overrides: Any) -> ActionRequest:
    values: dict[str, Any] = {
        "agent_name": "agent_a",
        "intent": "write",
        "target_entity_id": "billing_1",
        "proposed_action": "write billing",
        "idempotency_key": "idem",
        "payload": {"amount": 10},
        "timestamp": datetime.utcnow(),
    }
    values.update(overrides)
    return ActionRequest(**values)


def _decision() -> PolicyDecision:
    return PolicyDecision(
        mode="pause",
        reason="pause write for billing_1",
        policy_id="test.pause.billing",
        guidance="review",
    )


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


def test_approval_request_created_when_policy_pauses(
    approval_sf: sessionmaker[Session],
) -> None:
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    assert approval.status == "pending"
    assert approval.policy_id == "test.pause.billing"
    assert approval.resume_token


def test_approval_pending_status_blocks_action_execution(
    approval_sf: sessionmaker[Session],
    pause_policy: Path,
) -> None:
    service = AxiomMCPService(session_factory=approval_sf)
    out = service.record_action(
        agent_name="agent_a",
        intent="write",
        target_entity_id="billing_1",
        proposed_action="write billing",
        idempotency_key=None,
    )
    assert out["decision"] == "pause"
    assert out["approval_id"]
    with approval_sf() as session:
        assert session.query(ApprovalRequest).count() == 1
        assert session.query(Receipt).one().decision == "pause"


def test_approve_request_resumes_action_execution(approval_sf: sessionmaker[Session]) -> None:
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    resolved = approve_request(approval_sf, approval.id, by_user="ops@example.com", note="ok")
    assert resolved.status == "approved"
    assert resolved.resolved_by == "ops@example.com"
    assert resolved.resolved_at is not None


def test_deny_request_chains_deny_receipt(approval_sf: sessionmaker[Session]) -> None:
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    resolved = deny_request(approval_sf, approval.id, by_user="ops@example.com", note="no")
    assert resolved.status == "denied"
    with approval_sf() as session:
        receipt = session.query(Receipt).one()
        assert receipt.decision == "deny"
        assert receipt.policy_id == "test.pause.billing"


def test_expire_old_requests_marks_status_expired(approval_sf: sessionmaker[Session]) -> None:
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    with approval_sf() as session:
        row = session.get(ApprovalRequest, approval.id)
        assert row is not None
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    expired = expire_old_requests(approval_sf)
    assert [row.id for row in expired] == [approval.id]
    assert expired[0].status == "expired"


def test_approve_request_emits_ws_event(approval_sf: sessionmaker[Session]) -> None:
    events: list[dict[str, Any]] = []
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    approve_request(
        approval_sf,
        approval.id,
        by_user="ops@example.com",
        note="ok",
        event_callback=lambda event_type, payload: events.append({"type": event_type, **payload}),
    )
    assert events[0]["type"] == "approval_approved"


def test_deny_request_emits_ws_event(approval_sf: sessionmaker[Session]) -> None:
    events: list[dict[str, Any]] = []
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    deny_request(
        approval_sf,
        approval.id,
        by_user="ops@example.com",
        note="no",
        event_callback=lambda event_type, payload: events.append({"type": event_type, **payload}),
    )
    assert events[0]["type"] == "approval_denied"


def test_list_pending_approvals_filters_by_role(approval_sf: sessionmaker[Session]) -> None:
    create_approval_request(approval_sf, _action(), None, _decision())
    assert len(list_pending_approvals(approval_sf, filter_by_role="ops")) == 1
    assert list_pending_approvals(approval_sf, filter_by_role="finance") == []


def test_approval_endpoints_require_explicit_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause_policy: Path,
) -> None:
    db_url = f"sqlite:///{tmp_path / 'approval_api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    approval = create_approval_request(sf, _action(), None, _decision())
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.post(
            f"/api/internal/approvals/{approval.id}/approve", json={"note": "ok"}
        )
    assert response.status_code == 422


def test_approval_persists_resume_token_for_skill_runs(
    approval_sf: sessionmaker[Session],
    pause_policy: Path,
) -> None:
    skill_id = _register_skill(approval_sf)
    out = run_skill(
        skill_id,
        {"note": "x"},
        "agent_a",
        session_factory=approval_sf,
        policy_evaluator=get_policy_evaluator(approval_sf),
    )
    assert out["status"] == "pending_approval"
    with approval_sf() as session:
        row = session.get(ApprovalRequest, out["approval_id"])
        assert row is not None
        assert row.resume_token


def test_skill_run_resumes_after_approval_with_same_input(
    approval_sf: sessionmaker[Session],
    pause_policy: Path,
) -> None:
    approval = create_approval_request(
        approval_sf,
        _action(intent="skill:summarize_note", payload={"note": "x"}),
        None,
        _decision(),
    )
    resolved = approve_request(approval_sf, approval.id, by_user="ops@example.com", note="ok")
    assert resolved.proposed_action["payload"] == {"note": "x"}
    assert resolved.status == "approved"


def test_expired_approval_chains_expired_receipt(approval_sf: sessionmaker[Session]) -> None:
    approval = create_approval_request(approval_sf, _action(), None, _decision())
    with approval_sf() as session:
        row = session.get(ApprovalRequest, approval.id)
        assert row is not None
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    expire_old_requests(approval_sf)
    with approval_sf() as session:
        receipt = session.query(Receipt).one()
        assert receipt.decision == "expired"
