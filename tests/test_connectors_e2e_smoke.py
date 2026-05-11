from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import responses
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import ActionRequest, RealPolicyEvaluator, load_policies_from_dir
from axiom.schema.models import Base, ConnectorEventRow, ConnectorStateRow, Entity, Receipt


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    from axiom.studio.server import create_app

    db_url = f"sqlite:///{tmp_path / 'connectors_e2e.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_ID", "github_client")
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_SECRET", "github_secret")
    monkeypatch.setenv("AXIOM_GITHUB_WEBHOOK_SECRET", "github_webhook")
    monkeypatch.setenv("AXIOM_LINEAR_CLIENT_ID", "linear_client")
    monkeypatch.setenv("AXIOM_LINEAR_CLIENT_SECRET", "linear_secret")
    monkeypatch.setenv("AXIOM_SLACK_SIGNING_SECRET", "slack_secret")
    app = create_app(db_url=db_url, enable_organizer=False)
    return app, db_url


def _session_factory(db_url: str) -> sessionmaker[Session]:
    engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _github_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _slack_signature(secret: str, body: bytes, timestamp: int) -> str:
    basestring = b"v0:" + str(timestamp).encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _pii_rule_evaluator() -> RealPolicyEvaluator:
    rules = [
        rule
        for rule in load_policies_from_dir("policies/starter-pack")
        if rule.rule_id == "starter.data.pii_in_payload"
    ]
    return RealPolicyEvaluator(rules, None)


@responses.activate
def test_e2e_github_install_to_first_entity_under_30s(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_GITHUB_ENABLED", "1")
    app, db_url = _make_app(tmp_path, monkeypatch)
    responses.post(
        "https://github.com/login/oauth/access_token",
        json={"access_token": "gho_e2e"},
    )
    responses.get(
        "https://api.github.com/user/repos",
        json=[{"id": 1, "full_name": "octo/repo", "name": "repo"}],
        headers={"Link": ""},
    )
    responses.get(
        "https://api.github.com/repos/octo/repo/issues",
        json=[{"id": 2, "number": 7, "title": "Bug"}],
        headers={"Link": ""},
    )
    responses.get(
        "https://api.github.com/repos/octo/repo/pulls",
        json=[{"id": 3, "number": 8, "title": "Feature"}],
        headers={"Link": ""},
    )

    started = time.perf_counter()
    with TestClient(app) as client:
        callback = client.get("/api/internal/connectors/github/callback?code=abc&state=csrf")
        sync = client.post("/api/internal/connectors/github/sync")
    elapsed = time.perf_counter() - started

    assert callback.status_code == 200
    assert sync.status_code == 200
    assert sync.json()["ingested"] >= 1
    assert elapsed < 30
    with Session(create_engine(db_url, future=True)) as session:
        entity = session.execute(
            select(Entity).where(Entity.source_id.like("github:%")).limit(1)
        ).scalar_one()
        assert entity.type in {"repo", "ticket", "pull_request"}


def test_e2e_github_webhook_to_brain_event_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_GITHUB_ENABLED", "1")
    app, db_url = _make_app(tmp_path, monkeypatch)
    body = json.dumps(
        {
            "action": "opened",
            "issue": {"id": 12, "number": 7, "title": "Bug"},
            "repository": {"full_name": "octo/repo"},
        }
    ).encode()

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/connectors/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "delivery_1",
                "X-Hub-Signature-256": _github_signature("github_webhook", body),
            },
        )
        with client.websocket_connect("/ws/brain?since=0") as ws:
            envelope = ws.receive_json()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "events": 1}
    assert envelope["type"] == "connector_event_received"
    assert envelope["payload"] == {"vendor": "github", "event_type": "issues.opened"}
    with Session(create_engine(db_url, future=True)) as session:
        row = session.execute(select(ConnectorEventRow)).scalar_one()
        assert row.signature_ok is True


def test_e2e_github_writer_blocked_by_starter_pack_pii_rule(tmp_path: Path) -> None:
    from axiom.connectors.github.writer import GitHubWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    db_url = f"sqlite:///{tmp_path / 'github_writer.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    writer = GitHubWriter(
        state=SimpleNamespace(access_token="gho_e2e"),
        session_factory=sf,
        policy_evaluator=_pii_rule_evaluator(),
    )

    with pytest.raises(ConnectorWriteBlocked, match="starter.data.pii_in_payload"):
        writer.execute(
            writer.propose_action(
                "comment",
                {
                    "issue_url": "https://github.com/octo/repo/issues/7",
                    "body": "Customer email ada@example.com needs redaction.",
                },
            )
        )

    with sf() as session:
        receipt = session.execute(
            select(Receipt).where(Receipt.policy_id == "starter.data.pii_in_payload")
        ).scalar_one()
        assert receipt.agent_name == "connector:github"
        assert receipt.decision == "correct"


@responses.activate
def test_e2e_linear_install_through_first_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_LINEAR_ENABLED", "1")
    app, db_url = _make_app(tmp_path, monkeypatch)
    responses.post("https://api.linear.app/oauth/token", json={"access_token": "lin_e2e"})
    responses.post(
        "https://api.linear.app/graphql",
        json={"data": {"teams": {"nodes": [{"id": "team_1", "name": "Platform"}]}}},
    )
    responses.post(
        "https://api.linear.app/graphql",
        json={"data": {"projects": {"nodes": [{"id": "project_1", "name": "Launch"}]}}},
    )
    responses.post(
        "https://api.linear.app/graphql",
        json={
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue_1",
                            "title": "Bug",
                            "identifier": "AX-1",
                            "team": {"id": "team_1", "name": "Platform"},
                            "project": {"id": "project_1", "name": "Launch"},
                        }
                    ]
                }
            }
        },
    )

    with TestClient(app) as client:
        callback = client.get("/api/internal/connectors/linear/callback?code=abc&state=csrf")
        sync = client.post("/api/internal/connectors/linear/sync")

    assert callback.status_code == 200
    assert sync.status_code == 200
    assert sync.json()["ingested"] >= 1
    with Session(create_engine(db_url, future=True)) as session:
        state = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
        ).scalar_one()
        assert state.status == "connected"
        assert session.execute(
            select(Entity).where(Entity.source_id.like("linear:%")).limit(1)
        ).scalar_one()


def test_e2e_slack_webhook_signature_verify_then_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_SLACK_ENABLED", "1")
    app, db_url = _make_app(tmp_path, monkeypatch)
    body = json.dumps(
        {"event": {"type": "message", "channel": "C1", "ts": "123.456", "text": "hello"}}
    ).encode()
    timestamp = int(time.time())

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/connectors/slack/webhook",
            content=body,
            headers={
                "X-Slack-Signature": _slack_signature("slack_secret", body, timestamp),
                "X-Slack-Request-Timestamp": str(timestamp),
            },
        )
        events = client.get("/api/internal/connectors/slack/events")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "events": 1}
    assert events.json()["events"][0]["event_type"] == "message"
    with Session(create_engine(db_url, future=True)) as session:
        row = session.execute(select(ConnectorEventRow)).scalar_one()
        assert row.vendor == "slack"
        assert row.signature_ok is True


def test_e2e_gmail_external_email_pauses_for_approval() -> None:
    rules = load_policies_from_dir("policies/starter-pack")
    evaluator = RealPolicyEvaluator(rules, None)
    envelope = {"emailAddress": "founder@axiom.local", "historyId": "123"}
    action = ActionRequest(
        agent_name="connector:gmail",
        intent="forward",
        target_entity_id="email_1",
        proposed_action="gmail.forward",
        idempotency_key=None,
        payload={
            "pubsub_data": base64.b64encode(json.dumps(envelope).encode()).decode(),
        },
    )
    entity = SimpleNamespace(
        id="email_1",
        source_id="gmail:message:msg_1",
        cluster_id="comms",
        data={"from": "ada@example.com", "workspace_domain": "axiom.local"},
    )
    passport = SimpleNamespace(
        scope_clusters=["*"],
        scope_intents=["*"],
        scope_skills=["*"],
        revoked_at=None,
        expires_at=None,
    )

    decision = evaluator.evaluate(action, passport, entity)

    assert decision.mode == "pause"
    assert decision.policy_id == "starter.data.external_email_to_internal"
    assert decision.approval_required_role == "security"
