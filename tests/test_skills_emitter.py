from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import set_provider_key_with_session
from axiom.schema.models import Base, Edge, Entity, Receipt, Skill, SkillRun
from axiom.skills.registry import (
    activate_skill_with_session,
    archive_skill_with_session,
    get_skill_with_session,
    list_skills_with_session,
    register_skill_with_session,
)
from axiom.skills.runner import run_skill
from axiom.skills.skill_md import SkillManifestError, parse_skill_md, serialize_skill_md
from axiom.vault.crypto import ENV_VAR


@pytest.fixture()
def skill_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[sessionmaker[Session], str]]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'skills.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield sf, db_url
    engine.dispose()


def _fake_llm(monkeypatch: pytest.MonkeyPatch, content: str = '{"priority":"high"}') -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": [{"type": "text", "text": content}]}

    monkeypatch.setattr("axiom.skills.runner.httpx.post", lambda *a, **kw: Response())


def _register_priority_skill(session: Session):
    return register_skill_with_session(
        session,
        name="classify_ticket_priority",
        description="Classify support ticket priority",
        intent="classify",
        prompt_template="Classify: {ticket}",
        llm_provider="anthropic",
        llm_model="claude-3-haiku",
        output_schema={
            "type": "object",
            "required": ["priority"],
            "properties": {"priority": {"type": "string"}},
        },
    )


def _mcp_payload(result):
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        return json.loads(result[0].text)
    return result


def _process_entity(session: Session, entity_id: str = "process_refund") -> Entity:
    process = Entity(
        id=entity_id,
        type="process",
        data={
            "name": "Refund Review",
            "description": "Review refund requests",
            "steps": ["Classify the request", "Summarize the evidence"],
        },
        cluster_id="customer_support",
    )
    session.add(process)
    session.commit()
    return process


def _linked_decision(session: Session, process_id: str) -> None:
    decision = Entity(
        id="decision_refund_policy",
        type="decision",
        data={"title": "Refund policy decision", "summary": "Refunds over $500 need approval."},
        cluster_id="customer_support",
    )
    edge = Edge(
        id="edge_process_decision",
        source_id=process_id,
        target_id=decision.id,
        relationship="PROCESS_REFERENCES_DECISION",
        data={},
    )
    session.add_all([decision, edge])
    session.commit()


def test_emitter_emit_all_walks_all_process_entities(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        _process_entity(session)
        manifests = ProcessSkillEmitter(session).emit_all()
    assert [manifest.name for manifest in manifests] == ["refund_review"]


def test_emitter_emit_one_returns_manifest_for_one_process(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        process = _process_entity(session)
        manifest = ProcessSkillEmitter(session).emit_one(process.id)
    assert manifest.description == "Review refund requests"
    assert manifest.scope_clusters == ["customer_support"]


def test_emitter_infers_classify_intent_from_steps(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        process = _process_entity(session)
        assert ProcessSkillEmitter(session).emit_one(process.id).intent == "classify"


def test_emitter_infers_summarize_intent_from_steps(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        process = Entity(
            id="process_summary",
            type="process",
            data={"name": "Weekly Summary", "steps": ["Summarize the thread"]},
            cluster_id=None,
        )
        session.add(process)
        session.commit()
        assert ProcessSkillEmitter(session).emit_one(process.id).intent == "summarize"


def test_emitter_infers_transform_intent_as_fallback(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        process = Entity(id="process_generic", type="process", data={"name": "Generic Process"})
        session.add(process)
        session.commit()
        assert ProcessSkillEmitter(session).emit_one(process.id).intent == "transform"


def test_emitter_compiles_linked_decisions_into_prompt(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import ProcessSkillEmitter

    with sf() as session:
        process = _process_entity(session)
        _linked_decision(session, process.id)
        manifest = ProcessSkillEmitter(session).emit_one(process.id)
    assert "Refund policy decision" in manifest.prompt_template
    assert "Refunds over $500 need approval." in manifest.prompt_template


def test_compile_skills_idempotent_on_same_process(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import compile_skills_from_processes

    with sf() as session:
        _process_entity(session)
        first = compile_skills_from_processes(session)
        second = compile_skills_from_processes(session)
        assert first[0].id == second[0].id
        assert session.query(Skill).count() == 1


def test_compile_skills_emits_skill_compiled_ws_event(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.skills.emitter import compile_skills_from_processes

    events: list[tuple[str, dict[str, object]]] = []
    with sf() as session:
        _process_entity(session)
        compile_skills_from_processes(
            session,
            event_callback=lambda event_type, payload: events.append((event_type, payload)),
        )
    assert events[0][0] == "skill_compiled"


def test_compile_endpoint_dry_run_returns_manifests_without_persisting(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, db_url = skill_db
    from axiom.studio.server import create_app

    with sf() as session:
        _process_entity(session)
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/internal/skills/compile-from-processes", json={"dry_run": True}
        )
        assert response.status_code == 200
        assert response.json()["dry_run"] is True
        assert response.json()["compiled"][0]["name"] == "refund_review"
    with sf() as session:
        assert session.query(Skill).count() == 0


def test_r7_watchdog_rule_fires_for_uncompiled_process(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    from axiom.govern.watchdog_rules import process_without_compiled_skill

    with sf() as session:
        process = _process_entity(session)
        alert = process_without_compiled_skill(session, process, process.created_at)
    assert alert is not None
    assert alert.rule_id == "R7"


SKILL_MD = """---
name: classify_ticket_priority
description: Classify support ticket priority from text
intent: classify
llm_provider: anthropic
llm_model: claude-3-haiku-20240307
scope_clusters: [customer_support, incidents_ops]
trigger_type: event
trigger_config:
  event_type: ticket.created
output_schema:
  type: object
  required: [priority]
  properties:
    priority:
      type: string
---
Classify this support ticket.

Ticket: {ticket_title}
"""


def test_parse_skill_md_extracts_frontmatter_and_body() -> None:
    manifest = parse_skill_md(SKILL_MD)
    assert manifest.name == "classify_ticket_priority"
    assert manifest.scope_clusters == ["customer_support", "incidents_ops"]
    assert manifest.trigger_config == {"event_type": "ticket.created"}
    assert manifest.prompt_template == "Classify this support ticket.\n\nTicket: {ticket_title}\n"


def test_parse_skill_md_missing_required_field_raises() -> None:
    with pytest.raises(SkillManifestError, match="line 2"):
        parse_skill_md("---\nname: missing_intent\n---\nBody\n")


def test_parse_skill_md_invalid_yaml_raises_with_line_number() -> None:
    with pytest.raises(SkillManifestError, match="line 3"):
        parse_skill_md("---\nname: bad\noutput_schema: [unterminated\n---\nBody\n")


def test_parse_skill_md_handles_unicode_in_body() -> None:
    manifest = parse_skill_md(SKILL_MD + "\nEscalate if customer says café.\n")
    assert "café" in manifest.prompt_template


def test_serialize_skill_md_is_deterministic(skill_db: tuple[sessionmaker[Session], str]) -> None:
    sf, _db_url = skill_db
    with sf() as session:
        skill = _register_priority_skill(session)
        first = serialize_skill_md(skill)
        second = serialize_skill_md(skill)
    assert first == second
    assert first.startswith("---\n")


def test_serialize_then_parse_roundtrip_preserves_fields(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    with sf() as session:
        skill = _register_priority_skill(session)
        manifest = parse_skill_md(serialize_skill_md(skill))
    assert manifest.name == "classify_ticket_priority"
    assert manifest.output_schema["required"] == ["priority"]
    assert manifest.prompt_template == "Classify: {ticket}"


def test_skills_registry_crud(skill_db: tuple[sessionmaker[Session], str]) -> None:
    sf, _db_url = skill_db
    with sf() as session:
        skill = _register_priority_skill(session)
        assert skill.status == "draft"
        activated = activate_skill_with_session(session, skill.id)
        assert activated.status == "active"
        active = list_skills_with_session(session, status="active", intent="classify")
        assert active[0].id == skill.id
        assert get_skill_with_session(session, skill.id).name == "classify_ticket_priority"
        archived = archive_skill_with_session(session, skill.id)
        assert archived.status == "archived"


def test_skill_runner_happy_path_with_mocked_llm(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch)
    with sf() as session:
        skill = _register_priority_skill(session)
        activate_skill_with_session(session, skill.id)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(
        skill_id,
        {"ticket": "Production checkout is down"},
        "agent_runner",
        session_factory=sf,
    )
    assert result["run"]["status"] == "success"
    assert result["run"]["output_payload"] == {"priority": "high"}
    assert result["run"]["receipt_id"]

    with sf() as session:
        receipt = session.get(Receipt, result["run"]["receipt_id"])
        skill = get_skill_with_session(session, skill_id)
        assert receipt is not None
        assert receipt.action_id.startswith("skill_run:")
        assert skill.total_runs == 1


def test_skill_runner_failure_path(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch, content='{"wrong":"shape"}')
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(skill_id, {"ticket": "hello"}, "agent_runner", session_factory=sf)
    assert result["run"]["status"] == "failed"
    assert "missing required" in result["run"]["error_message"]
    assert result["run"]["receipt_id"]


def test_skill_run_failure_emits_skill_run_failed_ws_event(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch, content='{"wrong":"shape"}')
    events: list[tuple[str, dict[str, object]]] = []
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(
        skill_id,
        {"ticket": "hello"},
        "agent_runner",
        session_factory=sf,
        event_callback=lambda event_type, payload: events.append((event_type, payload)),
    )

    assert result["run"]["status"] == "failed"
    assert [event_type for event_type, _payload in events] == [
        "skill_run_started",
        "skill_run_failed",
    ]


def test_skill_run_failure_chains_receipt_with_decision_error(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch, content='{"wrong":"shape"}')
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(skill_id, {"ticket": "hello"}, "agent_runner", session_factory=sf)

    with sf() as session:
        receipt = session.get(Receipt, result["run"]["receipt_id"])
        assert receipt is not None
        assert receipt.decision == "error"
        assert receipt.action_id.startswith("skill_run:")


def test_skill_run_returns_receipt_id_in_response(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch)
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(skill_id, {"ticket": "down"}, "agent_runner", session_factory=sf)

    assert result["run"]["receipt_id"]


def test_skill_run_idempotency_key_dedupe_returns_cached_result(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    calls = 0

    def fake_call(*_args: object) -> str:
        nonlocal calls
        calls += 1
        return '{"priority":"high"}'

    monkeypatch.setattr("axiom.skills.runner._call_provider", fake_call)
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    first = run_skill(
        skill_id,
        {"ticket": "down"},
        "agent_runner",
        session_factory=sf,
        idempotency_key="idem-1",
    )
    second = run_skill(
        skill_id,
        {"ticket": "down"},
        "agent_runner",
        session_factory=sf,
        idempotency_key="idem-1",
    )

    assert first["run"]["id"] == second["run"]["id"]
    assert calls == 1


def test_skill_run_failed_receipt_demo_flag_follows_target(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch, content='{"wrong":"shape"}')
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(
        skill_id,
        {"ticket": "hello"},
        "agent_runner",
        session_factory=sf,
        receipt_demo_flag=True,
    )

    with sf() as session:
        receipt = session.get(Receipt, result["run"]["receipt_id"])
        assert receipt is not None
        assert receipt.demo_flag is True


@pytest.mark.asyncio
async def test_skill_mcp_tool_wiring(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _sf, db_url = skill_db
    _fake_llm(monkeypatch)
    monkeypatch.setenv("AXIOM_MCP_ALLOW_SYSTEM_PASSPORT", "1")
    from axiom.mcp.server import build_mcp_server

    mcp = build_mcp_server(db_url=db_url)
    registered = await mcp.call_tool(
        "axiom_register_skill",
        {
            "name": "summarize_note",
            "description": "Summarize a note",
            "intent": "summarize",
            "prompt_template": "Summarize {note}",
            "llm_provider": "anthropic",
            "llm_model": "claude-3-haiku",
        },
    )
    registered = _mcp_payload(registered)
    assert registered
    listed = _mcp_payload(await mcp.call_tool("axiom_list_skills", {}))
    assert listed
    discovered = listed["skills"][0]
    assert discovered["skill_md"].startswith("---\n")
    assert "name: summarize_note" in discovered["skill_md"]
    assert "Summarize {note}" in discovered["skill_md"]

    fetched = _mcp_payload(
        await mcp.call_tool("axiom_get_skill", {"skill_id": registered["skill"]["id"]})
    )
    assert fetched["skill"]["skill_md"] == discovered["skill_md"]


def test_skill_api_endpoints(skill_db: tuple[sessionmaker[Session], str]) -> None:
    _sf, db_url = skill_db
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/internal/skills",
            json={
                "name": "extract_company",
                "description": "Extract company",
                "intent": "extract",
                "prompt_template": "Extract {text}",
                "llm_provider": "anthropic",
                "llm_model": "claude-3-haiku",
            },
        )
        assert created.status_code == 200
        skill_id = created.json()["id"]
        assert client.get("/api/internal/skills").json()["skills"][0]["id"] == skill_id
        assert client.get(f"/api/internal/skills/{skill_id}").json()["name"] == "extract_company"
        assert client.get(f"/api/internal/skills/{skill_id}/runs").json()["runs"] == []
        archived = client.post(f"/api/internal/skills/{skill_id}/archive").json()
        assert archived["status"] == "archived"


def test_upload_md_endpoint_registers_skill(skill_db: tuple[sessionmaker[Session], str]) -> None:
    _sf, db_url = skill_db
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        uploaded = client.post("/api/internal/skills/upload-md", json={"content": SKILL_MD})
        assert uploaded.status_code == 200
        assert uploaded.json()["name"] == "classify_ticket_priority"
        assert uploaded.json()["trigger_type"] == "event"


def test_download_md_endpoint_returns_valid_skill_md(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    _sf, db_url = skill_db
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        uploaded = client.post("/api/internal/skills/upload-md", json={"content": SKILL_MD})
        skill_id = uploaded.json()["id"]
        response = client.get(f"/api/internal/skills/{skill_id}/md")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        manifest = parse_skill_md(response.text)
        assert manifest.name == "classify_ticket_priority"


def test_skill_archive_ws_broadcasts(skill_db: tuple[sessionmaker[Session], str]) -> None:
    _sf, db_url = skill_db
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/internal/skills",
            json={
                "name": "archive_me",
                "description": "Archive me",
                "intent": "summarize",
                "prompt_template": "Summarize {text}",
                "llm_provider": "openai",
                "llm_model": "gpt-4o-mini",
            },
        )
        skill_id = created.json()["id"]
        client.post(f"/api/internal/skills/{skill_id}/archive")
        with client.websocket_connect("/ws/brain?since=0") as ws:
            seen: set[str] = set()
            for _ in range(3):
                event = json.loads(ws.receive_text())
                seen.add(event["type"])
                if "skill_archived" in seen:
                    break
        assert "skill_archived" in seen


def test_skill_ws_broadcasts(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, db_url = skill_db
    _fake_llm(monkeypatch)
    with sf() as session:
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/internal/skills",
            json={
                "name": "classify_ticket_priority",
                "description": "Classify",
                "intent": "classify",
                "prompt_template": "Classify {ticket}",
                "llm_provider": "anthropic",
                "llm_model": "claude-3-haiku",
                "output_schema": {
                    "required": ["priority"],
                    "properties": {"priority": {"type": "string"}},
                },
            },
        )
        skill_id = created.json()["id"]
        client.post(
            f"/api/internal/skills/{skill_id}/run",
            json={"input_payload": {"ticket": "down"}},
        )
        with client.websocket_connect("/ws/brain?since=0") as ws:
            seen: set[str] = set()
            for _ in range(5):
                event = json.loads(ws.receive_text())
                seen.add(event["type"])
                if {"skill_registered", "skill_run_started", "skill_run_completed"}.issubset(seen):
                    break
        assert {"skill_registered", "skill_run_started", "skill_run_completed"}.issubset(seen)


def test_skill_receipt_linkage(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sf, _db_url = skill_db
    _fake_llm(monkeypatch)
    with sf() as session:
        skill = _register_priority_skill(session)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    run_skill(skill_id, {"ticket": "down"}, "agent_runner", session_factory=sf)
    with sf() as session:
        run = session.execute(select(SkillRun)).scalar_one()
        assert run.receipt_id is not None
        assert session.get(Receipt, run.receipt_id) is not None


def test_skill_activate_validates_trigger_config(
    skill_db: tuple[sessionmaker[Session], str],
) -> None:
    sf, _db_url = skill_db
    with sf() as session:
        skill = register_skill_with_session(
            session,
            name="monitor_feed",
            description="Monitor feed",
            intent="monitor",
            prompt_template="Check {item}",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            trigger_type="schedule",
            trigger_config={},
        )
        with pytest.raises(ValueError):
            activate_skill_with_session(session, skill.id)
