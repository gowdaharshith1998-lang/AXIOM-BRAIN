from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import responses
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import PolicyDecision
from axiom.schema.models import Base, ConnectorStateRow, Receipt


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'slack.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="slack_state_1",
                connector_id="slack",
                vendor="slack",
                access_token="xoxb-bot",
                refresh_token="xoxp-user",
                account_id="T1",
                account_label="Axiom HQ",
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


def _slack_signature(secret: str, body: bytes, timestamp: int) -> str:
    basestring = b"v0:" + str(timestamp).encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_slack_oauth_authorize_url_includes_bot_and_user_scopes() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.slack.oauth import SlackOAuth

    flow = SlackOAuth(
        ConnectorConfig(
            id="slack",
            vendor="slack",
            oauth_client_id="client",
            redirect_uri="https://axiom.local/slack/callback",
        )
    )

    url = flow.authorize_url("csrf")

    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "scope=channels%3Ahistory%2Cchannels%3Aread%2Cchat%3Awrite" in url
    assert "user_scope=search%3Aread" in url
    assert "state=csrf" in url


@responses.activate
def test_slack_oauth_exchange_code_stores_bot_and_user_tokens() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.slack.oauth import SlackOAuth

    responses.post(
        "https://slack.com/api/oauth.v2.access",
        json={
            "ok": True,
            "access_token": "xoxb-bot",
            "authed_user": {"access_token": "xoxp-user"},
            "team": {"id": "T1", "name": "Axiom HQ"},
        },
    )

    state = SlackOAuth(
        ConnectorConfig(
            id="slack",
            vendor="slack",
            oauth_client_id="client",
            oauth_client_secret="secret",
            redirect_uri="https://axiom.local/slack/callback",
        )
    ).exchange_code("code")

    assert state.connector_id == "slack"
    assert state.access_token == "xoxb-bot"
    assert state.refresh_token == "xoxp-user"
    assert state.account_label == "Axiom HQ"


def test_slack_webhook_url_verification_challenge_responds() -> None:
    from axiom.connectors.slack.webhook import SlackWebhookHandler

    body = b'{"type":"url_verification","challenge":"abc123"}'
    request = SimpleNamespace(body=body, headers={})

    assert SlackWebhookHandler("secret").challenge_response(request) == "abc123"


def test_slack_webhook_hmac_verify_with_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    from axiom.connectors.slack import webhook
    from axiom.connectors.slack.webhook import SlackWebhookHandler

    monkeypatch.setattr(webhook, "_now", lambda: 1_700_000_000)
    body = b'{"event":{"type":"message"}}'
    signature = _slack_signature("secret", body, 1_700_000_000)
    request = SimpleNamespace(
        body=body,
        headers={
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": "1700000000",
        },
    )

    assert SlackWebhookHandler("secret").verify(request) is True


def test_slack_webhook_rejects_replay_attack_old_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.connectors.slack import webhook
    from axiom.connectors.slack.webhook import SlackWebhookHandler

    monkeypatch.setattr(webhook, "_now", lambda: 1_700_000_700)
    body = b'{"event":{"type":"message"}}'
    request = SimpleNamespace(
        body=body,
        headers={
            "X-Slack-Signature": _slack_signature("secret", body, 1_700_000_000),
            "X-Slack-Request-Timestamp": "1700000000",
        },
    )

    assert SlackWebhookHandler("secret").verify(request) is False


def test_slack_webhook_parse_message_event() -> None:
    from axiom.connectors.slack.webhook import SlackWebhookHandler

    body = json.dumps(
        {"event": {"type": "message", "channel": "C1", "ts": "123.456", "text": "hello"}}
    ).encode()
    request = SimpleNamespace(body=body, headers={})

    event = SlackWebhookHandler("secret").parse(request)[0]

    assert event.vendor == "slack"
    assert event.event_type == "message"
    assert event.external_id == "C1:123.456"


def test_slack_webhook_parse_reaction_event() -> None:
    from axiom.connectors.slack.webhook import SlackWebhookHandler

    body = json.dumps(
        {"event": {"type": "reaction_added", "item": {"channel": "C1", "ts": "123.456"}}}
    ).encode()
    request = SimpleNamespace(body=body, headers={})

    event = SlackWebhookHandler("secret").parse(request)[0]

    assert event.event_type == "reaction_added"
    assert event.external_id == "C1:123.456:reaction_added"


@responses.activate
def test_slack_ingest_fetches_channels_and_users() -> None:
    from axiom.connectors.slack.ingest import fetch_channels, fetch_users

    responses.get(
        "https://slack.com/api/conversations.list",
        json={"ok": True, "channels": [{"id": "C1", "name": "eng-platform"}]},
    )
    responses.get(
        "https://slack.com/api/users.list",
        json={"ok": True, "members": [{"id": "U1", "name": "ada"}]},
    )
    state = SimpleNamespace(access_token="xoxb-bot")

    assert fetch_channels(state)[0]["name"] == "eng-platform"
    assert fetch_users(state)[0]["id"] == "U1"


def test_slack_ingest_normalizes_message_to_entity() -> None:
    from axiom.connectors.slack.ingest import normalize_message

    entity = normalize_message("C1", {"ts": "123.456", "text": "hello"})

    assert entity["type"] == "message"
    assert entity["cluster_id"] == "comms"
    assert entity["source_id"] == "slack:message:C1:123.456"


def test_slack_ingest_creates_thread_parent_child_edges() -> None:
    from axiom.connectors.slack.ingest import thread_parent_child_edge

    assert thread_parent_child_edge("message:parent", "message:reply") == {
        "source_nick": "message:parent",
        "target_nick": "message:reply",
        "relationship": "thread_has_reply",
        "data": {},
    }


def test_slack_writer_propose_postmessage_returns_action_request() -> None:
    from axiom.connectors.slack.writer import SlackWriter

    action = SlackWriter().propose_action(
        "post_message",
        {"channel": "C1", "text": "ship it"},
    )

    assert action.intent == "post_message"
    assert action.proposed_action == "slack.post_message"
    assert action.payload["channel"] == "C1"


def test_slack_writer_execute_blocks_on_policy_deny(tmp_path: Path) -> None:
    from axiom.connectors.slack.writer import SlackWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    writer = SlackWriter(
        state=SimpleNamespace(access_token="xoxb-bot"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="slack.policy.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="slack.policy.deny"):
        writer.execute(writer.propose_action("post_message", {"channel": "C1", "text": "x"}))


@responses.activate
def test_slack_writer_execute_calls_chat_postmessage(tmp_path: Path) -> None:
    from axiom.connectors.slack.writer import SlackWriter

    responses.post("https://slack.com/api/chat.postMessage", json={"ok": True, "ts": "123.456"})
    writer = SlackWriter(
        state=SimpleNamespace(access_token="xoxb-bot"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="slack.policy.allow")
        ),
    )

    result = writer.execute(
        writer.propose_action("post_message", {"channel": "C1", "text": "x"})
    )

    assert result["ok"] is True
    assert responses.calls[0].request.headers["Authorization"] == "Bearer xoxb-bot"
    assert responses.calls[0].request.url == "https://slack.com/api/chat.postMessage"


@responses.activate
def test_slack_writer_execute_chains_receipt(tmp_path: Path) -> None:
    from axiom.connectors.slack.writer import SlackWriter

    sf = _sf(tmp_path)
    responses.post("https://slack.com/api/reactions.add", json={"ok": True})
    writer = SlackWriter(
        state=SimpleNamespace(access_token="xoxb-bot"),
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="slack.policy.allow")
        ),
    )

    writer.execute(
        writer.propose_action(
            "reaction_add",
            {"channel": "C1", "timestamp": "123.456", "name": "white_check_mark"},
        )
    )

    with sf() as session:
        receipt = session.execute(
            select(Receipt).where(Receipt.policy_id == "slack.policy.allow")
        ).scalar_one()
        assert receipt.decision == "allow"
