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
from axiom.schema.models import Base, Receipt, SkillRun
from axiom.skills.registry import (
    activate_skill_with_session,
    archive_skill_with_session,
    get_skill_with_session,
    list_skills_with_session,
    register_skill_with_session,
)
from axiom.skills.runner import run_skill
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
    assert result["run"]["receipt_id"] is None


@pytest.mark.asyncio
async def test_skill_mcp_tool_wiring(
    skill_db: tuple[sessionmaker[Session], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _sf, db_url = skill_db
    _fake_llm(monkeypatch)
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
    assert registered
    listed = await mcp.call_tool("axiom_list_skills", {})
    assert listed


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
