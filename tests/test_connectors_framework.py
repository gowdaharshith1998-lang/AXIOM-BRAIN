from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.receipts import verify_receipt_chain
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.policy import PolicyDecision
from axiom.schema.models import Base, ConnectorEventRow, ConnectorStateRow, Entity, Receipt


class _Request:
    def __init__(self, body: bytes, signature: str) -> None:
        self.body = body
        self.headers = {"x-test-signature": signature}


class _PolicyEvaluator:
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision

    def evaluate(self, action: Any, passport: Any, entity: Any) -> PolicyDecision:
        return self.decision


def _session_factory(tmp_path) -> sessionmaker[Session]:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'connectors.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def test_base_oauth_flow_state_param_is_csrf_safe() -> None:
    from axiom.connectors.base import ConnectorConfig, OAuthFlow

    class TestOAuth(OAuthFlow):
        authorize_endpoint = "https://vendor.example/oauth/authorize"

        def exchange_code(self, code: str):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def refresh(self, state):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    flow = TestOAuth(
        ConnectorConfig(
            id="cfg_1",
            vendor="test",
            oauth_client_id="client_1",
            oauth_client_secret="secret_1",
            redirect_uri="https://axiom.example/callback",
            scopes=["repo", "read:org"],
            webhook_secret="whsec",
            workspace_id="workspace_1",
        )
    )

    url = flow.authorize_url("csrf-state-123")

    assert "state=csrf-state-123" in url
    assert "client_id=client_1" in url
    assert "redirect_uri=https%3A%2F%2Faxiom.example%2Fcallback" in url
    assert "scope=repo+read%3Aorg" in url


def test_base_webhook_verify_rejects_wrong_signature() -> None:
    from axiom.connectors.base import HmacSha256WebhookHandler

    handler = HmacSha256WebhookHandler("test", "secret", header_name="x-test-signature")

    assert handler.verify(_Request(b'{"ok": true}', "sha256=bad")) is False


def test_base_webhook_verify_accepts_valid_signature() -> None:
    from axiom.connectors.base import HmacSha256WebhookHandler

    body = b'{"ok": true}'
    digest = hmac.new(b"secret", body, "sha256").hexdigest()
    handler = HmacSha256WebhookHandler("test", "secret", header_name="x-test-signature")

    assert handler.verify(_Request(body, f"sha256={digest}")) is True


def test_registry_register_and_get_roundtrip() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    config = ConnectorConfig(id="cfg_1", vendor="github")

    registry.register_connector("github", lambda: SimpleNamespace(config=config))

    assert registry.get_connector("github").config.vendor == "github"


def test_registry_list_installed_returns_real_rows(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from axiom.connectors.registry import list_installed

    sf = _session_factory(tmp_path)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="state_1",
                connector_id="cfg_1",
                vendor="github",
                access_token="token",
                account_id="acct_1",
                account_label="ACME Repo",
                installed_by="founder",
                status="connected",
            )
        )
        session.commit()

    rows = list_installed(sf)

    assert rows == [
        {
            "id": "state_1",
            "connector_id": "cfg_1",
            "vendor": "github",
            "account_id": "acct_1",
            "account_label": "ACME Repo",
            "installed_by": "founder",
            "status": "connected",
            "last_sync_at": None,
        }
    ]


def test_ingest_normalize_to_entity_writes_source_id() -> None:
    from axiom.connectors.base import ConnectorEvent
    from axiom.connectors.ingest import normalize_to_entity

    event = ConnectorEvent(
        vendor="github",
        event_type="issue",
        external_id="octo/repo#1",
        payload={"title": "Fix billing sync", "entity_type": "ticket"},
        timestamp=datetime.utcnow(),
        signature_ok=True,
    )

    entity = normalize_to_entity("github", event)

    assert entity["type"] == "ticket"
    assert entity["source_id"] == "github:octo/repo#1"
    assert entity["data"]["vendor"] == "github"


@pytest.mark.asyncio
async def test_ingest_apply_to_brain_uses_existing_broadcaster(db_session) -> None:  # type: ignore[no-untyped-def]
    from axiom.connectors.ingest import apply_to_brain

    broadcaster = EventBroadcaster()
    entities = [
        {
            "nick": "repo",
            "type": "repo",
            "source_id": "github:repo:1",
            "cluster_id": "engineering_code",
            "data": {"name": "axiom"},
        },
        {
            "nick": "issue",
            "type": "ticket",
            "source_id": "github:issue:1",
            "cluster_id": "engineering_code",
            "data": {"title": "Bug"},
        },
    ]
    edges = [
        {
            "source_nick": "repo",
            "target_nick": "issue",
            "relationship": "repo_has_issue",
            "data": {},
        }
    ]

    count = await apply_to_brain(db_session, entities, edges, broadcaster=broadcaster)

    assert count == 3
    assert broadcaster.current_seq == 3
    persisted = db_session.execute(select(Entity).where(Entity.type == "ticket")).scalar_one()
    assert persisted.source_id == "github:issue:1"
    assert persisted.cluster_id == "engineering_code"


def test_writer_propose_action_returns_action_request() -> None:
    from axiom.connectors.writer import ConnectorWriter

    class TestWriter(ConnectorWriter):
        def _perform_execute(self, action, decision):  # type: ignore[no-untyped-def]
            return {"ok": True}

    writer = TestWriter(vendor="github")
    action = writer.propose_action("comment", {"issue_url": "https://example", "body": "LGTM"})

    assert action.agent_name == "connector:github"
    assert action.intent == "comment"
    assert action.payload["vendor"] == "github"


def test_writer_execute_blocks_when_policy_deny(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from axiom.connectors.writer import ConnectorWriteBlocked, ConnectorWriter

    class TestWriter(ConnectorWriter):
        def _perform_execute(self, action, decision):  # type: ignore[no-untyped-def]
            raise AssertionError("must not execute denied actions")

    sf = _session_factory(tmp_path)
    writer = TestWriter(
        vendor="github",
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="connector.test.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="connector.test.deny"):
        writer.execute(writer.propose_action("comment", {"body": "x"}), passport=SimpleNamespace())


def test_writer_execute_proceeds_when_policy_allow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from axiom.connectors.writer import ConnectorWriter

    class TestWriter(ConnectorWriter):
        def _perform_execute(self, action, decision):  # type: ignore[no-untyped-def]
            return {"executed": action.intent, "policy_id": decision.policy_id}

    sf = _session_factory(tmp_path)
    writer = TestWriter(
        vendor="github",
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="connector.test.allow")
        ),
    )

    result = writer.execute(
        writer.propose_action("comment", {"body": "x"}),
        passport=SimpleNamespace(passport_id=None),
    )

    assert result == {"executed": "comment", "policy_id": "connector.test.allow"}


def test_writer_execute_chains_receipt_with_real_policy_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from axiom.connectors.writer import ConnectorWriter

    class TestWriter(ConnectorWriter):
        def _perform_execute(self, action, decision):  # type: ignore[no-untyped-def]
            return {"ok": True}

    sf = _session_factory(tmp_path)
    writer = TestWriter(
        vendor="github",
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="connector.real.policy")
        ),
    )

    writer.execute(
        writer.propose_action("label", {"labels": ["bug"]}),
        passport=SimpleNamespace(passport_id=None),
    )

    with sf() as session:
        receipt = session.execute(select(Receipt)).scalar_one()
        assert receipt.policy_id == "connector.real.policy"
        assert receipt.decision == "allow"
        assert verify_receipt_chain(session, receipt.id) == "verified"


def test_connector_events_table_persists_raw_event(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sf = _session_factory(tmp_path)
    with sf() as session:
        row = ConnectorEventRow(
            id="event_1",
            vendor="github",
            connector_state_id="state_1",
            event_type="issues",
            external_id="octo/repo#1",
            payload={"action": "opened"},
            signature_ok=True,
            received_at=datetime.utcnow(),
            event_timestamp=datetime.utcnow() - timedelta(seconds=2),
        )
        session.add(row)
        session.commit()

    with sf() as session:
        persisted = session.get(ConnectorEventRow, "event_1")
        assert persisted is not None
        assert persisted.payload == {"action": "opened"}

    columns = {column["name"] for column in inspect(sf.kw["bind"]).get_columns("connector_events")}
    assert {"vendor", "event_type", "external_id", "payload", "signature_ok"}.issubset(columns)
