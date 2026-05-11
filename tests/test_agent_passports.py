from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.passports import (
    SYSTEM_PASSPORT_ID,
    PassportError,
    _demo_signature,
    check_scope,
    issue_passport,
    revoke_passport,
    toggle_kill_switch,
    verify_passport,
)
from axiom.mcp.server import AxiomMCPService
from axiom.schema.models import AgentPassport, Base, Entity, Receipt, SkillRun
from axiom.skills.registry import register_skill_with_session
from axiom.studio.server import create_app


@pytest.fixture()
def passport_db(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'passports.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture()
def passport_service(passport_db: sessionmaker[Session]) -> AxiomMCPService:
    with passport_db() as session:
        session.add_all(
            [
                Entity(
                    id="eng_1",
                    type="doc",
                    cluster_id="engineering_code",
                    composite_importance=0.1,
                    data={"title": "Engineering Note"},
                ),
                Entity(
                    id="eng_2",
                    type="doc",
                    cluster_id="engineering_code",
                    composite_importance=0.1,
                    data={"title": "Second Engineering Note"},
                ),
            ]
        )
        session.commit()
    return AxiomMCPService(session_factory=passport_db)


def _issue(
    sf: sessionmaker[Session],
    *,
    clusters: list[str] | None = None,
    intents: list[str] | None = None,
    skills: list[str] | None = None,
    ttl_hours: int = 1,
) -> tuple[str, str]:
    row, token = issue_passport(
        sf,
        agent_name="test_agent_1",
        agent_class="external_mcp",
        owner_email="test@example.com",
        scope_clusters=clusters or ["*"],
        scope_intents=intents or ["*"],
        scope_skills=skills or ["*"],
        ttl_hours=ttl_hours,
    )
    return row.passport_id, token


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


def test_issue_passport_returns_bearer_once(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'passport_api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app) as client:
        created = client.post(
            "/api/internal/passports",
            json={
                "agent_name": "test_agent_1",
                "agent_class": "external_mcp",
                "owner_email": "test@example.com",
                "scope_clusters": ["engineering_code"],
                "scope_intents": ["read"],
                "scope_skills": ["*"],
                "ttl_hours": 1,
            },
        )
        assert created.status_code == 200
        body = created.json()
        passport_id = body["passport_id"]
        assert body["bearer_token"].startswith("axiom_pt_")

        listed = client.get("/api/internal/passports").json()["passports"][0]
        detail = client.get(f"/api/internal/passports/{passport_id}").json()
        assert "bearer_token" not in listed
        assert "bearer_token" not in detail


def test_verify_passport_valid_token(passport_db: sessionmaker[Session]) -> None:
    passport_id, token = _issue(passport_db)
    row = verify_passport(passport_db, token)
    assert row.passport_id == passport_id


def test_verify_passport_rejects_revoked(passport_db: sessionmaker[Session]) -> None:
    passport_id, token = _issue(passport_db)
    assert verify_passport(passport_db, token).passport_id == passport_id
    revoke_passport(passport_db, passport_id, "test revoke")
    with pytest.raises(PassportError, match="revoked"):
        verify_passport(passport_db, token)


def test_verify_passport_rejects_kill_switched(passport_db: sessionmaker[Session]) -> None:
    passport_id, token = _issue(passport_db)
    toggle_kill_switch(passport_db, passport_id, True)
    with pytest.raises(PassportError, match="kill switch"):
        verify_passport(passport_db, token)


def test_verify_passport_rejects_expired(passport_db: sessionmaker[Session]) -> None:
    passport_id, token = _issue(passport_db)
    with passport_db() as session:
        row = session.get(AgentPassport, passport_id)
        assert row is not None
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        row.issuer_signature = _demo_signature(row)
        session.add(row)
        session.commit()
    with pytest.raises(PassportError, match="expired"):
        verify_passport(passport_db, token)


def test_check_scope_wildcard_allows_all(passport_db: sessionmaker[Session]) -> None:
    _passport_id, token = _issue(passport_db, clusters=["*"], intents=["*"], skills=["*"])
    row = verify_passport(passport_db, token)
    assert check_scope(row, "invoke_skill", "billing_payments", "skill_1")


def test_check_scope_cluster_match(passport_db: sessionmaker[Session]) -> None:
    _passport_id, token = _issue(passport_db, clusters=["engineering_code"])
    row = verify_passport(passport_db, token)
    assert check_scope(row, "read", "engineering_code")
    assert not check_scope(row, "read", "billing_payments")


def test_check_scope_intent_match(passport_db: sessionmaker[Session]) -> None:
    _passport_id, token = _issue(passport_db, intents=["read"])
    row = verify_passport(passport_db, token)
    assert check_scope(row, "read", "engineering_code")
    assert not check_scope(row, "write", "engineering_code")


def test_run_skill_with_passport_outside_skill_scope_denied(
    passport_service: AxiomMCPService,
    passport_db: sessionmaker[Session],
) -> None:
    skill_id = _register_skill(passport_db)
    _passport_id, token = _issue(
        passport_db,
        clusters=["*"],
        intents=["invoke_skill"],
        skills=["different_skill"],
    )
    with pytest.raises(ToolError, match="passport scope denied"):
        passport_service.run_skill(skill_id=skill_id, input_payload={"note": "x"}, passport_token=token)

    with passport_db() as session:
        assert session.query(SkillRun).count() == 0
        assert session.query(Receipt).count() == 0


def test_record_action_uses_default_passport_when_none_provided(
    passport_service: AxiomMCPService,
    passport_db: sessionmaker[Session],
) -> None:
    out = passport_service.record_action(
        agent_name="agent_a",
        intent="read",
        target_entity_id="eng_1",
        proposed_action="read engineering note",
        idempotency_key=None,
    )
    assert out["passport_id"] == SYSTEM_PASSPORT_ID
    with passport_db() as session:
        receipt = session.get(Receipt, out["receipt_id"])
    assert receipt is not None
    assert receipt.passport_id == SYSTEM_PASSPORT_ID


def test_passport_endpoint_revocation_invalidates_immediately(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'passport_revoke.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app) as client:
        created = client.post(
            "/api/internal/passports",
            json={
                "agent_name": "test_agent_1",
                "agent_class": "external_mcp",
                "owner_email": "test@example.com",
                "scope_clusters": ["*"],
                "scope_intents": ["*"],
                "scope_skills": ["*"],
                "ttl_hours": 1,
            },
        ).json()
        token = created["bearer_token"]
        assert verify_passport(sf, token).passport_id == created["passport_id"]
        assert client.delete(f"/api/internal/passports/{created['passport_id']}").status_code == 200
        with pytest.raises(PassportError, match="revoked"):
            verify_passport(sf, token)


def test_receipt_carries_passport_id(
    passport_service: AxiomMCPService,
    passport_db: sessionmaker[Session],
) -> None:
    passport_id, token = _issue(passport_db, clusters=["engineering_code"], intents=["read"])
    out = passport_service.record_action(
        agent_name="agent_a",
        intent="read",
        target_entity_id="eng_1",
        proposed_action="read engineering note",
        idempotency_key=None,
        passport_token=token,
    )
    assert out["passport_id"] == passport_id
    with passport_db() as session:
        receipt = session.get(Receipt, out["receipt_id"])
    assert receipt is not None
    assert receipt.passport_id == passport_id


def test_passport_smoke_revoke_and_kill_switch(
    passport_service: AxiomMCPService,
    passport_db: sessionmaker[Session],
) -> None:
    passport_id, token = _issue(passport_db, clusters=["engineering_code"], intents=["read"])
    allowed = passport_service.record_action(
        agent_name="test_agent_1",
        intent="read",
        target_entity_id="eng_1",
        proposed_action="read engineering note",
        idempotency_key=None,
        passport_token=token,
    )
    assert allowed["decision"] == "allow"
    assert allowed["passport_id"] == passport_id

    revoke_passport(passport_db, passport_id, "smoke revoke")
    with pytest.raises(ToolError, match="revoked"):
        passport_service.record_action(
            agent_name="test_agent_1",
            intent="read",
            target_entity_id="eng_1",
            proposed_action="read engineering note",
            idempotency_key=None,
            passport_token=token,
        )

    kill_id, kill_token = _issue(passport_db, clusters=["engineering_code"], intents=["read"])
    toggle_kill_switch(passport_db, kill_id, True)
    with pytest.raises(ToolError, match="kill switch"):
        passport_service.record_action(
            agent_name="test_agent_1",
            intent="read",
            target_entity_id="eng_1",
            proposed_action="read engineering note",
            idempotency_key=None,
            passport_token=kill_token,
        )
    toggle_kill_switch(passport_db, kill_id, False)
    after_toggle = passport_service.record_action(
        agent_name="test_agent_1",
        intent="read",
        target_entity_id="eng_2",
        proposed_action="read second engineering note",
        idempotency_key=None,
        passport_token=kill_token,
    )
    assert after_toggle["decision"] == "allow"
