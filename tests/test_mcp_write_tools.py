from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.mcp.server import AxiomMCPService, build_mcp_server
from axiom.govern.policy_evaluator import DemoPolicyEvaluator, PolicyDecision
from axiom.schema.models import Base, Edge, Entity, Receipt, Skill, SkillRun, Source
from axiom.skills.registry import get_skill_with_session, register_skill_with_session
from axiom.studio.server import create_app


class _EventsStub:
    def __init__(self) -> None:
        self.steps_calls = 0
        self.action_batches: list[list[dict[str, object]]] = []

    def emit_steps(self, steps, *, agent_name: str = "external_mcp_client") -> None:  # type: ignore[no-untyped-def]
        self.steps_calls += 1

    def emit_action_events(self, *, events: list[dict[str, object]]) -> None:
        self.action_batches.append(events)


@pytest.fixture()
def write_service(tmp_path: Path) -> AxiomMCPService:
    db_url = f"sqlite:///{tmp_path / 'mcp_write.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with sf() as session:
        session.add_all(
            [
                Entity(
                    id="high_risky",
                    type="doc",
                    cluster_id="company_knowledge",
                    composite_importance=0.9,
                    data={"title": "High Risk Entity"},
                ),
                Entity(
                    id="neighbor_safe",
                    type="doc",
                    cluster_id="company_knowledge",
                    composite_importance=0.7,
                    data={"title": "Neighbor Safe"},
                ),
                Entity(
                    id="billing_1",
                    type="account",
                    cluster_id="billing_payments",
                    composite_importance=0.1,
                    data={"title": "Billing Profile"},
                ),
                Entity(
                    id="low_1",
                    type="task",
                    cluster_id="engineering_code",
                    composite_importance=0.2,
                    data={"title": "Low Importance"},
                ),
            ]
        )
        session.add(
            Edge(
                id="ed_high_neighbor",
                source_id="high_risky",
                target_id="neighbor_safe",
                relationship="related_to",
                data={},
            )
        )
        session.commit()

    service = AxiomMCPService(session_factory=sf, event_forwarder=_EventsStub())
    service._policy = DemoPolicyEvaluator(deny_rate=0)  # type: ignore[attr-defined]
    return service


def _events_stub(service: AxiomMCPService) -> _EventsStub:
    return service._events  # type: ignore[return-value]


class _StaticPolicy:
    def __init__(
        self,
        decision: str,
        *,
        reason: str = "blocked by test policy",
        policy_id: str = "AEGIS-TEST",
        guidance: str = "use the safer option",
        suggested_alternative: str | None = "safe_skill",
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.policy_id = policy_id
        self.guidance = guidance
        self.suggested_alternative = suggested_alternative

    def evaluate(self, *_args, **_kwargs) -> PolicyDecision:  # type: ignore[no-untyped-def]
        return PolicyDecision(
            self.decision,
            self.reason,
            self.policy_id,
            guidance=self.guidance,
            suggested_alternative=self.suggested_alternative,
        )


def _register_test_skill(service: AxiomMCPService) -> str:
    with service._session_factory() as session:  # type: ignore[attr-defined]
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


def test_record_action_allow_branch(write_service: AxiomMCPService) -> None:
    out = write_service.record_action(
        agent_name="agent_a",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read low entity",
        idempotency_key=None,
    )
    assert out["decision"] == "allow"
    assert out["demo"] is True
    assert out["receipt_id"]
    batches = _events_stub(write_service).action_batches
    assert len(batches) == 1
    assert [e["type"] for e in batches[0]] == ["agent_action", "agent_action_evaluated", "receipt_added"]


def test_record_action_against_real_entity_marked_real(write_service: AxiomMCPService) -> None:
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Source(id="linear-main", source_type="linear", display_name="Linear", connected=True))
        session.add(
            Entity(
                id="linear_ticket_1",
                type="ticket",
                source_id="linear-main",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Real Linear Ticket"},
            )
        )
        session.commit()

    out = write_service.record_action(
        agent_name="agent_real",
        intent="read",
        target_entity_id="linear_ticket_1",
        proposed_action="read real ticket",
        idempotency_key=None,
    )

    assert out["demo"] is False
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        receipt = session.query(Receipt).filter_by(action_id=out["action_id"]).one()
    assert receipt.demo_flag is False


def test_record_action_against_synthetic_entity_stays_demo(write_service: AxiomMCPService) -> None:
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            Entity(
                id="synthetic_ticket_1",
                type="ticket",
                source_id="synthetic-default",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Synthetic Ticket"},
            )
        )
        session.commit()

    out = write_service.record_action(
        agent_name="agent_synth",
        intent="read",
        target_entity_id="synthetic_ticket_1",
        proposed_action="read synthetic ticket",
        idempotency_key=None,
    )

    assert out["demo"] is True
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        receipt = session.query(Receipt).filter_by(action_id=out["action_id"]).one()
    assert receipt.demo_flag is True


def test_blocked_real_entity_event_marked_real(write_service: AxiomMCPService) -> None:
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Source(id="jira-main", source_type="jira", display_name="Jira", connected=True))
        session.add(
            Entity(
                id="jira_ticket_1",
                type="ticket",
                source_id="jira-main",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Blocked Real Ticket"},
            )
        )
        session.commit()
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]

    with pytest.raises(ToolError):
        write_service.record_action(
            agent_name="agent_blocked_real",
            intent="write",
            target_entity_id="jira_ticket_1",
            proposed_action="blocked write",
            idempotency_key=None,
        )

    batch = _events_stub(write_service).action_batches[0]
    assert batch[0]["payload"]["demo"] is False  # type: ignore[index]
    assert batch[1]["payload"]["demo_flag"] is False  # type: ignore[index]


def test_record_action_correct_branch(write_service: AxiomMCPService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_VAULT_KEY", "present")
    out = write_service.record_action(
        agent_name="agent_b",
        intent="delete",
        target_entity_id="high_risky",
        proposed_action="delete high entity",
        idempotency_key=None,
    )
    assert out["decision"] == "correct"
    assert out["guidance"]
    assert out["suggested_alternative"] == "neighbor_safe"


def test_record_action_deny_branch(write_service: AxiomMCPService) -> None:
    with pytest.raises(ToolError, match="policy_id=AEGIS"):
        write_service.record_action(
            agent_name="agent_c",
            intent="write",
            target_entity_id="billing_1",
            proposed_action="write billing data",
            idempotency_key=None,
        )


def test_record_action_idempotency_reuses_result(write_service: AxiomMCPService) -> None:
    first = write_service.record_action(
        agent_name="agent_d",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read 1",
        idempotency_key="idem-1",
    )
    second = write_service.record_action(
        agent_name="agent_d",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read 1 altered",
        idempotency_key="idem-1",
    )
    assert second == first
    batches = _events_stub(write_service).action_batches
    assert len(batches) == 1


def test_check_policy_branches_and_no_persistence(write_service: AxiomMCPService, monkeypatch: pytest.MonkeyPatch) -> None:
    allow = write_service.check_policy(
        agent_name="agent_e",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
    )
    assert allow["decision"] == "allow"

    monkeypatch.setenv("AXIOM_VAULT_KEY", "present")
    correct = write_service.check_policy(
        agent_name="agent_e",
        intent="delete",
        target_entity_id="high_risky",
        proposed_action="delete",
    )
    assert correct["decision"] == "correct"
    assert correct["suggested_alternative"] == "neighbor_safe"

    deny = write_service.check_policy(
        agent_name="agent_e",
        intent="write",
        target_entity_id="billing_1",
        proposed_action="write",
    )
    assert deny["decision"] == "deny"

    assert _events_stub(write_service).action_batches == []


def test_request_human_approval_happy_path(write_service: AxiomMCPService) -> None:
    recorded = write_service.record_action(
        agent_name="agent_f",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read before escalation",
        idempotency_key=None,
    )
    out = write_service.request_human_approval(
        action_id=str(recorded["action_id"]),
        reason="Need exception",
        agent_name="agent_f",
    )
    assert out["status"] == "pending"
    assert out["action_id"] == recorded["action_id"]
    assert out["demo"] is False


def test_request_human_approval_unknown_action_raises(write_service: AxiomMCPService) -> None:
    with pytest.raises(LookupError):
        write_service.request_human_approval(
            action_id="missing",
            reason="x",
            agent_name="agent_g",
        )


@pytest.mark.asyncio
async def test_request_human_approval_unknown_action_returns_tool_error(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'mcp_tool.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    mcp = build_mcp_server(db_url=db_url)
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "axiom_request_human_approval",
            {"action_id": "missing", "reason": "needs review", "agent_name": "agent_g"},
        )


def test_internal_agent_action_events_endpoint_caps_to_50(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'server_write.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url)
    with TestClient(app) as client:
        events = [
            {
                "type": "agent_action",
                "source_id": None,
                "persisted_id": f"act_{i}",
                "timestamp": 1,
                "payload": {"action_id": f"act_{i}"},
            }
            for i in range(80)
        ]
        resp = client.post("/api/internal/agent-action-events", json={"events": events})
        assert resp.status_code == 200
        assert resp.json()["emitted"] == 50


def test_record_action_latency_budget(write_service: AxiomMCPService) -> None:
    start = time.perf_counter()
    out = write_service.record_action(
        agent_name="agent_h",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
        idempotency_key=None,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["action_id"]
    assert elapsed_ms < 100


def test_check_policy_latency_budget(write_service: AxiomMCPService) -> None:
    start = time.perf_counter()
    out = write_service.check_policy(
        agent_name="agent_i",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["decision"] in {"allow", "correct", "deny"}
    assert elapsed_ms < 30


def test_request_human_approval_latency_budget(write_service: AxiomMCPService) -> None:
    recorded = write_service.record_action(
        agent_name="agent_j",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read",
        idempotency_key=None,
    )
    start = time.perf_counter()
    out = write_service.request_human_approval(
        action_id=str(recorded["action_id"]),
        reason="review",
        agent_name="agent_j",
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert out["status"] == "pending"
    assert elapsed_ms < 30


def test_run_skill_deny_blocks_llm_call(
    write_service: AxiomMCPService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_id = _register_test_skill(write_service)
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    calls = 0

    def fake_post(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("axiom.skills.runner.httpx.post", fake_post)
    with pytest.raises(ToolError, match="policy_id=AEGIS-TEST"):
        write_service.run_skill(skill_id=skill_id, input_payload={"note": "x"})
    assert calls == 0


def test_run_skill_deny_writes_single_receipt_no_run_row(write_service: AxiomMCPService) -> None:
    skill_id = _register_test_skill(write_service)
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    with pytest.raises(ToolError):
        write_service.run_skill(skill_id=skill_id, input_payload={"note": "x"})

    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        receipts = session.query(Receipt).all()
        runs = session.query(SkillRun).all()
    assert len(receipts) == 1
    assert receipts[0].decision == "deny"
    assert runs == []


def test_run_skill_correct_returns_alternative_no_llm_call(
    write_service: AxiomMCPService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_id = _register_test_skill(write_service)
    write_service._policy = _StaticPolicy("correct", suggested_alternative="safe_summary")  # type: ignore[attr-defined]
    calls = 0

    def fake_post(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("axiom.skills.runner.httpx.post", fake_post)
    out = write_service.run_skill(skill_id=skill_id, input_payload={"note": "x"})

    assert out["decision"] == "correct"
    assert out["suggested_alternative"] == "safe_summary"
    assert calls == 0
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        assert session.query(SkillRun).count() == 0
        receipt = session.query(Receipt).one()
    assert receipt.decision == "correct"
    assert receipt.suggested_alternative == "safe_summary"


def test_skill_run_receipt_demo_flag_follows_input(
    write_service: AxiomMCPService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_id = _register_test_skill(write_service)
    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Source(id="linear-main", source_type="linear", display_name="Linear", connected=True))
        session.add(
            Entity(
                id="linear_ticket_2",
                type="ticket",
                source_id="linear-main",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Another Real Ticket"},
            )
        )
        session.commit()

    monkeypatch.setattr("axiom.skills.runner.get_provider_key_plaintext_with_session", lambda *_args: "key")
    monkeypatch.setattr("axiom.skills.runner._call_provider", lambda *_args: "summary")

    out = write_service.run_skill(
        skill_id=skill_id,
        input_payload={"note": "x", "target_entity_id": "linear_ticket_2"},
    )

    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        run = session.get(SkillRun, out["run"]["id"])
        assert run is not None
        receipt = session.get(Receipt, run.receipt_id)
    assert receipt is not None
    assert receipt.demo_flag is False


def test_register_skill_deny_blocks_creation(write_service: AxiomMCPService) -> None:
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    with pytest.raises(ToolError, match="policy_id=AEGIS-TEST"):
        write_service.register_skill(
            name="blocked",
            description="Blocked",
            intent="summarize",
            prompt_template="Summarize {text}",
            llm_provider="anthropic",
            llm_model="claude-3-haiku",
        )

    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        assert session.query(Skill).count() == 0
        receipt = session.query(Receipt).one()
    assert receipt.decision == "deny"


def test_archive_skill_deny_blocks_archival(write_service: AxiomMCPService) -> None:
    skill_id = _register_test_skill(write_service)
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    with pytest.raises(ToolError, match="policy_id=AEGIS-TEST"):
        write_service.archive_skill(skill_id)

    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        skill = get_skill_with_session(session, skill_id)
        receipt = session.query(Receipt).one()
    assert skill.status == "draft"
    assert receipt.decision == "deny"


def test_record_action_deny_short_circuits(write_service: AxiomMCPService) -> None:
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    with pytest.raises(ToolError):
        write_service.record_action(
            agent_name="agent_blocked",
            intent="write",
            target_entity_id="low_1",
            proposed_action="blocked write",
            idempotency_key=None,
        )

    with write_service._session_factory() as session:  # type: ignore[attr-defined]
        receipts = session.query(Receipt).all()
    assert len(receipts) == 1
    assert receipts[0].decision == "deny"


def test_ws_emits_agent_action_blocked_on_deny(write_service: AxiomMCPService) -> None:
    write_service._policy = _StaticPolicy("deny")  # type: ignore[attr-defined]
    with pytest.raises(ToolError):
        write_service.record_action(
            agent_name="agent_blocked",
            intent="write",
            target_entity_id="low_1",
            proposed_action="blocked write",
            idempotency_key=None,
        )

    batches = _events_stub(write_service).action_batches
    assert len(batches) == 1
    assert [event["type"] for event in batches[0]] == ["agent_action_blocked", "receipt_added"]
