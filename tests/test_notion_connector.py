from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import responses
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.policy import PolicyDecision
from axiom.schema.models import Base, ConnectorStateRow


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'notion.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="notion_state_1",
                connector_id="notion",
                vendor="notion",
                access_token="secret_token",
                account_id="workspace_1",
                account_label="Axiom Wiki",
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


def test_notion_oauth_authorize_url_correct() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.notion.oauth import NotionOAuth

    flow = NotionOAuth(
        ConnectorConfig(
            id="notion",
            vendor="notion",
            oauth_client_id="client",
            redirect_uri="https://axiom.local/notion/callback",
        )
    )

    url = flow.authorize_url("csrf")

    assert url.startswith("https://api.notion.com/v1/oauth/authorize?")
    assert "owner=user" in url
    assert "state=csrf" in url


@responses.activate
def test_notion_oauth_exchange_code_stores_token() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.notion.oauth import NotionOAuth

    responses.post(
        "https://api.notion.com/v1/oauth/token",
        json={
            "access_token": "secret_token",
            "workspace_id": "workspace_1",
            "workspace_name": "Axiom Wiki",
        },
    )

    state = NotionOAuth(
        ConnectorConfig(
            id="notion",
            vendor="notion",
            oauth_client_id="client",
            oauth_client_secret="secret",
            redirect_uri="https://axiom.local/notion/callback",
        )
    ).exchange_code("code")

    assert state.connector_id == "notion"
    assert state.access_token == "secret_token"
    assert state.account_label == "Axiom Wiki"


@responses.activate
def test_notion_poller_detects_changed_pages() -> None:
    from axiom.connectors.notion.poller import NotionPoller

    responses.post(
        "https://api.notion.com/v1/search",
        json={
            "results": [
                {"id": "page_1", "object": "page", "last_edited_time": "2026-01-02T00:00:00Z"}
            ]
        },
    )

    events = NotionPoller(
        state=SimpleNamespace(access_token="secret_token"),
        last_seen={"page_1": "2026-01-01T00:00:00Z"},
    ).poll_once()

    assert events[0].event_type == "page.changed"
    assert events[0].external_id == "page_1"


@responses.activate
def test_notion_poller_skips_unchanged_pages() -> None:
    from axiom.connectors.notion.poller import NotionPoller

    responses.post(
        "https://api.notion.com/v1/search",
        json={
            "results": [
                {"id": "page_1", "object": "page", "last_edited_time": "2026-01-01T00:00:00Z"}
            ]
        },
    )

    events = NotionPoller(
        state=SimpleNamespace(access_token="secret_token"),
        last_seen={"page_1": "2026-01-01T00:00:00Z"},
    ).poll_once()

    assert events == []


@responses.activate
def test_notion_poller_emits_connector_events() -> None:
    from axiom.connectors.notion.poller import NotionPoller

    responses.post(
        "https://api.notion.com/v1/search",
        json={
            "results": [
                {"id": "page_2", "object": "page", "last_edited_time": "2026-01-03T00:00:00Z"}
            ]
        },
    )

    event = NotionPoller(state=SimpleNamespace(access_token="secret_token")).poll_once()[0]

    assert event.vendor == "notion"
    assert event.payload["object"] == "page"
    assert event.signature_ok is True


def test_notion_ingest_normalizes_database_to_entity() -> None:
    from axiom.connectors.notion.ingest import normalize_database

    entity = normalize_database({"id": "database_1", "title": []})

    assert entity["type"] == "database"
    assert entity["cluster_id"] == "knowledge"
    assert entity["source_id"] == "notion:database:database_1"


def test_notion_ingest_normalizes_page_to_document() -> None:
    from axiom.connectors.notion.ingest import normalize_page

    entity = normalize_page({"id": "page_1", "url": "https://notion.so/page_1"})

    assert entity["type"] == "document"
    assert entity["source_id"] == "notion:page:page_1"


def test_notion_writer_propose_update_page_returns_action_request() -> None:
    from axiom.connectors.notion.writer import NotionWriter

    action = NotionWriter().propose_action(
        "update_page",
        {"page_id": "page_1", "properties": {"Status": {"select": {"name": "Done"}}}},
    )

    assert action.intent == "update_page"
    assert action.proposed_action == "notion.update_page"
    assert action.payload["page_id"] == "page_1"


def test_notion_writer_execute_blocks_on_policy_deny(tmp_path: Path) -> None:
    from axiom.connectors.notion.writer import NotionWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    writer = NotionWriter(
        state=SimpleNamespace(access_token="secret_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="notion.policy.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="notion.policy.deny"):
        writer.execute(writer.propose_action("archive_page", {"page_id": "page_1"}))


@responses.activate
def test_notion_writer_execute_calls_notion_api(tmp_path: Path) -> None:
    from axiom.connectors.notion.writer import NotionWriter

    responses.patch("https://api.notion.com/v1/pages/page_1", json={"id": "page_1"})
    writer = NotionWriter(
        state=SimpleNamespace(access_token="secret_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="notion.policy.allow")
        ),
    )

    result = writer.execute(writer.propose_action("archive_page", {"page_id": "page_1"}))

    assert result["id"] == "page_1"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret_token"
    assert responses.calls[0].request.headers["Notion-Version"] == "2022-06-28"
