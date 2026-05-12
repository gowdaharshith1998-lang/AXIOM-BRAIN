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
from axiom.vault.store import get_secret_with_session


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'github.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="state_1",
                connector_id="cfg_1",
                vendor="github",
                access_token="gho_token",
                account_id="octo",
                account_label="Octo Org",
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


def test_github_oauth_authorize_url_includes_required_scopes() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.github.oauth import GitHubOAuth

    flow = GitHubOAuth(
        ConnectorConfig(
            id="cfg_1",
            vendor="github",
            oauth_client_id="client",
            redirect_uri="https://axiom.local/callback",
        )
    )

    url = flow.authorize_url("csrf")

    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "scope=repo+read%3Aorg+write%3Adiscussion" in url
    assert "state=csrf" in url


@responses.activate
def test_github_oauth_exchange_code_stores_token() -> None:
    from axiom.connectors.base import ConnectorConfig
    from axiom.connectors.github.oauth import GitHubOAuth

    responses.post(
        "https://github.com/login/oauth/access_token",
        json={"access_token": "gho_token", "scope": "repo", "token_type": "bearer"},
        status=200,
    )
    flow = GitHubOAuth(
        ConnectorConfig(
            id="cfg_1",
            vendor="github",
            oauth_client_id="client",
            oauth_client_secret="secret",
            redirect_uri="https://axiom.local/callback",
        )
    )

    state = flow.exchange_code("code_123")

    assert state.connector_id == "cfg_1"
    assert state.access_token == "gho_token"
    assert state.refresh_token is None
    assert state.token_expires_at is None


def test_github_webhook_hmac_verify_with_real_signature() -> None:
    from axiom.connectors.github.webhook import GitHubWebhookHandler

    body = b'{"action":"opened"}'
    digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    request = SimpleNamespace(body=body, headers={"X-Hub-Signature-256": f"sha256={digest}"})

    assert GitHubWebhookHandler("secret").verify(request) is True


def test_github_webhook_parse_issue_opened_event() -> None:
    from axiom.connectors.github.webhook import GitHubWebhookHandler

    body = json.dumps(
        {
            "action": "opened",
            "issue": {"id": 12, "number": 7, "title": "Bug"},
            "repository": {"full_name": "octo/repo"},
        }
    ).encode()
    request = SimpleNamespace(
        body=body,
        headers={"X-GitHub-Event": "issues", "X-GitHub-Delivery": "delivery_1"},
    )

    event = GitHubWebhookHandler("secret").parse(request)[0]

    assert event.vendor == "github"
    assert event.event_type == "issues.opened"
    assert event.external_id == "delivery_1"
    assert event.payload["issue"]["title"] == "Bug"


def test_github_webhook_parse_pull_request_event() -> None:
    from axiom.connectors.github.webhook import GitHubWebhookHandler

    body = json.dumps(
        {
            "action": "opened",
            "pull_request": {"id": 99, "number": 3, "title": "Feature"},
            "repository": {"full_name": "octo/repo"},
        }
    ).encode()
    request = SimpleNamespace(
        body=body,
        headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "delivery_2"},
    )

    event = GitHubWebhookHandler("secret").parse(request)[0]

    assert event.event_type == "pull_request.opened"
    assert event.payload["pull_request"]["number"] == 3


@responses.activate
def test_github_ingest_fetches_repos_and_writes_entities(tmp_path: Path) -> None:
    from axiom.connectors.github.ingest import fetch_initial_repos, normalize_repo

    responses.get(
        "https://api.github.com/user/repos",
        json=[{"id": 1, "full_name": "octo/repo", "name": "repo"}],
        headers={"Link": ""},
    )
    repos = fetch_initial_repos(SimpleNamespace(access_token="gho_token"))
    entity = normalize_repo(repos[0])

    assert entity["type"] == "repo"
    assert entity["cluster_id"] == "engineering_code"
    assert entity["source_id"] == "github:repo:1"


@responses.activate
def test_github_ingest_fetches_issues_paginated() -> None:
    from axiom.connectors.github.ingest import fetch_issues

    responses.get(
        "https://api.github.com/repos/octo/repo/issues",
        json=[{"id": 1, "number": 1, "title": "One"}],
        headers={"Link": '<https://api.github.com/repos/octo/repo/issues?page=2>; rel="next"'},
    )
    responses.get(
        "https://api.github.com/repos/octo/repo/issues?page=2",
        json=[{"id": 2, "number": 2, "title": "Two"}],
        headers={"Link": ""},
    )

    issues = fetch_issues(SimpleNamespace(access_token="t"), "octo/repo")
    assert [issue["number"] for issue in issues] == [1, 2]


def test_github_ingest_normalizes_issue_to_ticket_entity() -> None:
    from axiom.connectors.github.ingest import normalize_issue

    entity = normalize_issue("octo/repo", {"id": 1, "number": 5, "title": "Bug"})

    assert entity["type"] == "ticket"
    assert entity["source_id"] == "github:issue:1"
    assert entity["data"]["repo"] == "octo/repo"


def test_github_ingest_creates_repo_to_issue_edge() -> None:
    from axiom.connectors.github.ingest import repo_to_issue_edge

    edge = repo_to_issue_edge("repo:1", "issue:1")

    assert edge == {
        "source_nick": "repo:1",
        "target_nick": "issue:1",
        "relationship": "repo_has_issue",
        "data": {},
    }


def test_github_writer_propose_comment_returns_action_request() -> None:
    from axiom.connectors.github.writer import GitHubWriter

    action = GitHubWriter().propose_action(
        "comment",
        {"issue_url": "https://github.com/octo/repo/issues/7", "body": "Looks good"},
    )

    assert action.intent == "comment"
    assert action.payload["issue_url"].endswith("/issues/7")
    assert action.proposed_action == "github.comment"


def test_github_writer_execute_blocks_on_policy_deny(tmp_path: Path) -> None:
    from axiom.connectors.github.writer import GitHubWriter
    from axiom.connectors.writer import ConnectorWriteBlocked

    writer = GitHubWriter(
        state=SimpleNamespace(access_token="gho_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="deny", reason="blocked", policy_id="github.policy.deny")
        ),
    )

    with pytest.raises(ConnectorWriteBlocked, match="github.policy.deny"):
        writer.execute(
            writer.propose_action(
                "comment",
                {"issue_url": "https://github.com/octo/repo/issues/7", "body": "x"},
            )
        )


@responses.activate
def test_github_writer_execute_proceeds_on_policy_allow(tmp_path: Path) -> None:
    from axiom.connectors.github.writer import GitHubWriter

    responses.post("https://api.github.com/repos/octo/repo/issues/7/comments", json={"id": 55})
    writer = GitHubWriter(
        state=SimpleNamespace(access_token="gho_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="github.policy.allow")
        ),
    )

    result = writer.execute(
        writer.propose_action(
            "comment",
            {"issue_url": "https://github.com/octo/repo/issues/7", "body": "x"},
        )
    )

    assert result["id"] == 55


@responses.activate
def test_github_writer_execute_calls_github_api_with_token(tmp_path: Path) -> None:
    from axiom.connectors.github.writer import GitHubWriter

    responses.post("https://api.github.com/repos/octo/repo/issues/7/comments", json={"id": 55})
    writer = GitHubWriter(
        state=SimpleNamespace(access_token="gho_token"),
        session_factory=_sf(tmp_path),
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="github.policy.allow")
        ),
    )

    writer.execute(
        writer.propose_action(
            "comment",
            {"issue_url": "https://github.com/octo/repo/issues/7", "body": "x"},
        )
    )

    assert responses.calls[0].request.headers["Authorization"] == "Bearer gho_token"
    assert json.loads(responses.calls[0].request.body or "{}") == {"body": "x"}


@responses.activate
def test_github_writer_execute_chains_receipt(tmp_path: Path) -> None:
    from axiom.connectors.github.writer import GitHubWriter

    sf = _sf(tmp_path)
    responses.patch("https://api.github.com/repos/octo/repo/issues/7", json={"state": "closed"})
    writer = GitHubWriter(
        state=SimpleNamespace(access_token="gho_token"),
        session_factory=sf,
        policy_evaluator=_PolicyEvaluator(
            PolicyDecision(mode="allow", reason="ok", policy_id="github.policy.allow")
        ),
    )

    writer.execute(
        writer.propose_action("close", {"issue_url": "https://github.com/octo/repo/issues/7"})
    )

    with sf() as session:
        receipt = session.execute(
            select(Receipt).where(Receipt.policy_id == "github.policy.allow")
        ).scalar_one()
        assert receipt.decision == "allow"


@responses.activate
def test_github_callback_endpoint_persists_connector_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.studio.server import create_app

    monkeypatch.setenv("AXIOM_CONNECTOR_GITHUB_ENABLED", "1")
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_ID", "client")
    monkeypatch.setenv("AXIOM_GITHUB_CLIENT_SECRET", "secret")
    responses.post(
        "https://github.com/login/oauth/access_token",
        json={"access_token": "gho_token"},
    )

    db_url = f"sqlite:///{tmp_path / 'api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        install = client.post("/api/internal/connectors/github/install")
        state = install.json()["state"]
        response = client.get(f"/api/internal/connectors/github/callback?code=abc&state={state}")

    assert response.status_code == 200
    with Session(engine) as session:
        state = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "github")
        ).scalar_one()
        assert state.access_token.startswith("vault:connector:github:")
        assert (
            get_secret_with_session(
                session,
                "connector:github",
                state.access_token.removeprefix("vault:connector:github:"),
            )
            == "gho_token"
        )
        assert state.account_label == "GitHub"
