from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import responses
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import ActionRequest, PolicyDecision, RealPolicyEvaluator, load_policies_from_dir
from axiom.schema.models import Base, ConnectorStateRow


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'gmail.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="gmail_state_1",
                connector_id="gmail",
                vendor="gmail",
                access_token="ya29.access",
                refresh_token="1//refresh",
                account_id="founder@axiom.local",
                account_label="founder@axiom.local",
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


def test_gmail_oauth_authorize_url_includes_scopes() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.gmail.oauth import GmailOAuth

    flow = GmailOAuth(
        ConnectorConfig(
            id="gmail",
            vendor="gmail",
            oauth_client_id="client",
            redirect_uri="https://axiom.local/gmail/callback",
        )
    )

    url = flow.authorize_url("csrf")

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "gmail.readonly" in url
    assert "gmail.send" in url
    assert "access_type=offline" in url
    assert "state=csrf" in url


@responses.activate
def test_gmail_oauth_exchange_code_stores_token_and_refresh() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.gmail.oauth import GmailOAuth

    responses.post(
        "https://oauth2.googleapis.com/token",
        json={"access_token": "ya29.access", "refresh_token": "1//refresh", "expires_in": 3600},
    )
    state = GmailOAuth(
        ConnectorConfig(
            id="gmail",
            vendor="gmail",
            oauth_client_id="client",
            oauth_client_secret="secret",
            redirect_uri="https://axiom.local/gmail/callback",
        )
    ).exchange_code("code")

    assert state.connector_id == "gmail"
    assert state.access_token == "ya29.access"
    assert state.refresh_token == "1//refresh"
    assert state.token_expires_at is not None


@responses.activate
def test_gmail_oauth_refresh_token_when_expired() -> None:
    from axiom.connectors.base import ConnectorConfig, ConnectorState
    from axiom.connectors.gmail.oauth import GmailOAuth

    responses.post(
        "https://oauth2.googleapis.com/token",
        json={"access_token": "ya29.new", "expires_in": 3600},
    )
    expired = ConnectorState(
        id="state_1",
        connector_id="gmail",
        access_token="old",
        refresh_token="1//refresh",
        token_expires_at=datetime.utcnow() - timedelta(seconds=1),
    )

    refreshed = GmailOAuth(
        ConnectorConfig(
            id="gmail",
            vendor="gmail",
            oauth_client_id="client",
            oauth_client_secret="secret",
        )
    ).refresh(expired)

    assert refreshed.access_token == "ya29.new"
    assert refreshed.refresh_token == "1//refresh"


def test_gmail_webhook_verifies_pubsub_jwt() -> None:
    from axiom.connectors.gmail.webhook import GmailWebhookHandler

    request = SimpleNamespace(headers={"Authorization": "Bearer jwt.token"}, body=b"{}")

    assert GmailWebhookHandler(verifier=lambda token: token == "jwt.token").verify(request)


def test_gmail_default_webhook_verifier_fails_closed_without_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.connectors.gmail.webhook import _default_verify_google_jwt

    monkeypatch.delenv("AXIOM_GMAIL_PUBSUB_AUDIENCE", raising=False)

    assert _default_verify_google_jwt("jwt.token") is False


@responses.activate
def test_gmail_webhook_fetches_history_since_historyid() -> None:
    from axiom.connectors.gmail.webhook import GmailWebhookHandler

    responses.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/history",
        json={"history": [{"id": "h2", "messages": [{"id": "m1"}]}]},
    )
    handler = GmailWebhookHandler(verifier=lambda _token: True)
    envelope = {
        "message": {
            "data": base64.b64encode(
                json.dumps({"emailAddress": "founder@axiom.local", "historyId": "123"}).encode()
            ).decode()
        }
    }
    request = SimpleNamespace(
        headers={"Authorization": "Bearer jwt"},
        body=json.dumps(envelope).encode(),
    )

    event = handler.parse(request)[0]
    history = handler.fetch_history(SimpleNamespace(access_token="ya29.access"), event)

    assert event.external_id == "founder@axiom.local:123"
    assert history[0]["id"] == "h2"


def test_gmail_ingest_normalizes_thread_and_messages() -> None:
    from axiom.connectors.gmail.ingest import (
        normalize_message,
        normalize_thread,
        thread_to_message_edge,
    )

    thread = normalize_thread({"id": "thread_1", "historyId": "10"})
    message = normalize_message(
        {
            "id": "msg_1",
            "threadId": "thread_1",
            "payload": {"headers": [{"name": "From", "value": "ada@example.com"}]},
        }
    )

    assert thread["type"] == "email_thread"
    assert message["type"] == "email"
    assert (
        thread_to_message_edge(thread["nick"], message["nick"])["relationship"]
        == "thread_has_message"
    )


def test_gmail_writer_propose_send_returns_action_request() -> None:
    from axiom.connectors.gmail.writer import GmailWriter

    action = GmailWriter().propose_action("send_email", {"to": "ada@example.com", "body": "Hi"})

    assert action.intent == "send_email"
    assert action.proposed_action == "gmail.send_email"
    assert action.payload["to"] == "ada@example.com"


def test_gmail_writer_execute_blocks_on_policy_deny(tmp_path: Path) -> None:
    from axiom.connectors.gmail.writer import GmailWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    writer = GmailWriter(
        state=SimpleNamespace(access_token="ya29.access"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="gmail.policy.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="gmail.policy.deny"):
        writer.execute(writer.propose_action("send_email", {"raw": "abc"}))


@responses.activate
def test_gmail_writer_execute_calls_gmail_send_api(tmp_path: Path) -> None:
    from axiom.connectors.gmail.writer import GmailWriter

    responses.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        json={"id": "msg_1"},
    )
    writer = GmailWriter(
        state=SimpleNamespace(access_token="ya29.access"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="gmail.policy.allow")
        ),
    )

    result = writer.execute(writer.propose_action("send_email", {"raw": "abc"}))

    assert result["id"] == "msg_1"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer ya29.access"


def test_connector_predicate_is_external_true_for_outside_gmail() -> None:
    from axiom.policy.predicates import connector_is_external

    entity = SimpleNamespace(
        source_id="gmail:message:msg_1",
        data={"from": "ada@example.com", "workspace_domain": "axiom.local"},
    )

    assert connector_is_external(None, None, entity, None, entity) is True


def test_connector_predicate_vendor_returns_correct_vendor() -> None:
    from axiom.policy.predicates import connector_vendor

    assert (
        connector_vendor(None, None, SimpleNamespace(source_id="slack:message:C1:1"), None)
        == "slack"
    )
    assert (
        connector_vendor(None, None, SimpleNamespace(source_id="synthetic:demo"), None)
        == "synthetic"
    )


def test_policy_external_email_forward_pauses_for_security_review() -> None:
    rules = load_policies_from_dir("policies/starter-pack")
    evaluator = RealPolicyEvaluator(rules, None)
    action = ActionRequest(
        agent_name="connector:gmail",
        intent="forward",
        target_entity_id="email_1",
        proposed_action="gmail.forward",
        idempotency_key=None,
        payload={},
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
