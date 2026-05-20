from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.github.ingest import (
    fetch_initial_repos as github_fetch_initial_repos,
)
from axiom.connectors.github.ingest import (
    fetch_issues as github_fetch_issues,
)
from axiom.connectors.github.ingest import (
    fetch_pull_requests as github_fetch_pull_requests,
)
from axiom.connectors.github.ingest import (
    normalize_issue as github_normalize_issue,
)
from axiom.connectors.github.ingest import (
    normalize_pull_request as github_normalize_pull_request,
)
from axiom.connectors.github.ingest import (
    normalize_repo as github_normalize_repo,
)
from axiom.connectors.github.ingest import (
    repo_to_issue_edge as github_repo_to_issue_edge,
)
from axiom.connectors.github.ingest import (
    repo_to_pr_edge as github_repo_to_pr_edge,
)
from axiom.connectors.gmail.ingest import fetch_labels as gmail_fetch_labels
from axiom.connectors.gmail.ingest import fetch_messages_in_thread as gmail_fetch_messages_in_thread
from axiom.connectors.gmail.ingest import fetch_threads as gmail_fetch_threads
from axiom.connectors.gmail.ingest import normalize_label as gmail_normalize_label
from axiom.connectors.gmail.ingest import normalize_message as gmail_normalize_message
from axiom.connectors.gmail.ingest import normalize_thread as gmail_normalize_thread
from axiom.connectors.gmail.ingest import thread_to_message_edge as gmail_thread_to_message_edge
from axiom.connectors.ingest import apply_to_brain
from axiom.connectors.linear.ingest import fetch_issues_for_team as linear_fetch_issues_for_team
from axiom.connectors.linear.ingest import fetch_projects as linear_fetch_projects
from axiom.connectors.linear.ingest import fetch_teams as linear_fetch_teams
from axiom.connectors.linear.ingest import normalize_issue as linear_normalize_issue
from axiom.connectors.linear.ingest import normalize_project as linear_normalize_project
from axiom.connectors.linear.ingest import normalize_team as linear_normalize_team
from axiom.connectors.linear.ingest import project_to_issue_edge as linear_project_to_issue_edge
from axiom.connectors.linear.ingest import team_to_issue_edge as linear_team_to_issue_edge
from axiom.connectors.notion.ingest import database_to_page_edge as notion_database_to_page_edge
from axiom.connectors.notion.ingest import fetch_databases as notion_fetch_databases
from axiom.connectors.notion.ingest import fetch_pages_in_database as notion_fetch_pages_in_database
from axiom.connectors.notion.ingest import normalize_database as notion_normalize_database
from axiom.connectors.notion.ingest import normalize_page as notion_normalize_page
from axiom.connectors.notion.poller import NotionPoller
from axiom.connectors.slack.ingest import fetch_channels as slack_fetch_channels
from axiom.connectors.slack.ingest import fetch_recent_messages_per_channel as slack_fetch_recent_messages_per_channel
from axiom.connectors.slack.ingest import fetch_users as slack_fetch_users
from axiom.connectors.slack.ingest import normalize_channel as slack_normalize_channel
from axiom.connectors.slack.ingest import normalize_message as slack_normalize_message
from axiom.connectors.slack.ingest import normalize_user as slack_normalize_user
from axiom.connectors.slack.ingest import (
    channel_to_message_edge as slack_channel_to_message_edge,
)
from axiom.connectors.slack.ingest import (
    message_mention_edges as slack_message_mention_edges,
)
from axiom.connectors.slack.ingest import (
    thread_parent_child_edge as slack_thread_parent_child_edge,
)
from axiom.env import vault_status
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.retrieval.embeddings import bootstrap_embeddings
from axiom.schema.models import ConnectorEventRow, ConnectorStateRow
from axiom.vault.errors import SecretNotFound, VaultCorrupt, VaultLocked
from axiom.vault.store import get_secret_with_session

log = logging.getLogger("axiom.connectors.sync")
CONNECTOR_VENDORS = ("github", "linear", "slack", "notion", "gmail")


def connector_sync_interval_seconds() -> int:
    raw = os.environ.get("AXIOM_CONNECTOR_SYNC_INTERVAL_SECONDS", "300")
    try:
        return max(60, int(raw))
    except ValueError:
        return 300


def connector_startup_delay_seconds() -> float:
    raw = os.environ.get("AXIOM_CONNECTOR_SYNC_STARTUP_DELAY_SECONDS", "2")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 2.0


def vault_is_unlocked() -> bool:
    present, error = vault_status()
    return present and error is None


def _now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def _secret_key_from_ref(vendor: str, ref: str) -> str | None:
    prefix = f"vault:connector:{vendor}:"
    return ref.removeprefix(prefix) if ref.startswith(prefix) else None


def connector_token_state(session: Session, row: ConnectorStateRow) -> SimpleNamespace:
    def resolve(ref: str | None) -> str | None:
        if not ref:
            return None
        key_name = _secret_key_from_ref(row.vendor, ref)
        if key_name is None:
            return ref
        return get_secret_with_session(session, f"connector:{row.vendor}", key_name)

    return SimpleNamespace(
        access_token=resolve(row.access_token) or "",
        refresh_token=resolve(row.refresh_token),
        token_expires_at=row.token_expires_at,
    )


def _connected_state(session: Session, vendor: str) -> ConnectorStateRow | None:
    row = (
        session.execute(select(ConnectorStateRow).where(ConnectorStateRow.vendor == vendor))
        .scalars()
        .first()
    )
    if row is None or row.status != "connected":
        return None
    return row


async def sync_github(session: Session, broadcaster: EventBroadcaster) -> dict[str, Any]:
    state = _connected_state(session, "github")
    if state is None:
        raise LookupError("GitHub connector not installed")
    token_state = connector_token_state(session, state)
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for repo in github_fetch_initial_repos(token_state):
        repo_entity = github_normalize_repo(repo)
        entities.append(repo_entity)
        repo_name = str(repo["full_name"])
        for issue in github_fetch_issues(token_state, repo_name):
            issue_entity = github_normalize_issue(repo_name, issue)
            entities.append(issue_entity)
            edges.append(github_repo_to_issue_edge(repo_entity["nick"], issue_entity["nick"]))
        for pull_request in github_fetch_pull_requests(token_state, repo_name):
            pr_entity = github_normalize_pull_request(repo_name, pull_request)
            entities.append(pr_entity)
            edges.append(github_repo_to_pr_edge(repo_entity["nick"], pr_entity["nick"]))
    count = await apply_to_brain(session, entities, edges, broadcaster=broadcaster)
    state.last_sync_at = datetime.utcnow()
    session.add(state)
    session.commit()
    return {"vendor": "github", "status": "ok", "ingested": count}


async def sync_linear(session: Session, broadcaster: EventBroadcaster) -> dict[str, Any]:
    state = _connected_state(session, "linear")
    if state is None:
        raise LookupError("Linear connector not installed")
    token_state = connector_token_state(session, state)
    teams = linear_fetch_teams(token_state)
    projects = linear_fetch_projects(token_state)
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    projects_by_id: dict[str, dict[str, Any]] = {}
    for project in projects:
        project_entity = linear_normalize_project(project)
        projects_by_id[str(project["id"])] = project_entity
        entities.append(project_entity)
    for team in teams:
        team_entity = linear_normalize_team(team)
        entities.append(team_entity)
        for issue in linear_fetch_issues_for_team(token_state, str(team["id"])):
            issue_entity = linear_normalize_issue(issue)
            entities.append(issue_entity)
            edges.append(linear_team_to_issue_edge(team_entity["nick"], issue_entity["nick"]))
            project_payload = issue.get("project")
            project_id = str(project_payload.get("id")) if isinstance(project_payload, dict) else ""
            linked_project_entity = projects_by_id.get(project_id)
            if linked_project_entity is not None:
                edges.append(
                    linear_project_to_issue_edge(linked_project_entity["nick"], issue_entity["nick"])
                )
    count = await apply_to_brain(session, entities, edges, broadcaster=broadcaster)
    state.last_sync_at = datetime.utcnow()
    session.add(state)
    session.commit()
    return {"vendor": "linear", "status": "ok", "ingested": count}


async def sync_slack(session: Session, broadcaster: EventBroadcaster) -> dict[str, Any]:
    state = _connected_state(session, "slack")
    if state is None:
        raise LookupError("Slack connector not installed")
    token_state = connector_token_state(session, state)
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for user in slack_fetch_users(token_state):
        entities.append(slack_normalize_user(user))
    for channel in slack_fetch_channels(token_state):
        channel_entity = slack_normalize_channel(channel)
        entities.append(channel_entity)
        channel_id = str(channel["id"])
        for message in slack_fetch_recent_messages_per_channel(token_state, channel_id):
            message_entity = slack_normalize_message(channel_id, message)
            entities.append(message_entity)
            edges.append(
                slack_channel_to_message_edge(channel_entity["nick"], message_entity["nick"])
            )
            parent_ts = message.get("thread_ts")
            if parent_ts and parent_ts != message.get("ts"):
                edges.append(
                    slack_thread_parent_child_edge(
                        f"message:{channel_id}:{parent_ts}",
                        message_entity["nick"],
                    )
                )
            edges.extend(
                slack_message_mention_edges(message_entity["nick"], str(message.get("text") or ""))
            )
    count = await apply_to_brain(session, entities, edges, broadcaster=broadcaster)
    state.last_sync_at = datetime.utcnow()
    session.add(state)
    session.commit()
    return {"vendor": "slack", "status": "ok", "ingested": count}


async def sync_notion(session: Session, broadcaster: EventBroadcaster) -> dict[str, Any]:
    state = _connected_state(session, "notion")
    if state is None:
        raise LookupError("Notion connector not installed")
    token_state = connector_token_state(session, state)
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for database in notion_fetch_databases(token_state):
        database_entity = notion_normalize_database(database)
        entities.append(database_entity)
        for page in notion_fetch_pages_in_database(token_state, str(database["id"])):
            page_entity = notion_normalize_page(page)
            entities.append(page_entity)
            edges.append(notion_database_to_page_edge(database_entity["nick"], page_entity["nick"]))
    ingested = await apply_to_brain(session, entities, edges, broadcaster=broadcaster)

    poll_events = NotionPoller(state=token_state).poll_once()
    for event in poll_events:
        session.add(
            ConnectorEventRow(
                vendor="notion",
                connector_state_id=state.id,
                event_type=event.event_type,
                external_id=event.external_id,
                payload=event.payload,
                signature_ok=True,
                received_at=datetime.utcnow(),
                event_timestamp=event.timestamp,
            )
        )
    state.last_sync_at = datetime.utcnow()
    session.add(state)
    session.commit()

    for event in poll_events:
        await broadcaster.publish(
            {
                "type": "connector_event_received",
                "source_id": "notion",
                "persisted_id": event.external_id,
                "timestamp": _now_ms(),
                "payload": {"vendor": "notion", "event_type": event.event_type},
            }
        )

    return {
        "vendor": "notion",
        "status": "ok",
        "ingested": ingested,
        "events": len(poll_events),
        "watch_mode": "polling",
    }


async def sync_gmail(session: Session, broadcaster: EventBroadcaster) -> dict[str, Any]:
    state = _connected_state(session, "gmail")
    if state is None:
        raise LookupError("Gmail connector not installed")
    token_state = connector_token_state(session, state)
    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for label in gmail_fetch_labels(token_state):
        entities.append(gmail_normalize_label(label))
    for thread in gmail_fetch_threads(token_state):
        thread_entity = gmail_normalize_thread(thread)
        entities.append(thread_entity)
        thread_id = str(thread["id"])
        try:
            messages = gmail_fetch_messages_in_thread(token_state, thread_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping Gmail thread %s — fetch failed: %s", thread_id, exc)
            continue
        for message in messages:
            message_entity = gmail_normalize_message(message)
            entities.append(message_entity)
            edges.append(gmail_thread_to_message_edge(thread_entity["nick"], message_entity["nick"]))
    count = await apply_to_brain(session, entities, edges, broadcaster=broadcaster)
    state.last_sync_at = datetime.utcnow()
    session.add(state)
    session.commit()
    return {"vendor": "gmail", "status": "ok", "ingested": count}


_VENDOR_SYNCERS = {
    "github": sync_github,
    "linear": sync_linear,
    "slack": sync_slack,
    "notion": sync_notion,
    "gmail": sync_gmail,
}


def schedule_connector_sync_after_oauth(
    vendor: str,
    session_factory: sessionmaker[Session],
    broadcaster: EventBroadcaster,
) -> None:
    """Schedule an immediate background sync after OAuth completes."""
    if not vault_is_unlocked():
        log.warning("Skipping post-OAuth sync for %s — vault is locked", vendor)
        return

    async def _run() -> None:
        try:
            with session_factory() as session:
                result = await sync_vendor(session, vendor, broadcaster)
            log.info(
                "Post-OAuth sync for %s finished (ingested=%s)",
                vendor,
                result.get("ingested", result.get("events", 0)),
            )
        except LookupError:
            log.warning("Post-OAuth sync skipped — %s not connected", vendor)
        except (VaultLocked, VaultCorrupt, SecretNotFound) as exc:
            log.warning("Post-OAuth sync for %s failed — vault: %s", vendor, exc)
        except Exception:
            log.exception("Post-OAuth sync failed for %s", vendor)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run())
        return
    loop.create_task(_run())


async def sync_vendor(
    session: Session,
    vendor: str,
    broadcaster: EventBroadcaster,
) -> dict[str, Any]:
    syncer = _VENDOR_SYNCERS.get(vendor)
    if syncer is None:
        raise ValueError(f"unknown connector vendor: {vendor}")
    return await syncer(session, broadcaster)


async def sync_all_connected_connectors(
    session_factory: sessionmaker[Session],
    broadcaster: EventBroadcaster,
) -> dict[str, Any]:
    if not vault_is_unlocked():
        return {"skipped": "vault_locked", "results": []}

    with session_factory() as session:
        vendors = list(
            session.execute(
                select(ConnectorStateRow.vendor).where(ConnectorStateRow.status == "connected")
            )
            .scalars()
            .all()
        )

    if not vendors:
        return {"skipped": "none_connected", "results": []}

    results: list[dict[str, Any]] = []
    for vendor in vendors:
        try:
            with session_factory() as session:
                result = await sync_vendor(session, vendor, broadcaster)
                results.append(result)
                log.info(
                    "Synced %s connector (ingested=%s)",
                    vendor,
                    result.get("ingested", result.get("events", 0)),
                )
        except (VaultLocked, VaultCorrupt, SecretNotFound) as exc:
            log.warning("Skipping %s sync — vault unavailable: %s", vendor, exc)
        except LookupError:
            continue
        except Exception:
            log.exception("Connector sync failed for %s", vendor)

    try:
        with session_factory() as session:
            embedded = bootstrap_embeddings(session)
            if embedded:
                log.info("Indexed embeddings for %d entities after connector sync", embedded)
    except Exception:
        log.exception("Embedding bootstrap after connector sync failed")

    await broadcaster.publish(
        {
            "type": "connector_sync_completed",
            "source_id": None,
            "persisted_id": None,
            "timestamp": _now_ms(),
            "payload": {"vendors": [item.get("vendor") for item in results], "results": results},
        }
    )
    return {"results": results}


async def connector_sync_loop(
    session_factory: sessionmaker[Session],
    broadcaster: EventBroadcaster,
) -> None:
    if not vault_is_unlocked():
        log.warning("Connector auto-sync disabled — vault is locked")
        return

    delay = connector_startup_delay_seconds()
    if delay:
        await asyncio.sleep(delay)

    interval = connector_sync_interval_seconds()
    log.info("Connector auto-sync enabled (interval=%ss)", interval)

    while True:
        try:
            summary = await sync_all_connected_connectors(session_factory, broadcaster)
            if summary.get("results"):
                log.info("Connector auto-sync cycle finished: %d vendor(s)", len(summary["results"]))
        except Exception:
            log.exception("Connector auto-sync cycle failed; will retry")
        await asyncio.sleep(interval)
