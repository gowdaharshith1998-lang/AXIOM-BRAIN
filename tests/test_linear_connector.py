from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import responses
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import PolicyDecision
from axiom.schema.models import Base, ConnectorStateRow, Receipt


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'linear.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="linear_state_1",
                connector_id="linear",
                vendor="linear",
                access_token="lin_token",
                account_id="workspace_1",
                account_label="Linear Workspace",
                installed_by="founder",
                status="connected",
            )
        )
        session.commit()
    return sf


class _PolicyEvaluator:
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision

    def evaluate(self, action, passport, entity):  # type: ignore[no-untyped-def]
        return self.decision


def test_linear_oauth_authorize_url_correct_endpoint() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.linear.oauth import LinearOAuth

    flow = LinearOAuth(
        ConnectorConfig(
            id="linear",
            vendor="linear",
            oauth_client_id="client",
            redirect_uri="https://axiom.local/linear/callback",
        )
    )

    url = flow.authorize_url("csrf")

    assert url.startswith("https://linear.app/oauth/authorize?")
    assert "scope=read+write+issues%3Acreate" in url
    assert "state=csrf" in url


@responses.activate
def test_linear_oauth_exchange_code_stores_token() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.linear.oauth import LinearOAuth

    responses.post("https://api.linear.app/oauth/token", json={"access_token": "lin_token"})
    state = LinearOAuth(
        ConnectorConfig(
            id="linear",
            vendor="linear",
            oauth_client_id="client",
            oauth_client_secret="secret",
            redirect_uri="https://axiom.local/linear/callback",
        )
    ).exchange_code("code")

    assert state.connector_id == "linear"
    assert state.access_token == "lin_token"


def test_linear_webhook_hmac_verify() -> None:
    from axiom.connectors.linear.webhook import LinearWebhookHandler

    body = b'{"type":"Issue"}'
    digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    request = SimpleNamespace(body=body, headers={"linear-signature": digest})

    assert LinearWebhookHandler("secret").verify(request) is True


def test_linear_webhook_parse_issue_update_event() -> None:
    from axiom.connectors.linear.webhook import LinearWebhookHandler

    body = json.dumps({"type": "Issue", "action": "update", "data": {"id": "issue_1"}}).encode()
    request = SimpleNamespace(body=body, headers={"linear-delivery": "delivery_1"})

    event = LinearWebhookHandler("secret").parse(request)[0]

    assert event.vendor == "linear"
    assert event.event_type == "Issue.update"
    assert event.external_id == "delivery_1"


@responses.activate
def test_linear_ingest_fetches_teams_and_issues() -> None:
    from axiom.connectors.linear.ingest import fetch_issues_for_team, fetch_teams

    responses.post(
        "https://api.linear.app/graphql",
        json={
            "data": {
                "teams": {"nodes": [{"id": "team_1", "name": "Platform"}]},
                "issues": {"nodes": [{"id": "issue_1", "title": "Bug"}]},
            }
        },
    )
    state = SimpleNamespace(access_token="lin_token")

    assert fetch_teams(state)[0]["name"] == "Platform"
    assert fetch_issues_for_team(state, "team_1")[0]["id"] == "issue_1"


def test_linear_ingest_normalizes_issue_to_ticket() -> None:
    from axiom.connectors.linear.ingest import normalize_issue

    entity = normalize_issue({"id": "issue_1", "title": "Bug"})

    assert entity["type"] == "ticket"
    assert entity["cluster_id"] == "engineering_code"
    assert entity["source_id"] == "linear:issue:issue_1"


def test_linear_ingest_normalizes_project_to_project_entity() -> None:
    from axiom.connectors.linear.ingest import normalize_project

    entity = normalize_project({"id": "project_1", "name": "Launch"})

    assert entity["type"] == "project"
    assert entity["source_id"] == "linear:project:project_1"


def test_linear_ingest_creates_team_to_issue_edges() -> None:
    from axiom.connectors.linear.ingest import team_to_issue_edge

    assert team_to_issue_edge("team:1", "issue:1") == {
        "source_nick": "team:1",
        "target_nick": "issue:1",
        "relationship": "team_has_issue",
        "data": {},
    }


def test_linear_writer_propose_comment_returns_action_request() -> None:
    from axiom.connectors.linear.writer import LinearWriter

    action = LinearWriter().propose_action("comment", {"issue_id": "issue_1", "body": "LGTM"})

    assert action.intent == "comment"
    assert action.proposed_action == "linear.comment"
    assert action.payload["issue_id"] == "issue_1"


def test_linear_writer_execute_blocks_on_policy_deny(tmp_path: Path) -> None:
    from axiom.connectors.linear.writer import LinearWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    writer = LinearWriter(
        state=SimpleNamespace(access_token="lin_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="linear.policy.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="linear.policy.deny"):
        writer.execute(writer.propose_action("comment", {"issue_id": "issue_1", "body": "x"}))


@responses.activate
def test_linear_writer_execute_uses_graphql_mutation(tmp_path: Path) -> None:
    from axiom.connectors.linear.writer import LinearWriter

    responses.post(
        "https://api.linear.app/graphql",
        json={"data": {"commentCreate": {"success": True}}},
    )
    writer = LinearWriter(
        state=SimpleNamespace(access_token="lin_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="linear.policy.allow")
        ),
    )

    result = writer.execute(
        writer.propose_action("comment", {"issue_id": "issue_1", "body": "x"})
    )

    assert result["data"]["commentCreate"]["success"] is True
    assert responses.calls[0].request.headers["Authorization"] == "Bearer lin_token"
    assert "commentCreate" in str(responses.calls[0].request.body)


@responses.activate
def test_linear_writer_execute_chains_receipt(tmp_path: Path) -> None:
    from axiom.connectors.linear.writer import LinearWriter

    sf = _sf(tmp_path)
    responses.post(
        "https://api.linear.app/graphql",
        json={"data": {"issueUpdate": {"success": True}}},
    )
    writer = LinearWriter(
        state=SimpleNamespace(access_token="lin_token"),
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="linear.policy.allow")
        ),
    )

    writer.execute(
        writer.propose_action("state_change", {"issue_id": "issue_1", "state_id": "done"})
    )

    with sf() as session:
        receipt = session.execute(
            select(Receipt).where(Receipt.policy_id == "linear.policy.allow")
        ).scalar_one()
        assert receipt.decision == "allow"


@responses.activate
def test_linear_callback_endpoint_persists_connector_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.studio.server import create_app

    monkeypatch.setenv("AXIOM_CONNECTOR_LINEAR_ENABLED", "1")
    monkeypatch.setenv("AXIOM_LINEAR_CLIENT_ID", "client")
    monkeypatch.setenv("AXIOM_LINEAR_CLIENT_SECRET", "secret")
    responses.post("https://api.linear.app/oauth/token", json={"access_token": "lin_token"})

    db_url = f"sqlite:///{tmp_path / 'api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/connectors/linear/callback?code=abc&state=csrf")

    assert response.status_code == 200
    with Session(engine) as session:
        state = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
        ).scalar_one()
        assert state.access_token == "lin_token"
        assert state.account_label == "Linear Workspace"
