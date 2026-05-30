from __future__ import annotations

import asyncio
import base64
import html
import hmac
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, NoReturn, cast

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Table, create_engine, desc, func, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.api.search import EntitySearchResult, search_entities
from axiom.connectors.sync_runner import (
    connector_sync_loop,
    run_initial_sync,
    schedule_connector_sync_after_oauth,
    sync_all_connected_connectors,
    sync_gmail,
    sync_github,
    sync_linear,
    sync_notion,
    sync_slack,
    sync_vendor,
)
from axiom.env import load_axiom_env, log_vault_startup_status
from axiom.connectors.base import ConnectorConfig
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
from axiom.connectors.github.oauth import GITHUB_SCOPES, GitHubOAuth
from axiom.connectors.github.webhook import GitHubWebhookHandler
from axiom.connectors.gmail.ingest import fetch_labels as gmail_fetch_labels
from axiom.connectors.gmail.ingest import fetch_messages_in_thread as gmail_fetch_messages_in_thread
from axiom.connectors.gmail.ingest import fetch_threads as gmail_fetch_threads
from axiom.connectors.gmail.ingest import normalize_label as gmail_normalize_label
from axiom.connectors.gmail.ingest import normalize_message as gmail_normalize_message
from axiom.connectors.gmail.ingest import normalize_thread as gmail_normalize_thread
from axiom.connectors.gmail.ingest import thread_to_message_edge as gmail_thread_to_message_edge
from axiom.connectors.gmail.oauth import GMAIL_SCOPES, GmailOAuth
from axiom.connectors.gmail.webhook import GmailWebhookHandler
from axiom.connectors.ingest import apply_to_brain, normalize_to_edges, normalize_to_entity
from axiom.connectors.linear.ingest import fetch_issues_for_team as linear_fetch_issues_for_team
from axiom.connectors.linear.ingest import fetch_projects as linear_fetch_projects
from axiom.connectors.linear.ingest import fetch_teams as linear_fetch_teams
from axiom.connectors.linear.ingest import normalize_issue as linear_normalize_issue
from axiom.connectors.linear.ingest import normalize_project as linear_normalize_project
from axiom.connectors.linear.ingest import normalize_team as linear_normalize_team
from axiom.connectors.linear.ingest import project_to_issue_edge as linear_project_to_issue_edge
from axiom.connectors.linear.ingest import team_to_issue_edge as linear_team_to_issue_edge
from axiom.connectors.linear.oauth import LINEAR_SCOPES, LinearOAuth
from axiom.connectors.linear.webhook import LinearWebhookHandler
from axiom.connectors.notion.ingest import database_to_page_edge as notion_database_to_page_edge
from axiom.connectors.notion.ingest import fetch_databases as notion_fetch_databases
from axiom.connectors.notion.ingest import fetch_pages_in_database as notion_fetch_pages_in_database
from axiom.connectors.notion.ingest import normalize_database as notion_normalize_database
from axiom.connectors.notion.ingest import normalize_page as notion_normalize_page
from axiom.connectors.notion.oauth import NotionOAuth
from axiom.connectors.notion.poller import NotionPoller
from axiom.connectors.registry import ensure_connectors_schema
from axiom.connectors.registry import list_installed as list_connectors
from axiom.connectors.slack.ingest import channel_to_message_edge as slack_channel_to_message_edge
from axiom.connectors.slack.ingest import fetch_channels as slack_fetch_channels
from axiom.connectors.slack.ingest import (
    fetch_recent_messages_per_channel as slack_fetch_recent_messages_per_channel,
)
from axiom.connectors.slack.ingest import fetch_users as slack_fetch_users
from axiom.connectors.slack.ingest import message_mention_edges as slack_message_mention_edges
from axiom.connectors.slack.ingest import normalize_channel as slack_normalize_channel
from axiom.connectors.slack.ingest import normalize_message as slack_normalize_message
from axiom.connectors.slack.ingest import normalize_user as slack_normalize_user
from axiom.connectors.slack.ingest import (
    thread_parent_child_edge as slack_thread_parent_child_edge,
)
from axiom.connectors.slack.oauth import SLACK_BOT_SCOPES, SlackOAuth
from axiom.connectors.slack.webhook import SlackWebhookHandler
from axiom.govern.agent_actions import emit_demo_agent_actions
from axiom.govern.agent_registry import (
    AgentType,
    agent_registry_row,
    backfill_agent_registry_from_receipts,
    ensure_agent_registry_schema,
    get_agents,
)
from axiom.govern.approvals import (
    approval_to_dict,
    approve_request,
    deny_request,
    ensure_approvals_schema,
    expire_old_requests,
    get_approval,
    list_pending_approvals,
)
from axiom.govern.cluster_checks import (
    cleanup_cluster_check_runs,
    cluster_check_run_row,
    ensure_cluster_check_runs_schema,
    get_cluster_check_runs,
    record_cluster_check_runs,
    retention_limit_from_env,
    summarize_cluster_check_runs,
)
from axiom.govern.llm_keys import ensure_llm_provider_keys_schema
from axiom.govern.passports import (
    ensure_passports_schema,
    get_passport,
    issue_passport,
    list_passports,
    passport_to_dict,
    revoke_passport,
    toggle_kill_switch,
)
from axiom.govern.policy_evaluator import DemoPolicyEvaluator, get_policy_evaluator
from axiom.govern.receipts import (
    ensure_receipts_schema,
    receipt_to_dict,
)
from axiom.govern.snapshots import (
    backfill_snapshots_from_receipts,
    ensure_snapshots_schema,
    get_snapshots,
    take_snapshot,
)
from axiom.govern.verify import verify_receipt_chain
from axiom.govern.warden import emit_demo_warden_insights
from axiom.govern.watchdog import (
    WatchdogAgent,
    acknowledge_alert,
    alert_to_dict,
    ensure_watchdog_alerts_schema,
    list_open_alerts,
    resolve_alert,
)
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.organize.agent import OrganizerAgent
from axiom.organize.cluster_health import (
    ClusterHealthMonitor,
    compute_brain_health_score,
    health_status_for_score,
)
from axiom.policy import ActionRequest, PolicyRule, RealPolicyEvaluator, reload_policies
from axiom.retrieval.embeddings import bootstrap_embeddings, ensure_entity_embeddings_schema
from axiom.retrieval.search import SearchMode, hybrid_search
from axiom.schema.dto import EdgeDTO, EntityDTO
from axiom.schema.models import (
    Action,
    AgentPassport,
    AgentRegistry,
    ClusterCheckRun,
    ConnectorConfigRow,
    ConnectorEventRow,
    ConnectorStateRow,
    Edge,
    Entity,
    MetricsSnapshot,
    Receipt,
    Skill,
    Source,
    new_id,
)
from axiom.sign.ed25519_signer import load_or_create_keypair
from axiom.skills.emitter import compile_skills_from_processes, manifest_to_dict
from axiom.skills.registry import (
    SkillNotFound,
    activate_skill_with_session,
    archive_skill_with_session,
    ensure_skills_schema,
    get_skill_with_session,
    list_skill_runs_with_session,
    list_skills_with_session,
    register_skill_with_session,
    skill_run_to_dict,
    skill_to_dict,
)
from axiom.skills.runner import run_skill
from axiom.skills.skill_md import (
    SkillManifest,
    SkillManifestError,
    parse_skill_md,
    serialize_skill_md,
)
from axiom.sources.base import IngestEvent
from axiom.sources.live_synthetic import LiveSyntheticSource
from axiom.studio.auth import (
    auth_is_misconfigured,
    auth_required,
    is_http_auth_exempt,
    request_is_authenticated,
    websocket_auth_subprotocol,
    websocket_is_authenticated,
)
from axiom.studio.brain_ask_api import router as brain_ask_router
from axiom.studio.llm_keys_api import router as llm_keys_router
from axiom.studio.sources import ensure_sources_schema, real_sources_snapshot
from axiom.studio.vault_api import router as vault_router
from axiom.vault.errors import SecretNotFound, VaultCorrupt, VaultLocked
from axiom.vault.models import Secret
from axiom.vault.store import (
    delete_secret_with_session,
    get_secret_with_session,
    store_secret_with_session,
)


class NavigationStepIn(BaseModel):
    from_id: str
    to_id: str
    edge_id: str | None = None


class NavigationBatchIn(BaseModel):
    agent_name: str = "external_mcp_client"
    steps: list[NavigationStepIn] = Field(default_factory=list)


class AgentActionEventsIn(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


class SkillIn(BaseModel):
    name: str
    description: str = ""
    intent: str
    prompt_template: str
    llm_provider: str
    llm_model: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    trigger_type: str = "manual"
    created_by: str = "external_mcp_client"


class SkillRunIn(BaseModel):
    input_payload: dict[str, Any] = Field(default_factory=dict)
    agent_name: str = "external_mcp_client"
    idempotency_key: str | None = None


class SkillMdIn(BaseModel):
    content: str


class CompileSkillsIn(BaseModel):
    dry_run: bool = False
    process_ids: list[str] | None = None


class ConnectorConfigIn(BaseModel):
    oauth_client_id: str
    oauth_client_secret: str
    redirect_uri: str | None = None
    webhook_secret: str | None = None
    workspace_id: str | None = None


MAX_PUBLIC_PASSPORT_TTL_HOURS = 24


class PassportIn(BaseModel):
    agent_name: str
    agent_class: str
    owner_email: str
    scope_clusters: list[str] = Field(default_factory=list)
    scope_intents: list[str] = Field(default_factory=lambda: ["read"])
    scope_skills: list[str] = Field(default_factory=list)
    ttl_hours: int = Field(default=1, gt=0, le=MAX_PUBLIC_PASSPORT_TTL_HOURS)


class AgentRegisterIn(BaseModel):
    name: str
    agent_class: str
    owner_email: str
    passport_id: str | None = None
    issue_new_passport: bool = False
    ttl_hours: int = Field(default=24, gt=0, le=MAX_PUBLIC_PASSPORT_TTL_HOURS)


class KillSwitchIn(BaseModel):
    enabled: bool


class WatchdogResolveIn(BaseModel):
    resolution_note: str = ""


class ApprovalResolveIn(BaseModel):
    by_user: str
    note: str | None = None


class InternalSearchIn(BaseModel):
    query: str = ""
    mode: SearchMode = "hybrid"
    top_k: int = Field(default=8, ge=1, le=50)
    weights: dict[str, float] | None = None


def datetime_now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _reject_wildcard_passport_scopes(
    scope_clusters: list[str],
    scope_intents: list[str],
    scope_skills: list[str],
) -> None:
    if "*" not in {*scope_clusters, *scope_intents, *scope_skills}:
        return
    if _truthy_env("AXIOM_ALLOW_WILDCARD_PASSPORTS"):
        return
    raise HTTPException(
        status_code=422,
        detail="wildcard passport scopes require AXIOM_ALLOW_WILDCARD_PASSPORTS=1",
    )


def _entity_name(entity: Entity) -> str:
    data = entity.data or {}
    return (
        _text(data.get("title")) or _text(data.get("name")) or _text(data.get("label")) or entity.id
    )


def _is_policy_entity(entity: Entity) -> bool:
    data = entity.data or {}
    haystack = " ".join(
        str(value).lower()
        for value in (
            entity.type,
            entity.cluster_id,
            data.get("title"),
            data.get("name"),
            data.get("category"),
        )
        if value is not None
    )
    return (
        entity.type.lower() in {"policy", "governance"}
        or (entity.cluster_id or "").lower() == "governance"
        or "policy" in haystack
    )


def _receipt_signed(receipt: Receipt) -> bool:
    return bool(receipt.signature)


def _passport_status(payload: dict[str, Any]) -> str:
    if payload.get("revoked_at"):
        return "revoked"
    if payload.get("kill_switch"):
        return "kill_switch"
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, str):
        try:
            if datetime.fromisoformat(expires_at) < datetime.utcnow():
                return "expired"
        except ValueError:
            pass
    return "active"


def _receipt_row(receipt: Receipt) -> dict[str, Any]:
    return {
        **receipt_to_dict(receipt),
        "receipt_id": receipt.id,
        "receipt_type": "agent_action",
        "merkle_root": receipt.this_hash,
        "signed": _receipt_signed(receipt),
        "demo": receipt.demo_flag,
        "timestamp": _iso(receipt.created_at),
    }


def _persist_connector_event(
    session: Session,
    *,
    vendor: str,
    connector_state_id: str | None,
    event_type: str,
    external_id: str | None,
    payload: Any,
    signature_ok: bool,
    received_at: datetime,
    event_timestamp: datetime | None,
) -> bool:
    """Persist one connector webhook event, de-duplicating retries (P1-4 / DEDUP).

    The webhook may be re-delivered by the vendor; the UniqueConstraint on
    (vendor, external_id) is the hard DB-level guarantee. This helper also
    short-circuits a known duplicate (already committed, or already queued in
    the same batch) so a retry is a benign skip rather than an IntegrityError
    that aborts the batch. A missing external id is stored as NULL (SQLite
    treats NULLs as distinct in a UNIQUE index) so null-id events never collide.

    Returns True if a new row was queued, False if it was a benign duplicate.
    """
    normalized_external_id = external_id or None
    # De-duplicate webhook retries on (vendor, external_id). A NULL external id
    # is never treated as a duplicate (NULLs are distinct in the UNIQUE index).
    # The UniqueConstraint on the model is the hard DB-level guarantee; this
    # function additionally short-circuits known duplicates so a retry is a
    # benign skip instead of an IntegrityError that aborts the batch.
    if normalized_external_id is not None:
        # 1) Already committed (e.g. a retry in a separate request).
        existing = session.execute(
            select(ConnectorEventRow.id).where(
                ConnectorEventRow.vendor == vendor,
                ConnectorEventRow.external_id == normalized_external_id,
            )
        ).first()
        if existing is not None:
            return False
        # 2) Already queued earlier in this same (uncommitted) batch. Scanning
        #    session.new avoids forcing an early flush, which would reorder DB
        #    writes relative to the surrounding brain-apply step.
        for pending in session.new:
            if (
                isinstance(pending, ConnectorEventRow)
                and pending.vendor == vendor
                and pending.external_id == normalized_external_id
            ):
                return False
    row = ConnectorEventRow(
        vendor=vendor,
        connector_state_id=connector_state_id,
        event_type=event_type,
        external_id=normalized_external_id,
        payload=payload,
        signature_ok=signature_ok,
        received_at=received_at,
        event_timestamp=event_timestamp,
    )
    session.add(row)
    return True


def _policy_rule_row(rule: PolicyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "description": rule.description,
        "severity": rule.severity,
        "when": rule.when.to_source(),
        "then": {
            "type": rule.then.type,
            "reason": rule.then.reason,
            "guidance": rule.then.guidance,
            "suggested_alternative": rule.then.suggested_alternative,
            "approval_required_role": rule.then.approval_required_role,
            "approval_timeout_seconds": rule.then.approval_timeout_seconds,
        },
        "metadata": rule.metadata,
        "source": rule.source,
    }


SETTINGS_FILE = Path("axiom_studio_settings.json")
log = logging.getLogger("axiom.studio")

load_axiom_env()

MCP_TOOL_NAMES = [
    "axiom_query_brain",
    "axiom_get_entity",
    "axiom_traverse",
    "axiom_walk",
    "axiom_list_sources",
    "axiom_record_action",
    "axiom_check_policy",
    "axiom_request_human_approval",
    "axiom_list_skills",
    "axiom_get_skill",
    "axiom_run_skill",
    "axiom_register_skill",
    "axiom_archive_skill",
]


def _snapshots_enabled() -> bool:
    return os.environ.get("AXIOM_SNAPSHOT_ENABLED", "1").lower() not in {"0", "false", "no", "off"}


def _production_mode() -> bool:
    return os.environ.get("AXIOM_ENV", "").strip().lower() == "production"


def _fail_fast_on_bad_config() -> None:
    """Refuse to start with an unsafe production configuration (P0-3).

    - production without ``AXIOM_API_TOKEN`` would serve fail-open → exit.
    - ``AXIOM_VAULT_KEY`` present but not a valid Fernet key → exit (every
      stored secret would be unreadable and the vault silently locked).
    """
    from axiom.env import vault_status
    from axiom.studio.auth import configured_api_token

    if _production_mode() and configured_api_token() is None:
        raise SystemExit(
            "FATAL: AXIOM_ENV=production but AXIOM_API_TOKEN is not set. "
            "Refusing to start fail-open. Set AXIOM_API_TOKEN (or unset AXIOM_ENV "
            "for local dev)."
        )
    present, error = vault_status()
    if present and error:
        raise SystemExit(
            f"FATAL: AXIOM_VAULT_KEY is present but is not a valid Fernet key: {error}"
        )


def create_app(
    *,
    db_url: str | None = None,
    live: bool = False,
    live_rate: float = 0.125,
    live_pause_after: int | None = None,
    enable_organizer: bool = True,
) -> FastAPI:
    _fail_fast_on_bad_config()
    db_url = db_url or os.environ.get("DATABASE_URL") or "sqlite:///./axiom.db"
    engine = create_engine(db_url, future=True)
    ensure_passports_schema(engine)
    ensure_receipts_schema(engine)
    ensure_agent_registry_schema(engine)
    ensure_cluster_check_runs_schema(engine)
    ensure_snapshots_schema(engine)
    ensure_llm_provider_keys_schema(engine)
    ensure_skills_schema(engine)
    ensure_sources_schema(engine)
    ensure_entity_embeddings_schema(engine)
    ensure_watchdog_alerts_schema(engine)
    ensure_approvals_schema(engine)
    ensure_connectors_schema(engine)
    cast(Table, Secret.__table__).create(bind=engine, checkfirst=True)
    # SkillFile primitive tables — created here so a fresh DB (no migrations)
    # still serves the SkillFile endpoints.
    from axiom.schema.models import SkillFileRow, SkillFileVersionRow

    cast(Table, SkillFileRow.__table__).create(bind=engine, checkfirst=True)
    cast(Table, SkillFileVersionRow.__table__).create(bind=engine, checkfirst=True)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()
    policy_evaluator = get_policy_evaluator(session_local)
    cluster_health_monitor = ClusterHealthMonitor()
    live_source = (
        LiveSyntheticSource(rate_per_second=live_rate, max_events=live_pause_after)
        if live
        else None
    )
    production_mode = _production_mode()
    demo_simulator_enabled = os.environ.get("AXIOM_DEMO_SIMULATOR") == "1" and not production_mode

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.broadcaster = broadcaster
        app.state.SessionLocal = session_local
        app.state.live_source = live_source
        app.state.live_task = None
        app.state.cluster_health_task = None
        app.state.agent_action_task = None
        app.state.warden_task = None
        app.state.watchdog = None
        app.state.snapshot_task = None
        app.state.cluster_check_retention_task = None
        app.state.connector_sync_task = None
        app.state.vault_unlocked = False
        app.state.organizer = None
        app.state.events_per_min = 0.0
        app.state.studio_settings = {}
        app.state.mcp_action_events = []
        app.state.mcp_tool_counts = dict.fromkeys(MCP_TOOL_NAMES, 0)
        app.state.mcp_last_called = dict.fromkeys(MCP_TOOL_NAMES)
        app.state.policy_evaluator = policy_evaluator
        # Seed SkillFiles from skills/library/ on startup (idempotent).
        try:
            from axiom.skills.skill_file_store import seed_from_disk

            with session_local() as seed_session:
                seeded = seed_from_disk(seed_session)
            if seeded:
                log.info("seeded %d skill_file(s) from disk", seeded)
        except Exception as exc:  # noqa: BLE001
            log.exception("skill_file seed failed: %s", exc)
        if SETTINGS_FILE.exists():
            try:
                app.state.studio_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                log.exception("failed to load studio settings; starting with empty dict")
                app.state.studio_settings = {}
        previous_health: dict[str, str] = {}
        last_seq = broadcaster.current_seq
        last_seq_at = asyncio.get_running_loop().time()
        snapshots_enabled = _snapshots_enabled()

        async def cluster_health_loop() -> None:
            nonlocal last_seq, last_seq_at
            while True:
                with session_local() as session:
                    snapshot = cluster_health_monitor.snapshot(session)
                    record_cluster_check_runs(session, snapshot)
                for cluster_id, item in snapshot.items():
                    status = item.status.value
                    if previous_health.get(cluster_id) not in {None, status}:
                        await broadcaster.publish(
                            {
                                "type": "cluster_health_changed",
                                "source_id": None,
                                "persisted_id": cluster_id,
                                "payload": item.to_json(),
                                "timestamp": datetime_now_ms(),
                            }
                        )
                    previous_health[cluster_id] = status
                now = asyncio.get_running_loop().time()
                elapsed = max(now - last_seq_at, 1e-6)
                seq_delta = max(0, broadcaster.current_seq - last_seq)
                app.state.events_per_min = (seq_delta / elapsed) * 60.0
                last_seq = broadcaster.current_seq
                last_seq_at = now
                await asyncio.sleep(15)

        async def snapshot_loop() -> None:
            while True:
                await asyncio.sleep(3600)
                try:
                    with session_local() as session:
                        take_snapshot(session)
                except Exception:  # noqa: BLE001
                    log.exception("metrics snapshot loop iteration failed; will retry")

        async def cluster_check_retention_loop() -> None:
            while True:
                try:
                    with session_local() as session:
                        cleanup_cluster_check_runs(session, retention_limit_from_env())
                except Exception:  # noqa: BLE001
                    log.exception("cluster_check retention sweep failed; will retry")
                await asyncio.sleep(21_600)

        health_task = asyncio.create_task(cluster_health_loop())
        cluster_check_retention_task = asyncio.create_task(cluster_check_retention_loop())
        agent_action_task = (
            asyncio.create_task(emit_demo_agent_actions(broadcaster, session_factory=session_local))
            if demo_simulator_enabled
            else None
        )
        warden_task = (
            asyncio.create_task(emit_demo_warden_insights(broadcaster, session_local))
            if os.environ.get("AXIOM_DEMO_WARDEN") == "1" and not production_mode
            else None
        )
        app.state.cluster_health_task = health_task
        app.state.cluster_check_retention_task = cluster_check_retention_task
        app.state.agent_action_task = agent_action_task
        app.state.warden_task = warden_task

        try:
            with session_local() as session:
                backfill_agent_registry_from_receipts(session)
        except Exception:  # noqa: BLE001
            log.exception("agent registry backfill failed during startup; continuing")

        try:
            with session_local() as session:
                bootstrap_embeddings(session)
        except Exception:  # noqa: BLE001
            log.exception("entity embeddings bootstrap failed during startup; continuing")

        snapshot_task: asyncio.Task[None] | None = None
        if snapshots_enabled:
            try:
                with session_local() as session:
                    snapshot_count = int(
                        session.execute(select(func.count(MetricsSnapshot.id))).scalar_one()
                    )
                    receipt_count = int(
                        session.execute(select(func.count(Receipt.id))).scalar_one()
                    )
                    if snapshot_count == 0 and receipt_count > 0:
                        backfill_snapshots_from_receipts(session)
                    today_id = datetime.utcnow().date().isoformat()
                    if session.get(MetricsSnapshot, today_id) is None:
                        take_snapshot(session)
            except Exception:  # noqa: BLE001
                log.exception("metrics snapshot startup priming failed; continuing")
            snapshot_task = asyncio.create_task(snapshot_loop())
            app.state.snapshot_task = snapshot_task

        organizer: OrganizerAgent | None = None
        if enable_organizer:
            organizer = OrganizerAgent(
                session_factory=session_local,
                broadcaster=broadcaster,
            )
            try:
                await organizer.backfill_once()
            except Exception:  # noqa: BLE001
                # Backfill is best-effort; the loop will retry continuously.
                log.exception("organizer initial backfill failed; loop will retry")
            organizer.start()
            app.state.organizer = organizer

        watchdog = WatchdogAgent(
            session_factory=session_local,
            broadcaster=broadcaster,
        )
        watchdog.start()
        app.state.watchdog = watchdog

        app.state.vault_unlocked = log_vault_startup_status()
        if app.state.vault_unlocked:
            asyncio.create_task(run_initial_sync(session_local, broadcaster))
            app.state.connector_sync_task = asyncio.create_task(
                connector_sync_loop(session_local, broadcaster)
            )
        else:
            app.state.connector_sync_task = None

        if live_source is None:
            try:
                yield
            finally:
                await watchdog.cancel()
                if organizer is not None:
                    await organizer.cancel()
                health_task.cancel()
                if agent_action_task is not None:
                    agent_action_task.cancel()
                cluster_check_retention_task.cancel()
                if warden_task is not None:
                    warden_task.cancel()
                if snapshot_task is not None:
                    snapshot_task.cancel()
                if app.state.connector_sync_task is not None:
                    app.state.connector_sync_task.cancel()
                with suppress(asyncio.CancelledError):
                    await health_task
                if agent_action_task is not None:
                    with suppress(asyncio.CancelledError):
                        await agent_action_task
                with suppress(asyncio.CancelledError):
                    await cluster_check_retention_task
                if warden_task is not None:
                    with suppress(asyncio.CancelledError):
                        await warden_task
                if app.state.connector_sync_task is not None:
                    with suppress(asyncio.CancelledError):
                        await app.state.connector_sync_task
                engine.dispose()
            return

        with session_local() as session:
            pipeline = IngestPipeline(
                source=live_source,
                session=session,
                broadcaster=broadcaster,
            )
            await pipeline.run(since=None)

            async def on_live_event(event: Any) -> None:
                await pipeline._handle(event)  # noqa: SLF001

            callback = cast(Callable[[IngestEvent], None], on_live_event)
            async with live_source.watch(callback):
                app.state.live_task = live_source.task or asyncio.current_task()
                try:
                    yield
                finally:
                    live_source.cancel()
                    await watchdog.cancel()
                    if organizer is not None:
                        await organizer.cancel()
                    health_task.cancel()
                    if agent_action_task is not None:
                        agent_action_task.cancel()
                    cluster_check_retention_task.cancel()
                    if warden_task is not None:
                        warden_task.cancel()
                    if snapshot_task is not None:
                        snapshot_task.cancel()
                    if app.state.connector_sync_task is not None:
                        app.state.connector_sync_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await health_task
                    if agent_action_task is not None:
                        with suppress(asyncio.CancelledError):
                            await agent_action_task
                    with suppress(asyncio.CancelledError):
                        await cluster_check_retention_task
                    if warden_task is not None:
                        with suppress(asyncio.CancelledError):
                            await warden_task
                    if snapshot_task is not None:
                        with suppress(asyncio.CancelledError):
                            await snapshot_task
                    if app.state.connector_sync_task is not None:
                        with suppress(asyncio.CancelledError):
                            await app.state.connector_sync_task
                    engine.dispose()

    app = FastAPI(title="AXIOM Studio API", lifespan=lifespan)
    app.state.policy_evaluator = policy_evaluator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_api_auth(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not auth_required() or is_http_auth_exempt(request.method, request.url.path):
            return await call_next(request)
        if auth_is_misconfigured():
            return JSONResponse(
                {"detail": "API auth is required but AXIOM_API_TOKEN is not configured."},
                status_code=503,
            )
        if not request_is_authenticated(request):
            return JSONResponse(
                {"detail": "Missing or invalid API bearer token."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    app.include_router(vault_router)
    app.include_router(llm_keys_router)
    app.include_router(brain_ask_router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        active_evaluator = getattr(app.state, "policy_evaluator", policy_evaluator)
        policy_mode = "demo" if isinstance(active_evaluator, DemoPolicyEvaluator) else "real"
        return {
            "status": "ok",
            "current_seq": broadcaster.current_seq,
            "live": live_source is not None,
            "events_emitted": live_source.events_emitted if live_source is not None else 0,
            "policy_mode": policy_mode,
            "auth_required": auth_required(),
        }

    @app.get("/api/internal/settings")
    def get_studio_settings() -> dict[str, Any]:
        return {"settings": dict(getattr(app.state, "studio_settings", {}))}

    @app.put("/api/internal/settings")
    def put_studio_settings(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        existing = dict(getattr(app.state, "studio_settings", {}))
        existing.update(payload)
        app.state.studio_settings = existing
        try:
            SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            log.exception("failed to persist studio settings to %s", SETTINGS_FILE)
        return {"settings": existing}

    connector_vendors = {"github", "linear", "slack", "notion", "gmail"}

    def _vault_ref(vendor: str, key_name: str) -> str:
        return f"vault:connector:{vendor}:{key_name}"

    def _is_vault_ref(value: str | None) -> bool:
        return bool(value and value.startswith("vault:connector:"))

    def _secret_key_from_ref(vendor: str, ref: str) -> str | None:
        prefix = f"vault:connector:{vendor}:"
        return ref.removeprefix(prefix) if ref.startswith(prefix) else None

    def _put_connector_secret(session: Any, vendor: str, key_name: str, plaintext: str) -> str:
        delete_secret_with_session(session, f"connector:{vendor}", key_name)
        store_secret_with_session(session, f"connector:{vendor}", key_name, plaintext)
        return _vault_ref(vendor, key_name)

    def _get_connector_secret(
        session: Any,
        vendor: str,
        ref_or_plaintext: str | None,
        env_fallback: str | None = None,
    ) -> str | None:
        if not ref_or_plaintext:
            return env_fallback
        key_name = _secret_key_from_ref(vendor, ref_or_plaintext)
        if key_name is None:
            return ref_or_plaintext
        try:
            return get_secret_with_session(session, f"connector:{vendor}", key_name)
        except SecretNotFound:
            return env_fallback

    def _map_vault_error(exc: Exception) -> HTTPException:
        if isinstance(exc, VaultLocked):
            return HTTPException(
                status_code=503,
                detail="Vault locked. Set AXIOM_VAULT_KEY before storing connector secrets.",
            )
        if isinstance(exc, VaultCorrupt):
            return HTTPException(status_code=500, detail="Vault decryption failed.")
        return HTTPException(status_code=500, detail=str(exc))

    def _connector_config_row_to_config(
        session: Any,
        row: ConnectorConfigRow,
        fallback: ConnectorConfig,
    ) -> ConnectorConfig:
        return ConnectorConfig(
            id=row.id,
            vendor=row.vendor,
            oauth_client_id=row.oauth_client_id,
            oauth_client_secret=_get_connector_secret(
                session,
                row.vendor,
                row.oauth_client_secret,
                fallback.oauth_client_secret,
            ),
            redirect_uri=row.redirect_uri,
            scopes=list(row.scopes or []),
            webhook_secret=_get_connector_secret(
                session,
                row.vendor,
                row.webhook_secret,
                fallback.webhook_secret,
            ),
            workspace_id=row.workspace_id,
            install_state=row.install_state,
        )

    def _saved_connector_config(fallback: ConnectorConfig) -> ConnectorConfig | None:
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorConfigRow).where(ConnectorConfigRow.vendor == fallback.vendor)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            try:
                return _connector_config_row_to_config(session, row, fallback)
            except (VaultLocked, VaultCorrupt) as exc:
                raise _map_vault_error(exc) from exc

    def _with_saved_connector_config(fallback: ConnectorConfig) -> ConnectorConfig:
        return _saved_connector_config(fallback) or fallback

    def _connector_configured(config: ConnectorConfig) -> bool:
        return bool(
            (config.oauth_client_id or "").strip()
            and (config.oauth_client_secret or "").strip()
            and (config.redirect_uri or "").strip()
        )

    def _resolve_connector_redirect_uri(redirect_uri: str, request: Request) -> str:
        uri = redirect_uri.strip()
        if uri.startswith("http://") or uri.startswith("https://"):
            return uri
        base = os.environ.get("AXIOM_PUBLIC_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
        return f"{base}{uri if uri.startswith('/') else f'/{uri}'}"

    def _connector_config_with_resolved_redirect(config: ConnectorConfig, request: Request) -> ConnectorConfig:
        redirect_uri = (config.redirect_uri or "").strip()
        if not redirect_uri:
            return config
        resolved = _resolve_connector_redirect_uri(redirect_uri, request)
        if resolved == config.redirect_uri:
            return config
        return replace(config, redirect_uri=resolved)

    _CONNECTOR_VENDOR_LABELS = {
        "github": "GitHub",
        "linear": "Linear",
        "slack": "Slack",
        "notion": "Notion",
        "gmail": "Gmail",
    }

    def _connector_vendor_label(vendor: str) -> str:
        return _CONNECTOR_VENDOR_LABELS.get(vendor, vendor.replace("_", " ").title())

    def _connector_oauth_callback_html(
        vendor: str,
        *,
        ok: bool,
        detail: str,
        account_label: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> HTMLResponse:
        vendor_label = _connector_vendor_label(vendor)
        safe_detail = html.escape(detail)
        safe_account = html.escape(account_label.strip()) if account_label and account_label.strip() else ""
        message = {
            "type": "axiom:connector-oauth",
            "vendor": vendor,
            "ok": ok,
            "detail": detail,
            "payload": payload or {},
        }
        encoded_message = json.dumps(message).replace("</", "<\\/")
        auto_close_ms = 3000 if ok else 0
        icon_class = "oauth-icon oauth-icon--ok" if ok else "oauth-icon oauth-icon--error"
        icon_glyph = "✓" if ok else "✕"
        heading = "Connected Successfully" if ok else "Connection Failed"
        subtext = (
            f"{html.escape(vendor_label)} has been connected to your Company Brain."
            if ok
            else "We could not complete the connection."
        )
        account_block = (
            f'<p class="oauth-account">Signed in as: <span>{safe_account}</span></p>'
            if ok and safe_account
            else ""
        )
        error_block = (
            f'<p class="oauth-error-detail">{safe_detail}</p>' if not ok else ""
        )
        page_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AXIOM — {html.escape(vendor_label)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      font-family: Inter, "Avenir Next", "Helvetica Neue", sans-serif;
      color: #e8f2ff;
      background: #0a0f1a;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background-color: #0a0f1a;
      background-image:
        radial-gradient(circle at 50% 0%, rgba(0, 212, 170, 0.12), transparent 42%),
        linear-gradient(rgba(25, 83, 137, 0.14) 1px, transparent 1px),
        linear-gradient(90deg, rgba(25, 83, 137, 0.14) 1px, transparent 1px);
      background-size: auto, 32px 32px, 32px 32px;
    }}
    .oauth-shell {{
      width: min(420px, 100%);
      text-align: center;
    }}
    .oauth-brand {{
      margin: 0 0 28px;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.42em;
      text-indent: 0.42em;
      color: #f3f7ff;
      text-shadow: 0 0 24px rgba(0, 212, 170, 0.35);
    }}
    .oauth-card {{
      border: 1px solid rgba(0, 212, 170, 0.28);
      border-radius: 16px;
      padding: 36px 28px 28px;
      background:
        radial-gradient(circle at 100% 0%, rgba(0, 212, 170, 0.08), transparent 40%),
        linear-gradient(180deg, rgba(7, 17, 34, 0.96), rgba(5, 12, 24, 0.98));
      box-shadow:
        0 24px 80px rgba(0, 0, 0, 0.45),
        inset 0 1px 0 rgba(0, 212, 170, 0.12);
    }}
    .oauth-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 72px;
      height: 72px;
      margin: 0 auto 20px;
      border-radius: 50%;
      font-size: 36px;
      font-weight: 700;
      line-height: 1;
      animation: oauth-pop 520ms cubic-bezier(0.22, 1, 0.36, 1) both;
    }}
    .oauth-icon--ok {{
      color: #0a0f1a;
      background: linear-gradient(145deg, #00d4aa, #00a88a);
      box-shadow: 0 0 40px rgba(0, 212, 170, 0.45);
    }}
    .oauth-icon--error {{
      color: #ffe8ea;
      background: linear-gradient(145deg, #ff4f57, #c92a35);
      box-shadow: 0 0 32px rgba(255, 79, 87, 0.35);
    }}
    .oauth-title {{
      margin: 0 0 10px;
      font-size: 22px;
      font-weight: 600;
      color: #f1f7ff;
    }}
    .oauth-subtext {{
      margin: 0;
      font-size: 14px;
      line-height: 1.5;
      color: #94a4ba;
    }}
    .oauth-account {{
      margin: 16px 0 0;
      font-size: 13px;
      color: #7f92ab;
    }}
    .oauth-account span {{
      color: #dce9ff;
      font-weight: 500;
    }}
    .oauth-error-detail {{
      margin: 14px 0 0;
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid rgba(255, 79, 87, 0.35);
      background: rgba(255, 79, 87, 0.1);
      font-size: 13px;
      line-height: 1.45;
      color: #ffc8cc;
      text-align: left;
    }}
    .oauth-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-top: 26px;
      min-width: 180px;
      height: 42px;
      padding: 0 22px;
      border: 1px solid rgba(0, 212, 170, 0.55);
      border-radius: 8px;
      background: rgba(0, 212, 170, 0.14);
      color: #00d4aa;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
    }}
    .oauth-button:hover {{
      background: rgba(0, 212, 170, 0.24);
      border-color: #00d4aa;
      color: #e8fff9;
    }}
    .oauth-footer {{
      margin: 18px 0 0;
      font-size: 12px;
      color: #5f728f;
    }}
    @keyframes oauth-pop {{
      from {{ opacity: 0; transform: scale(0.72); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}
  </style>
</head>
<body>
  <div class="oauth-shell">
    <p class="oauth-brand">AXIOM</p>
    <div class="oauth-card">
      <div class="{icon_class}" aria-hidden="true">{icon_glyph}</div>
      <h1 class="oauth-title">{heading}</h1>
      <p class="oauth-subtext">{subtext}</p>
      {account_block}
      {error_block}
      <button type="button" class="oauth-button" id="oauth-close">Return to AXIOM</button>
      <p class="oauth-footer">You can safely close this window</p>
    </div>
  </div>
  <script>
    (function() {{
      var msg = {encoded_message};
      var autoCloseMs = {auto_close_ms};
      function notifyParent() {{
        try {{
          if (window.opener && !window.opener.closed) {{
            window.opener.postMessage(msg, window.location.origin);
          }}
        }} catch (error) {{}}
      }}
      function closeWindow() {{
        window.close();
      }}
      notifyParent();
      document.getElementById("oauth-close").addEventListener("click", closeWindow);
      if (autoCloseMs > 0) {{
        window.setTimeout(closeWindow, autoCloseMs);
      }}
    }})();
  </script>
</body>
</html>"""
        return HTMLResponse(content=page_html)

    _OAuthCallbackResult = TypeVar("_OAuthCallbackResult", bound=dict[str, Any])

    def _execute_connector_oauth_callback(
        vendor: str,
        connect: Callable[[], _OAuthCallbackResult],
        background_tasks: BackgroundTasks | None = None,
    ) -> HTMLResponse:
        try:
            result = connect()
            if background_tasks is not None:
                background_tasks.add_task(
                    _post_oauth_connector_sync,
                    vendor,
                )
            else:
                schedule_connector_sync_after_oauth(vendor, session_local, broadcaster)
            account_label = str(result.get("account_label") or "").strip() or None
            return _connector_oauth_callback_html(
                vendor,
                ok=True,
                detail=f"{_connector_vendor_label(vendor)} has been connected to your Company Brain.",
                account_label=account_label,
                payload=result,
            )
        except HTTPException as exc:
            detail = str(exc.detail)
            return _connector_oauth_callback_html(vendor, ok=False, detail=detail)
        except Exception as exc:  # noqa: BLE001
            log.exception("%s OAuth callback failed", vendor)
            return _connector_oauth_callback_html(
                vendor,
                ok=False,
                detail=str(exc) or "Authorization failed",
            )

    async def _post_oauth_connector_sync(vendor: str) -> None:
        try:
            with session_local() as session:
                await sync_vendor(session, vendor, broadcaster)
        except LookupError:
            log.warning("Post-OAuth sync skipped — %s not connected", vendor)
        except Exception:
            log.exception("Post-OAuth sync failed for %s", vendor)

    def _require_connector_configured(config: ConnectorConfig, label: str) -> None:
        if not _connector_configured(config):
            raise HTTPException(
                status_code=409,
                detail=f"{label} connector setup required",
            )

    def _require_webhook_configured(config: ConnectorConfig, label: str) -> None:
        if not (config.webhook_secret or "").strip():
            raise HTTPException(
                status_code=409,
                detail=f"{label} webhook setup required",
            )

    def _persist_connector_install_config(config: ConnectorConfig, state: str) -> None:
        with session_local() as session:
            try:
                oauth_client_secret = (
                    _put_connector_secret(
                        session,
                        config.vendor,
                        "oauth_client_secret",
                        config.oauth_client_secret,
                    )
                    if config.oauth_client_secret
                    else None
                )
                webhook_secret = (
                    _put_connector_secret(
                        session,
                        config.vendor,
                        "webhook_secret",
                        config.webhook_secret,
                    )
                    if config.webhook_secret
                    else None
                )
            except (VaultLocked, VaultCorrupt) as exc:
                raise _map_vault_error(exc) from exc
            row = session.get(ConnectorConfigRow, config.id)
            if row is None:
                row = ConnectorConfigRow(
                    id=config.id,
                    vendor=config.vendor,
                    oauth_client_id=config.oauth_client_id,
                    oauth_client_secret=oauth_client_secret,
                    redirect_uri=config.redirect_uri,
                    scopes=config.scopes,
                    webhook_secret=webhook_secret,
                    workspace_id=config.workspace_id,
                    install_state=state,
                )
            else:
                row.install_state = state
                row.oauth_client_id = config.oauth_client_id
                row.oauth_client_secret = oauth_client_secret or row.oauth_client_secret
                row.redirect_uri = config.redirect_uri
                row.scopes = config.scopes
                row.webhook_secret = webhook_secret or row.webhook_secret
                row.workspace_id = config.workspace_id
            session.add(row)
            session.commit()

    def _new_connector_oauth_state() -> str:
        try:
            ttl_seconds = int(os.environ.get("AXIOM_OAUTH_STATE_TTL_SECONDS", "600"))
        except ValueError:
            ttl_seconds = 600
        expires_at_ms = datetime_now_ms() + max(ttl_seconds, 60) * 1000
        return f"{new_id()}.{expires_at_ms}"

    def _connector_oauth_state_expired(state: str) -> bool:
        try:
            expires_at_ms = int(state.rsplit(".", 1)[1])
        except (IndexError, ValueError):
            return True
        return expires_at_ms < datetime_now_ms()

    def _consume_connector_oauth_state(config: ConnectorConfig, state: str) -> None:
        with session_local() as session:
            row = session.get(ConnectorConfigRow, config.id)
            if (
                row is None
                or row.vendor != config.vendor
                or not row.install_state
                or not hmac.compare_digest(row.install_state, state)
                or _connector_oauth_state_expired(row.install_state)
            ):
                raise HTTPException(status_code=400, detail="invalid OAuth state")
            row.install_state = "callback_pending"
            session.add(row)
            session.commit()

    def _put_connector_token(
        session: Any,
        vendor: str,
        state_id: str,
        token_name: str,
        plaintext: str | None,
    ) -> str | None:
        if not plaintext:
            return None
        key_name = f"state:{state_id}:{token_name}"
        return _put_connector_secret(session, vendor, key_name, plaintext)

    def _get_connector_token(
        session: Any,
        row: ConnectorStateRow,
        token_name: str,
    ) -> str | None:
        value = row.access_token if token_name == "access_token" else row.refresh_token
        return _get_connector_secret(session, row.vendor, value)

    def _connector_token_state(session: Any, row: ConnectorStateRow) -> SimpleNamespace:
        return SimpleNamespace(
            access_token=_get_connector_token(session, row, "access_token") or "",
            refresh_token=_get_connector_token(session, row, "refresh_token"),
            token_expires_at=row.token_expires_at,
        )

    def _webhook_graph_payload(
        vendor: str, event: Any
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        payload = event.payload or {}
        entities: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        if vendor == "github":
            repo = payload.get("repository")
            repo_entity = (
                github_normalize_repo(repo) if isinstance(repo, dict) and repo.get("id") else None
            )
            if repo_entity is not None:
                entities.append(repo_entity)
            repo_name = str((repo or {}).get("full_name") or "")
            issue = payload.get("issue")
            if isinstance(issue, dict) and issue.get("id"):
                issue_entity = github_normalize_issue(repo_name, issue)
                entities.append(issue_entity)
                if repo_entity is not None:
                    edges.append(
                        github_repo_to_issue_edge(repo_entity["nick"], issue_entity["nick"])
                    )
            pull_request = payload.get("pull_request")
            if isinstance(pull_request, dict) and pull_request.get("id"):
                pr_entity = github_normalize_pull_request(repo_name, pull_request)
                entities.append(pr_entity)
                if repo_entity is not None:
                    edges.append(github_repo_to_pr_edge(repo_entity["nick"], pr_entity["nick"]))

        elif vendor == "linear":
            data = payload.get("data")
            if isinstance(data, dict) and data.get("id"):
                if str(payload.get("type", "")).lower() == "issue":
                    entities.append(linear_normalize_issue(data))
                elif str(payload.get("type", "")).lower() == "project":
                    entities.append(linear_normalize_project(data))
                elif str(payload.get("type", "")).lower() == "team":
                    entities.append(linear_normalize_team(data))

        elif vendor == "slack":
            slack_event = payload.get("event")
            if isinstance(slack_event, dict):
                event_type = str(slack_event.get("type") or "")
                if event_type == "message" and slack_event.get("channel") and slack_event.get("ts"):
                    entities.append(
                        slack_normalize_message(str(slack_event["channel"]), slack_event)
                    )
                    edges.extend(
                        slack_message_mention_edges(
                            f"message:{slack_event['channel']}:{slack_event['ts']}",
                            str(slack_event.get("text") or ""),
                        )
                    )
                elif event_type in {"channel_created", "channel_rename"}:
                    channel = slack_event.get("channel")
                    if isinstance(channel, dict) and channel.get("id"):
                        entities.append(slack_normalize_channel(channel))

        if not entities:
            entities.append(normalize_to_entity(vendor, event))
            edges.extend(normalize_to_edges(vendor, event))

        return entities, edges

    async def _apply_signed_webhook_events_to_brain(
        session: Any,
        vendor: str,
        events: list[Any],
        signature_ok: bool,
    ) -> int:
        if not signature_ok:
            return 0
        entities: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for event in events:
            event_entities, event_edges = _webhook_graph_payload(vendor, event)
            entities.extend(event_entities)
            edges.extend(event_edges)
        return await apply_to_brain(session, entities, edges, broadcaster=broadcaster)

    def _connector_config_for(vendor: str) -> ConnectorConfig:
        if vendor == "github":
            return github_config()
        if vendor == "linear":
            return linear_config()
        if vendor == "slack":
            return slack_config()
        if vendor == "notion":
            return notion_config()
        if vendor == "gmail":
            return gmail_config()
        raise HTTPException(status_code=404, detail="connector not found")

    @app.put("/api/internal/connectors/{vendor}/config")
    def put_connector_config(
        vendor: str,
        body: Annotated[ConnectorConfigIn, Body()],
        request: Request,
    ) -> dict[str, Any]:
        if vendor not in connector_vendors:
            raise HTTPException(status_code=404, detail="connector not found")
        default = _connector_config_for(vendor)
        redirect_uri = _resolve_connector_redirect_uri(
            (body.redirect_uri or default.redirect_uri or "").strip(),
            request,
        )
        config = ConnectorConfig(
            id=vendor,
            vendor=vendor,
            oauth_client_id=body.oauth_client_id.strip(),
            oauth_client_secret=body.oauth_client_secret.strip(),
            redirect_uri=redirect_uri,
            scopes=default.scopes,
            webhook_secret=(body.webhook_secret or "").strip() or default.webhook_secret,
            workspace_id=(body.workspace_id or "").strip() or default.workspace_id,
        )
        _require_connector_configured(config, vendor.title())
        _persist_connector_install_config(config, "configured")
        return {
            "vendor": vendor,
            "configured": True,
            "redirect_uri": config.redirect_uri,
            "watch_mode": "polling" if vendor == "notion" else "webhook",
        }

    def github_enabled() -> bool:
        return _connector_configured(github_config())

    def github_config() -> ConnectorConfig:
        return _with_saved_connector_config(
            ConnectorConfig(
                id="github",
                vendor="github",
                oauth_client_id=os.environ.get("AXIOM_GITHUB_CLIENT_ID"),
                oauth_client_secret=os.environ.get("AXIOM_GITHUB_CLIENT_SECRET"),
                redirect_uri=os.environ.get(
                    "AXIOM_GITHUB_REDIRECT_URI",
                    "/api/internal/connectors/github/callback",
                ),
                scopes=GITHUB_SCOPES,
                webhook_secret=os.environ.get("AXIOM_GITHUB_WEBHOOK_SECRET"),
                workspace_id=os.environ.get("AXIOM_WORKSPACE_ID"),
            )
        )

    def require_github_enabled() -> None:
        _require_connector_configured(github_config(), "GitHub")

    @app.post("/api/internal/connectors/github/install")
    def post_github_install() -> dict[str, Any]:
        require_github_enabled()
        config = github_config()
        state = _new_connector_oauth_state()
        _persist_connector_install_config(config, state)
        return {"authorize_url": GitHubOAuth(config).authorize_url(state), "state": state}

    @app.get("/api/internal/connectors/github/callback")
    def get_github_callback(
        request: Request,
        code: str,
        state: str,
        background_tasks: BackgroundTasks,
    ) -> HTMLResponse:
        def _connect() -> dict[str, Any]:
            require_github_enabled()
            config = _connector_config_with_resolved_redirect(github_config(), request)
            _consume_connector_oauth_state(config, state)
            oauth_state = GitHubOAuth(config).exchange_code(code)
            with session_local() as session:
                config_row = session.get(ConnectorConfigRow, config.id)
                if config_row is None:
                    config_row = ConnectorConfigRow(
                        id=config.id,
                        vendor="github",
                        oauth_client_id=config.oauth_client_id,
                        oauth_client_secret=_put_connector_secret(
                            session,
                            "github",
                            "oauth_client_secret",
                            config.oauth_client_secret or "",
                        )
                        if config.oauth_client_secret
                        else None,
                        redirect_uri=config.redirect_uri,
                        scopes=config.scopes,
                        webhook_secret=_put_connector_secret(
                            session,
                            "github",
                            "webhook_secret",
                            config.webhook_secret or "",
                        )
                        if config.webhook_secret
                        else None,
                        workspace_id=config.workspace_id,
                        install_state="connected",
                    )
                    session.add(config_row)
                else:
                    config_row.install_state = "connected"
                    session.add(config_row)
                row = ConnectorStateRow(
                    id=oauth_state.id,
                    connector_id=config.id,
                    vendor="github",
                    access_token=_put_connector_token(
                        session,
                        "github",
                        oauth_state.id,
                        "access_token",
                        oauth_state.access_token,
                    )
                    or "",
                    refresh_token=_put_connector_token(
                        session,
                        "github",
                        oauth_state.id,
                        "refresh_token",
                        oauth_state.refresh_token,
                    ),
                    token_expires_at=None,
                    account_id=oauth_state.account_id,
                    account_label=oauth_state.account_label or "GitHub",
                    installed_by=oauth_state.installed_by,
                    status="connected",
                )
                session.add(row)
                session.commit()
            return {"status": "connected", "account_label": oauth_state.account_label or "GitHub"}

        return _execute_connector_oauth_callback("github", _connect, background_tasks)

    @app.post("/api/internal/connectors/github/sync")
    async def post_github_sync() -> dict[str, Any]:
        require_github_enabled()
        try:
            with session_local() as session:
                return await sync_github(session, broadcaster)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/internal/connectors/github/webhook")
    async def post_github_webhook(request: Request) -> dict[str, Any]:
        config = github_config()
        _require_webhook_configured(config, "GitHub")
        body = await request.body()
        headers = dict(request.headers)
        handler = GitHubWebhookHandler(config.webhook_secret or "")
        parsed_request = SimpleNamespace(body=body, headers=headers)
        signature_ok = handler.verify(parsed_request)
        if not signature_ok:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        events = handler.parse(parsed_request)
        with session_local() as session:
            for event in events:
                _persist_connector_event(
                    session,
                    vendor="github",
                    connector_state_id=None,
                    event_type=event.event_type,
                    external_id=event.external_id,
                    payload=event.payload,
                    signature_ok=signature_ok,
                    received_at=datetime.utcnow(),
                    event_timestamp=event.timestamp,
                )
            session.commit()
            ingested = await _apply_signed_webhook_events_to_brain(
                session,
                "github",
                events,
                signature_ok,
            )
        for event in events:
            await broadcaster.publish(
                {
                    "type": "connector_event_received",
                    "source_id": "github",
                    "persisted_id": event.external_id,
                    "timestamp": datetime_now_ms(),
                    "payload": {"vendor": "github", "event_type": event.event_type},
                }
            )
        return {"ok": signature_ok, "events": len(events), "ingested": ingested}

    @app.get("/api/internal/connectors/github/status")
    def get_github_status() -> dict[str, Any]:
        require_github_enabled()
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "github")
                )
                .scalars()
                .first()
            )
        if row is None:
            return {"vendor": "github", "status": "disconnected"}
        return {
            "vendor": "github",
            "status": row.status,
            "account_label": row.account_label,
            "last_sync_at": _iso(row.last_sync_at),
        }

    def linear_enabled() -> bool:
        return _connector_configured(linear_config())

    def linear_config() -> ConnectorConfig:
        return _with_saved_connector_config(
            ConnectorConfig(
                id="linear",
                vendor="linear",
                oauth_client_id=os.environ.get("AXIOM_LINEAR_CLIENT_ID"),
                oauth_client_secret=os.environ.get("AXIOM_LINEAR_CLIENT_SECRET"),
                redirect_uri=os.environ.get(
                    "AXIOM_LINEAR_REDIRECT_URI",
                    "/api/internal/connectors/linear/callback",
                ),
                scopes=LINEAR_SCOPES,
                webhook_secret=os.environ.get("AXIOM_LINEAR_WEBHOOK_SECRET"),
                workspace_id=os.environ.get("AXIOM_WORKSPACE_ID"),
            )
        )

    def require_linear_enabled() -> None:
        _require_connector_configured(linear_config(), "Linear")

    @app.post("/api/internal/connectors/linear/install")
    def post_linear_install() -> dict[str, Any]:
        require_linear_enabled()
        config = linear_config()
        state = _new_connector_oauth_state()
        _persist_connector_install_config(config, state)
        return {"authorize_url": LinearOAuth(config).authorize_url(state), "state": state}

    @app.get("/api/internal/connectors/linear/callback")
    def get_linear_callback(
        request: Request,
        code: str,
        state: str,
        background_tasks: BackgroundTasks,
    ) -> HTMLResponse:
        def _connect() -> dict[str, Any]:
            require_linear_enabled()
            config = _connector_config_with_resolved_redirect(linear_config(), request)
            _consume_connector_oauth_state(config, state)
            oauth_state = LinearOAuth(config).exchange_code(code)
            with session_local() as session:
                config_row = session.get(ConnectorConfigRow, config.id)
                if config_row is None:
                    config_row = ConnectorConfigRow(
                        id=config.id,
                        vendor="linear",
                        oauth_client_id=config.oauth_client_id,
                        oauth_client_secret=_put_connector_secret(
                            session,
                            "linear",
                            "oauth_client_secret",
                            config.oauth_client_secret or "",
                        )
                        if config.oauth_client_secret
                        else None,
                        redirect_uri=config.redirect_uri,
                        scopes=config.scopes,
                        webhook_secret=_put_connector_secret(
                            session,
                            "linear",
                            "webhook_secret",
                            config.webhook_secret or "",
                        )
                        if config.webhook_secret
                        else None,
                        workspace_id=config.workspace_id,
                        install_state="connected",
                    )
                    session.add(config_row)
                else:
                    config_row.install_state = "connected"
                    session.add(config_row)
                row = ConnectorStateRow(
                    id=oauth_state.id,
                    connector_id=config.id,
                    vendor="linear",
                    access_token=_put_connector_token(
                        session,
                        "linear",
                        oauth_state.id,
                        "access_token",
                        oauth_state.access_token,
                    )
                    or "",
                    refresh_token=_put_connector_token(
                        session,
                        "linear",
                        oauth_state.id,
                        "refresh_token",
                        oauth_state.refresh_token,
                    ),
                    token_expires_at=oauth_state.token_expires_at,
                    account_id=oauth_state.account_id,
                    account_label=oauth_state.account_label or "Linear Workspace",
                    installed_by=oauth_state.installed_by,
                    status="connected",
                )
                session.add(row)
                session.commit()
            return {
                "status": "connected",
                "account_label": oauth_state.account_label or "Linear Workspace",
            }

        return _execute_connector_oauth_callback("linear", _connect, background_tasks)

    @app.post("/api/internal/connectors/linear/sync")
    async def post_linear_sync() -> dict[str, Any]:
        require_linear_enabled()
        try:
            with session_local() as session:
                return await sync_linear(session, broadcaster)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/internal/connectors/linear/webhook")
    async def post_linear_webhook(request: Request) -> dict[str, Any]:
        config = linear_config()
        _require_webhook_configured(config, "Linear")
        body = await request.body()
        headers = dict(request.headers)
        handler = LinearWebhookHandler(config.webhook_secret or "")
        parsed_request = SimpleNamespace(body=body, headers=headers)
        signature_ok = handler.verify(parsed_request)
        if not signature_ok:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        events = handler.parse(parsed_request)
        with session_local() as session:
            for event in events:
                _persist_connector_event(
                    session,
                    vendor="linear",
                    connector_state_id=None,
                    event_type=event.event_type,
                    external_id=event.external_id,
                    payload=event.payload,
                    signature_ok=signature_ok,
                    received_at=datetime.utcnow(),
                    event_timestamp=event.timestamp,
                )
            session.commit()
            ingested = await _apply_signed_webhook_events_to_brain(
                session,
                "linear",
                events,
                signature_ok,
            )
        for event in events:
            await broadcaster.publish(
                {
                    "type": "connector_event_received",
                    "source_id": "linear",
                    "persisted_id": event.external_id,
                    "timestamp": datetime_now_ms(),
                    "payload": {"vendor": "linear", "event_type": event.event_type},
                }
            )
        return {"ok": signature_ok, "events": len(events), "ingested": ingested}

    @app.get("/api/internal/connectors/linear/status")
    def get_linear_status() -> dict[str, Any]:
        require_linear_enabled()
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
                )
                .scalars()
                .first()
            )
        if row is None:
            return {"vendor": "linear", "status": "disconnected"}
        return {
            "vendor": "linear",
            "status": row.status,
            "account_label": row.account_label,
            "last_sync_at": _iso(row.last_sync_at),
        }

    def slack_enabled() -> bool:
        return _connector_configured(slack_config())

    def slack_config() -> ConnectorConfig:
        return _with_saved_connector_config(
            ConnectorConfig(
                id="slack",
                vendor="slack",
                oauth_client_id=os.environ.get("AXIOM_SLACK_CLIENT_ID"),
                oauth_client_secret=os.environ.get("AXIOM_SLACK_CLIENT_SECRET"),
                redirect_uri=os.environ.get(
                    "AXIOM_SLACK_REDIRECT_URI",
                    "/api/internal/connectors/slack/callback",
                ),
                scopes=SLACK_BOT_SCOPES,
                webhook_secret=os.environ.get("AXIOM_SLACK_SIGNING_SECRET"),
                workspace_id=os.environ.get("AXIOM_WORKSPACE_ID"),
            )
        )

    def require_slack_enabled() -> None:
        _require_connector_configured(slack_config(), "Slack")

    @app.post("/api/internal/connectors/slack/install")
    def post_slack_install() -> dict[str, Any]:
        require_slack_enabled()
        config = slack_config()
        state = _new_connector_oauth_state()
        _persist_connector_install_config(config, state)
        return {"authorize_url": SlackOAuth(config).authorize_url(state), "state": state}

    @app.get("/api/internal/connectors/slack/callback")
    def get_slack_callback(
        request: Request,
        code: str,
        state: str,
        background_tasks: BackgroundTasks,
    ) -> HTMLResponse:
        def _connect() -> dict[str, Any]:
            require_slack_enabled()
            config = _connector_config_with_resolved_redirect(slack_config(), request)
            _consume_connector_oauth_state(config, state)
            oauth_state = SlackOAuth(config).exchange_code(code)
            with session_local() as session:
                config_row = session.get(ConnectorConfigRow, config.id)
                if config_row is None:
                    config_row = ConnectorConfigRow(
                        id=config.id,
                        vendor="slack",
                        oauth_client_id=config.oauth_client_id,
                        oauth_client_secret=_put_connector_secret(
                            session,
                            "slack",
                            "oauth_client_secret",
                            config.oauth_client_secret or "",
                        )
                        if config.oauth_client_secret
                        else None,
                        redirect_uri=config.redirect_uri,
                        scopes=config.scopes,
                        webhook_secret=_put_connector_secret(
                            session,
                            "slack",
                            "webhook_secret",
                            config.webhook_secret or "",
                        )
                        if config.webhook_secret
                        else None,
                        workspace_id=config.workspace_id,
                        install_state="connected",
                    )
                    session.add(config_row)
                else:
                    config_row.install_state = "connected"
                    session.add(config_row)
                row = ConnectorStateRow(
                    id=oauth_state.id,
                    connector_id=config.id,
                    vendor="slack",
                    access_token=_put_connector_token(
                        session,
                        "slack",
                        oauth_state.id,
                        "access_token",
                        oauth_state.access_token,
                    )
                    or "",
                    refresh_token=_put_connector_token(
                        session,
                        "slack",
                        oauth_state.id,
                        "refresh_token",
                        oauth_state.refresh_token,
                    ),
                    token_expires_at=oauth_state.token_expires_at,
                    account_id=oauth_state.account_id,
                    account_label=oauth_state.account_label or "Slack Workspace",
                    installed_by=oauth_state.installed_by,
                    status="connected",
                )
                session.add(row)
                session.commit()
            return {
                "status": "connected",
                "account_label": oauth_state.account_label or "Slack Workspace",
            }

        return _execute_connector_oauth_callback("slack", _connect, background_tasks)

    @app.post("/api/internal/connectors/slack/sync")
    async def post_slack_sync() -> dict[str, Any]:
        require_slack_enabled()
        try:
            with session_local() as session:
                return await sync_slack(session, broadcaster)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/internal/connectors/slack/webhook", response_model=None)
    async def post_slack_webhook(request: Request) -> dict[str, Any] | PlainTextResponse:
        config = slack_config()
        _require_webhook_configured(config, "Slack")
        body = await request.body()
        headers = dict(request.headers)
        handler = SlackWebhookHandler(config.webhook_secret or "")
        parsed_request = SimpleNamespace(body=body, headers=headers)
        signature_ok = handler.verify(parsed_request)
        challenge = handler.challenge_response(parsed_request)
        if challenge is not None:
            if not signature_ok:
                raise HTTPException(status_code=401, detail="invalid webhook signature")
            return PlainTextResponse(challenge)
        if not signature_ok:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        events = handler.parse(parsed_request)
        with session_local() as session:
            for event in events:
                _persist_connector_event(
                    session,
                    vendor="slack",
                    connector_state_id=None,
                    event_type=event.event_type,
                    external_id=event.external_id,
                    payload=event.payload,
                    signature_ok=signature_ok,
                    received_at=datetime.utcnow(),
                    event_timestamp=event.timestamp,
                )
            session.commit()
            ingested = await _apply_signed_webhook_events_to_brain(
                session,
                "slack",
                events,
                signature_ok,
            )
        for event in events:
            await broadcaster.publish(
                {
                    "type": "connector_event_received",
                    "source_id": "slack",
                    "persisted_id": event.external_id,
                    "timestamp": datetime_now_ms(),
                    "payload": {"vendor": "slack", "event_type": event.event_type},
                }
            )
        return {"ok": signature_ok, "events": len(events), "ingested": ingested}

    @app.get("/api/internal/connectors/slack/status")
    def get_slack_status() -> dict[str, Any]:
        require_slack_enabled()
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "slack")
                )
                .scalars()
                .first()
            )
        if row is None:
            return {"vendor": "slack", "status": "disconnected"}
        return {
            "vendor": "slack",
            "status": row.status,
            "account_label": row.account_label,
            "last_sync_at": _iso(row.last_sync_at),
        }

    def notion_enabled() -> bool:
        return _connector_configured(notion_config())

    def notion_config() -> ConnectorConfig:
        return _with_saved_connector_config(
            ConnectorConfig(
                id="notion",
                vendor="notion",
                oauth_client_id=os.environ.get("AXIOM_NOTION_CLIENT_ID"),
                oauth_client_secret=os.environ.get("AXIOM_NOTION_CLIENT_SECRET"),
                redirect_uri=os.environ.get(
                    "AXIOM_NOTION_REDIRECT_URI",
                    "/api/internal/connectors/notion/callback",
                ),
                workspace_id=os.environ.get("AXIOM_WORKSPACE_ID"),
            )
        )

    def require_notion_enabled() -> None:
        _require_connector_configured(notion_config(), "Notion")

    @app.post("/api/internal/connectors/notion/install")
    def post_notion_install(request: Request) -> dict[str, Any]:
        require_notion_enabled()
        config = _connector_config_with_resolved_redirect(notion_config(), request)
        state = _new_connector_oauth_state()
        _persist_connector_install_config(config, state)
        return {"authorize_url": NotionOAuth(config).authorize_url(state), "state": state}

    @app.get("/api/internal/connectors/notion/callback")
    def get_notion_callback(
        request: Request,
        code: str,
        state: str,
        background_tasks: BackgroundTasks,
    ) -> HTMLResponse:
        def _connect() -> dict[str, Any]:
            require_notion_enabled()
            config = _connector_config_with_resolved_redirect(notion_config(), request)
            _consume_connector_oauth_state(config, state)
            oauth_state = NotionOAuth(config).exchange_code(code)
            with session_local() as session:
                config_row = session.get(ConnectorConfigRow, config.id)
                if config_row is None:
                    config_row = ConnectorConfigRow(
                        id=config.id,
                        vendor="notion",
                        oauth_client_id=config.oauth_client_id,
                        oauth_client_secret=_put_connector_secret(
                            session,
                            "notion",
                            "oauth_client_secret",
                            config.oauth_client_secret or "",
                        )
                        if config.oauth_client_secret
                        else None,
                        redirect_uri=config.redirect_uri,
                        scopes=[],
                        workspace_id=config.workspace_id,
                        install_state="connected",
                    )
                    session.add(config_row)
                else:
                    config_row.install_state = "connected"
                    session.add(config_row)
                row = ConnectorStateRow(
                    id=oauth_state.id,
                    connector_id=config.id,
                    vendor="notion",
                    access_token=_put_connector_token(
                        session,
                        "notion",
                        oauth_state.id,
                        "access_token",
                        oauth_state.access_token,
                    )
                    or "",
                    refresh_token=_put_connector_token(
                        session,
                        "notion",
                        oauth_state.id,
                        "refresh_token",
                        oauth_state.refresh_token,
                    ),
                    token_expires_at=oauth_state.token_expires_at,
                    account_id=oauth_state.account_id,
                    account_label=oauth_state.account_label or "Notion Workspace",
                    installed_by=oauth_state.installed_by,
                    status="connected",
                )
                session.add(row)
                session.commit()
            return {
                "status": "connected",
                "account_label": oauth_state.account_label or "Notion Workspace",
                "watch_mode": "polling",
            }

        return _execute_connector_oauth_callback("notion", _connect, background_tasks)

    @app.post("/api/internal/connectors/notion/sync")
    async def post_notion_sync() -> dict[str, Any]:
        require_notion_enabled()
        try:
            with session_local() as session:
                return await sync_notion(session, broadcaster)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/internal/connectors/notion/poll")
    async def post_notion_poll() -> dict[str, Any]:
        require_notion_enabled()
        with session_local() as session:
            state = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "notion")
                )
                .scalars()
                .first()
            )
            if state is None:
                raise HTTPException(status_code=404, detail="Notion connector not installed")
            events = NotionPoller(state=_connector_token_state(session, state)).poll_once()
            for event in events:
                _persist_connector_event(
                    session,
                    vendor="notion",
                    connector_state_id=state.id,
                    event_type=event.event_type,
                    external_id=event.external_id,
                    payload=event.payload,
                    signature_ok=True,
                    received_at=datetime.utcnow(),
                    event_timestamp=event.timestamp,
                )
            state.last_sync_at = datetime.utcnow()
            session.add(state)
            session.commit()
        for event in events:
            await broadcaster.publish(
                {
                    "type": "connector_event_received",
                    "source_id": "notion",
                    "persisted_id": event.external_id,
                    "timestamp": datetime_now_ms(),
                    "payload": {"vendor": "notion", "event_type": event.event_type},
                }
            )
        return {"status": "ok", "events": len(events), "watch_mode": "polling"}

    @app.get("/api/internal/connectors/notion/status")
    def get_notion_status() -> dict[str, Any]:
        require_notion_enabled()
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "notion")
                )
                .scalars()
                .first()
            )
        if row is None:
            return {"vendor": "notion", "status": "disconnected", "watch_mode": "polling"}
        return {
            "vendor": "notion",
            "status": row.status,
            "account_label": row.account_label,
            "last_sync_at": _iso(row.last_sync_at),
            "watch_mode": "polling",
        }

    def gmail_enabled() -> bool:
        return _connector_configured(gmail_config())

    def gmail_config() -> ConnectorConfig:
        return _with_saved_connector_config(
            ConnectorConfig(
                id="gmail",
                vendor="gmail",
                oauth_client_id=os.environ.get("AXIOM_GMAIL_CLIENT_ID"),
                oauth_client_secret=os.environ.get("AXIOM_GMAIL_CLIENT_SECRET"),
                redirect_uri=os.environ.get(
                    "AXIOM_GMAIL_REDIRECT_URI",
                    "/api/internal/connectors/gmail/callback",
                ),
                scopes=GMAIL_SCOPES,
                workspace_id=os.environ.get("AXIOM_WORKSPACE_ID"),
            )
        )

    def require_gmail_enabled() -> None:
        _require_connector_configured(gmail_config(), "Gmail")

    @app.post("/api/internal/connectors/gmail/install")
    def post_gmail_install() -> dict[str, Any]:
        require_gmail_enabled()
        config = gmail_config()
        state = _new_connector_oauth_state()
        _persist_connector_install_config(config, state)
        return {"authorize_url": GmailOAuth(config).authorize_url(state), "state": state}

    @app.get("/api/internal/connectors/gmail/callback")
    def get_gmail_callback(
        request: Request,
        code: str,
        state: str,
        background_tasks: BackgroundTasks,
    ) -> HTMLResponse:
        def _connect() -> dict[str, Any]:
            require_gmail_enabled()
            config = _connector_config_with_resolved_redirect(gmail_config(), request)
            _consume_connector_oauth_state(config, state)
            oauth_state = GmailOAuth(config).exchange_code(code)
            with session_local() as session:
                config_row = session.get(ConnectorConfigRow, config.id)
                if config_row is None:
                    config_row = ConnectorConfigRow(
                        id=config.id,
                        vendor="gmail",
                        oauth_client_id=config.oauth_client_id,
                        oauth_client_secret=_put_connector_secret(
                            session,
                            "gmail",
                            "oauth_client_secret",
                            config.oauth_client_secret or "",
                        )
                        if config.oauth_client_secret
                        else None,
                        redirect_uri=config.redirect_uri,
                        scopes=config.scopes,
                        workspace_id=config.workspace_id,
                        install_state="connected",
                    )
                    session.add(config_row)
                else:
                    config_row.install_state = "connected"
                    session.add(config_row)
                row = ConnectorStateRow(
                    id=oauth_state.id,
                    connector_id=config.id,
                    vendor="gmail",
                    access_token=_put_connector_token(
                        session,
                        "gmail",
                        oauth_state.id,
                        "access_token",
                        oauth_state.access_token,
                    )
                    or "",
                    refresh_token=_put_connector_token(
                        session,
                        "gmail",
                        oauth_state.id,
                        "refresh_token",
                        oauth_state.refresh_token,
                    ),
                    token_expires_at=oauth_state.token_expires_at,
                    account_id=oauth_state.account_id,
                    account_label=oauth_state.account_label or "Gmail",
                    installed_by=oauth_state.installed_by,
                    status="connected",
                )
                session.add(row)
                session.commit()
            return {"status": "connected", "account_label": oauth_state.account_label or "Gmail"}

        return _execute_connector_oauth_callback("gmail", _connect, background_tasks)

    @app.post("/api/internal/connectors/gmail/sync")
    async def post_gmail_sync() -> dict[str, Any]:
        require_gmail_enabled()
        try:
            with session_local() as session:
                return await sync_gmail(session, broadcaster)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/internal/connectors/gmail/webhook")
    async def post_gmail_webhook(request: Request) -> dict[str, Any]:
        require_gmail_enabled()
        body = await request.body()
        headers = dict(request.headers)
        handler = GmailWebhookHandler()
        parsed_request = SimpleNamespace(body=body, headers=headers)
        signature_ok = handler.verify(parsed_request)
        if not signature_ok:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        events = handler.parse(parsed_request)
        with session_local() as session:
            for event in events:
                _persist_connector_event(
                    session,
                    vendor="gmail",
                    connector_state_id=None,
                    event_type=event.event_type,
                    external_id=event.external_id,
                    payload=event.payload,
                    signature_ok=signature_ok,
                    received_at=datetime.utcnow(),
                    event_timestamp=event.timestamp,
                )
            session.commit()
            ingested = await _apply_signed_webhook_events_to_brain(
                session,
                "gmail",
                events,
                signature_ok,
            )
        for event in events:
            await broadcaster.publish(
                {
                    "type": "connector_event_received",
                    "source_id": "gmail",
                    "persisted_id": event.external_id,
                    "timestamp": datetime_now_ms(),
                    "payload": {"vendor": "gmail", "event_type": event.event_type},
                }
            )
        return {"ok": signature_ok, "events": len(events), "ingested": ingested}

    @app.get("/api/internal/connectors/gmail/status")
    def get_gmail_status() -> dict[str, Any]:
        require_gmail_enabled()
        with session_local() as session:
            row = (
                session.execute(
                    select(ConnectorStateRow).where(ConnectorStateRow.vendor == "gmail")
                )
                .scalars()
                .first()
            )
        if row is None:
            return {"vendor": "gmail", "status": "disconnected"}
        return {
            "vendor": "gmail",
            "status": row.status,
            "account_label": row.account_label,
            "last_sync_at": _iso(row.last_sync_at),
        }

    @app.delete("/api/internal/connectors/{vendor}")
    def delete_connector(vendor: str) -> dict[str, Any]:
        if vendor not in {"github", "linear", "slack", "notion", "gmail"}:
            raise HTTPException(status_code=404, detail="connector not found")
        with session_local() as session:
            rows = (
                session.execute(select(ConnectorStateRow).where(ConnectorStateRow.vendor == vendor))
                .scalars()
                .all()
            )
            for row in rows:
                session.delete(row)
            session.commit()
        return {"status": "disconnected", "vendor": vendor, "revoked": len(rows)}

    def require_connector_enabled(vendor: str) -> None:
        if vendor == "github":
            require_github_enabled()
        elif vendor == "linear":
            require_linear_enabled()
        elif vendor == "slack":
            require_slack_enabled()
        elif vendor == "notion":
            require_notion_enabled()
        elif vendor == "gmail":
            require_gmail_enabled()
        else:
            raise HTTPException(status_code=404, detail="connector not found")

    @app.post("/api/internal/connectors/{vendor}/test")
    def post_connector_test(vendor: str) -> dict[str, Any]:
        require_connector_enabled(vendor)
        with session_local() as session:
            row = (
                session.execute(select(ConnectorStateRow).where(ConnectorStateRow.vendor == vendor))
                .scalars()
                .first()
            )
        return {
            "vendor": vendor,
            "ok": row is not None and row.status == "connected",
            "status": row.status if row is not None else "disconnected",
        }

    @app.get("/api/internal/connectors/{vendor}/events")
    def get_connector_events(vendor: str) -> dict[str, Any]:
        if vendor not in {"github", "linear", "slack", "notion", "gmail"}:
            raise HTTPException(status_code=404, detail="connector not found")
        with session_local() as session:
            rows = (
                session.execute(
                    select(ConnectorEventRow)
                    .where(ConnectorEventRow.vendor == vendor)
                    .order_by(desc(ConnectorEventRow.received_at))
                    .limit(50)
                )
                .scalars()
                .all()
            )
        return {
            "events": [
                {
                    "vendor": row.vendor,
                    "event_type": row.event_type,
                    "external_id": row.external_id,
                    "received_at": _iso(row.received_at),
                    "signature_ok": row.signature_ok,
                    "payload": row.payload,
                }
                for row in rows
            ]
        }

    @app.post("/api/internal/connectors/sync-all")
    async def post_connectors_sync_all() -> dict[str, Any]:
        return await sync_all_connected_connectors(session_local, broadcaster)

    @app.get("/api/internal/connectors/status")
    def get_connectors_status() -> dict[str, Any]:
        installed = {row["vendor"]: row for row in list_connectors(session_local)}
        vendors = ["github", "linear", "slack", "notion", "gmail"]
        now = datetime.utcnow()
        event_cutoff = now - timedelta(hours=24)
        receipt_cutoff = now - timedelta(days=7)
        metrics: dict[str, dict[str, Any]] = {}
        configured: dict[str, bool] = {}
        with session_local() as session:
            config_rows = {
                row.vendor: _connector_config_row_to_config(
                    session,
                    row,
                    ConnectorConfig(id=row.id, vendor=row.vendor),
                )
                for row in session.execute(select(ConnectorConfigRow)).scalars().all()
            }
            for vendor in vendors:
                entities_ingested = session.execute(
                    select(func.count(Entity.id)).where(Entity.source_id.startswith(f"{vendor}:"))
                ).scalar_one()
                events_24h = session.execute(
                    select(func.count(ConnectorEventRow.id)).where(
                        ConnectorEventRow.vendor == vendor,
                        ConnectorEventRow.received_at >= event_cutoff,
                    )
                ).scalar_one()
                writes_blocked = session.execute(
                    select(func.count(Receipt.id)).where(
                        Receipt.agent_name == f"connector:{vendor}",
                        Receipt.decision != "allow",
                        Receipt.created_at >= receipt_cutoff,
                    )
                ).scalar_one()
                metrics[vendor] = {
                    "entities_ingested": int(entities_ingested or 0),
                    "events_24h": int(events_24h or 0),
                    "writes_blocked_week": int(writes_blocked or 0),
                }
                configured[vendor] = _connector_configured(
                    config_rows.get(vendor) or _connector_config_for(vendor)
                )
        return {
            "connectors": [
                {
                    "vendor": vendor,
                    "status": installed.get(vendor, {}).get("status", "disconnected"),
                    "account_label": installed.get(vendor, {}).get("account_label"),
                    "last_sync_at": installed.get(vendor, {}).get("last_sync_at"),
                    "configured": configured[vendor],
                    **metrics[vendor],
                    "watch_mode": "polling" if vendor == "notion" else "webhook",
                }
                for vendor in vendors
            ]
        }

    @app.get("/api/internal/agent-registry")
    def get_agent_registry(
        days: int = Query(30, ge=1, le=365),
        type: Annotated[AgentType | None, Query()] = None,  # noqa: A002
    ) -> dict[str, Any]:
        with session_local() as session:
            rows = get_agents(session, days=days, agent_type=type)
        passports = list_passports(session_local, active_only=False)
        passports_by_agent: dict[str, AgentPassport] = {}
        for passport in passports:
            existing = passports_by_agent.get(passport.agent_name)
            if existing is None or passport.issued_at > existing.issued_at:
                passports_by_agent[passport.agent_name] = passport
        enriched = []
        for row in rows:
            payload = agent_registry_row(row)
            matched_passport = passports_by_agent.get(row.agent_name)
            if matched_passport is not None:
                passport_payload = passport_to_dict(matched_passport)
                payload.update(
                    {
                        "name": row.agent_name,
                        "agent_class": matched_passport.agent_class,
                        "owner_email": matched_passport.owner_email,
                        "passport_id": matched_passport.passport_id,
                        "passport_status": _passport_status(passport_payload),
                    }
                )
            else:
                payload.update(
                    {
                        "name": row.agent_name,
                        "agent_class": "unknown",
                        "owner_email": None,
                        "passport_id": None,
                        "passport_status": "missing",
                    }
                )
            enriched.append(payload)
        return {
            "agents": enriched,
            "range_days": days,
            "type": type,
        }

    @app.post("/api/internal/agent-registry")
    async def post_agent_registry(body: Annotated[AgentRegisterIn, Body()]) -> dict[str, Any]:
        name = body.name.strip()
        agent_class = body.agent_class.strip()
        owner_email = body.owner_email.strip()
        if not name or not agent_class or not owner_email:
            raise HTTPException(status_code=422, detail="name, class, and owner_email are required")

        issued_token: str | None = None
        passport_payload: dict[str, Any] | None = None
        if body.issue_new_passport or not body.passport_id:
            try:
                row, issued_token = issue_passport(
                    session_local,
                    agent_name=name,
                    agent_class=agent_class,
                    owner_email=owner_email,
                    scope_clusters=["external_mcp"],
                    scope_intents=["read"],
                    scope_skills=[],
                    ttl_hours=body.ttl_hours,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            passport_payload = passport_to_dict(row)
            await publish_passport_event("passport_issued", passport_payload, row.passport_id)
        else:
            try:
                passport_payload = passport_to_dict(get_passport(session_local, body.passport_id))
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="passport not found") from exc

        with session_local() as session:
            registry = session.get(AgentRegistry, name)
            now = datetime.utcnow()
            if registry is None:
                registry = AgentRegistry(
                    agent_name=name,
                    first_seen=now,
                    last_seen=now,
                    agent_type="external_mcp",
                    demo_flag=False,
                )
            registry.last_seen = now
            registry.demo_flag = False
            session.add(registry)
            session.commit()
            session.refresh(registry)
            payload = agent_registry_row(registry)
        payload.update(
            {
                "name": name,
                "agent_class": passport_payload.get("agent_class", agent_class),
                "owner_email": passport_payload.get("owner_email", owner_email),
                "passport_id": passport_payload.get("passport_id"),
                "passport_status": _passport_status(passport_payload),
                "bearer_token": issued_token,
            }
        )
        return payload

    @app.get("/api/internal/agents/activity")
    def list_agent_activity(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        """Unified runtime feed: skill runs + MCP tool calls + connector syncs.

        Replaces the watchdog-receipts feed at /agents/activity. Surfaces zero
        governance content; watchdog-derived tool calls are excluded. Returns a
        single timeline sorted newest-first. Missing/empty sources degrade
        silently so a partially-connected brain still renders.
        """
        from axiom.schema.models import Action, ConnectorStateRow, Skill, SkillRun

        items: list[dict[str, Any]] = []

        with session_local() as session:
            # Source 1: skill runs (LLM-call skills produced by the skills runner).
            try:
                skill_runs = session.execute(
                    select(SkillRun, Skill.name)
                    .join(Skill, Skill.id == SkillRun.skill_id)
                    .order_by(desc(SkillRun.run_at))
                    .limit(limit)
                ).all()
                for run, skill_name in skill_runs:
                    items.append(
                        {
                            "kind": "skill_run",
                            "id": run.id,
                            "title": f"Skill ran: {skill_name}",
                            "status": run.status or "completed",
                            "duration_ms": run.duration_ms,
                            "agent_name": run.agent_name,
                            "at": run.run_at.isoformat() if run.run_at else None,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("activity: skill_run source failed: %s", exc)

            # Source 2: MCP tool calls (the actions ledger); watchdog rows excluded.
            try:
                actions = (
                    session.execute(
                        select(Action).order_by(desc(Action.created_at)).limit(limit)
                    )
                    .scalars()
                    .all()
                )
                for action in actions:
                    tool = action.tool or "tool"
                    if "watchdog" in tool.lower():
                        continue
                    items.append(
                        {
                            "kind": "mcp_tool_call",
                            "id": action.id,
                            "title": f"Tool call: {tool}",
                            "status": "completed",
                            "agent_name": action.agent_id,
                            "at": action.created_at.isoformat() if action.created_at else None,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("activity: mcp_tool_call source failed: %s", exc)

            # Source 3: connector sync events.
            try:
                connector_rows = (
                    session.execute(
                        select(ConnectorStateRow)
                        .where(ConnectorStateRow.last_sync_at.is_not(None))
                        .order_by(desc(ConnectorStateRow.last_sync_at))
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
                for row in connector_rows:
                    items.append(
                        {
                            "kind": "connector_sync",
                            "id": row.id,
                            "title": f"Connector synced: {row.vendor}",
                            "status": row.status or "synced",
                            "agent_name": None,
                            "at": row.last_sync_at.isoformat() if row.last_sync_at else None,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("activity: connector_sync source failed: %s", exc)

        # Newest first; rows without a timestamp sort to the end.
        items.sort(key=lambda item: item.get("at") or "", reverse=True)
        return {"items": items[:limit]}

    @app.get("/api/internal/mcp-stats")
    def get_mcp_stats() -> dict[str, Any]:
        now_ms = datetime_now_ms()
        one_hour_ago = now_ms - 3600_000
        raw_events = list(getattr(app.state, "mcp_action_events", []))
        events = [event for event in raw_events if int(event.get("timestamp", 0)) >= one_hour_ago]
        active_agents = sorted(
            {
                str(event.get("agent_name", "")).strip()
                for event in events
                if event.get("agent_name")
            }
        )
        one_hour_ago_dt = datetime.utcnow() - timedelta(hours=1)
        with session_local() as session:
            observed_agents = [
                row.agent_name
                for row in session.execute(
                    select(AgentRegistry)
                    .where(AgentRegistry.last_seen >= one_hour_ago_dt)
                    .order_by(desc(AgentRegistry.last_seen), AgentRegistry.agent_name)
                ).scalars()
            ]
        return {
            "tools": [
                {
                    "name": name,
                    "calls": int(getattr(app.state, "mcp_tool_counts", {}).get(name, 0)),
                    "last_called": getattr(app.state, "mcp_last_called", {}).get(name),
                }
                for name in MCP_TOOL_NAMES
            ],
            "connected_clients": len(active_agents),
            "active_agents": active_agents,
            "observed_agents": observed_agents,
            "last_tool_call": max((event.get("timestamp") for event in raw_events), default=None),
            "recent_actions": sorted(
                events, key=lambda item: int(item.get("timestamp", 0)), reverse=True
            )[:20],
        }

    async def publish_passport_event(
        event_type: str, payload: dict[str, Any], persisted_id: str
    ) -> None:
        await broadcaster.publish(
            {
                "type": event_type,
                "source_id": None,
                "persisted_id": persisted_id,
                "timestamp": datetime_now_ms(),
                "payload": payload,
            }
        )

    @app.post("/api/internal/passports")
    async def post_internal_passport(body: Annotated[PassportIn, Body()]) -> dict[str, Any]:
        _reject_wildcard_passport_scopes(
            body.scope_clusters,
            body.scope_intents,
            body.scope_skills,
        )
        try:
            row, token = issue_passport(
                session_local,
                agent_name=body.agent_name,
                agent_class=body.agent_class,
                owner_email=body.owner_email,
                scope_clusters=body.scope_clusters,
                scope_intents=body.scope_intents,
                scope_skills=body.scope_skills,
                ttl_hours=body.ttl_hours,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = passport_to_dict(row)
        await publish_passport_event("passport_issued", payload, row.passport_id)
        return {**payload, "bearer_token": token}

    @app.get("/api/internal/passports")
    def get_internal_passports(active_only: bool = True) -> dict[str, Any]:
        rows = list_passports(session_local, active_only=active_only)
        return {"passports": [passport_to_dict(row) for row in rows]}

    @app.get("/api/internal/passports/{passport_id}")
    def get_internal_passport(passport_id: str) -> dict[str, Any]:
        try:
            return passport_to_dict(get_passport(session_local, passport_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="passport not found") from exc

    @app.delete("/api/internal/passports/{passport_id}")
    async def delete_internal_passport(
        passport_id: str, reason: str | None = None
    ) -> dict[str, Any]:
        try:
            row = revoke_passport(session_local, passport_id, reason=reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="passport not found") from exc
        payload = passport_to_dict(row)
        await publish_passport_event("passport_revoked", payload, row.passport_id)
        return payload

    @app.post("/api/internal/passports/{passport_id}/kill-switch")
    async def post_internal_passport_kill_switch(
        passport_id: str,
        body: Annotated[KillSwitchIn, Body()],
    ) -> dict[str, Any]:
        try:
            row = toggle_kill_switch(session_local, passport_id, body.enabled)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="passport not found") from exc
        payload = passport_to_dict(row)
        await publish_passport_event("passport_kill_switch_toggled", payload, row.passport_id)
        return payload

    @app.get("/api/internal/metrics-snapshots")
    def get_metrics_snapshots(
        days: int = Query(30, ge=1, le=365),
        metric: str | None = None,
    ) -> dict[str, Any]:
        if metric is not None and metric != "brain_health":
            raise HTTPException(status_code=400, detail="unsupported metric")
        with session_local() as session:
            if _snapshots_enabled():
                try:
                    take_snapshot(session)
                except Exception:  # noqa: BLE001
                    log.exception("on-demand metric snapshot failed; serving cached rows")
            rows = get_snapshots(session, days=days)
        if metric == "brain_health":
            rows = rows[-36:]

        payload = {
            "snapshots": [
                {
                    "date": row.snapshot_date.isoformat(),
                    "entity_count": row.entity_count,
                    "edge_count": row.edge_count,
                    "receipt_count": row.receipt_count,
                    "allow_count": row.allow_count,
                    "correct_count": row.correct_count,
                    "deny_count": row.deny_count,
                    "agent_count": row.agent_count,
                    "brain_health_score": row.brain_health_score,
                    "created_at": _iso(row.created_at),
                }
                for row in rows
            ],
            "range_days": days,
        }
        if metric == "brain_health":
            payload["metric"] = "brain_health"
            payload["timeseries"] = [
                {
                    "date": row.snapshot_date.isoformat(),
                    "value": row.brain_health_score,
                }
                for row in rows
            ]
        return payload

    @app.get("/api/internal/cluster-checks")
    def get_internal_cluster_checks(
        cluster: str | None = None,
        severity: str | None = None,
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict[str, Any]:
        with session_local() as session:
            rows = get_cluster_check_runs(
                session,
                cluster=cluster,
                severity=severity,
                limit=limit,
            )
            count_query = select(func.count(ClusterCheckRun.id))
            if cluster:
                count_query = count_query.where(ClusterCheckRun.cluster_id == cluster)
            if severity:
                count_query = count_query.where(ClusterCheckRun.severity == severity)
            total = int(session.execute(count_query).scalar_one())
        return {
            "checks": [cluster_check_run_row(row) for row in rows],
            "total_count": total,
            "cluster": cluster,
            "severity": severity,
        }

    @app.get("/api/internal/cluster-checks/summary")
    def get_internal_cluster_checks_summary() -> dict[str, Any]:
        with session_local() as session:
            summary = summarize_cluster_check_runs(session)
        return {
            "clusters": summary,
            "window_hours": 24,
        }

    async def publish_watchdog_event(
        event_type: str,
        payload: dict[str, Any],
        persisted_id: str,
    ) -> None:
        await broadcaster.publish(
            {
                "type": event_type,
                "source_id": None,
                "persisted_id": persisted_id,
                "timestamp": datetime_now_ms(),
                "payload": payload,
            }
        )

    @app.get("/api/internal/watchdog/alerts")
    def get_internal_watchdog_alerts(
        status: str = Query("open"),
        cluster_id: str | None = None,
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            with session_local() as session:
                rows = list_open_alerts(
                    session,
                    status=status,
                    cluster_id=cluster_id,
                    limit=limit,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"alerts": [alert_to_dict(row) for row in rows]}

    @app.post("/api/internal/watchdog/alerts/{alert_id}/acknowledge")
    async def post_internal_watchdog_acknowledge(alert_id: str) -> dict[str, Any]:
        try:
            with session_local() as session:
                payload = alert_to_dict(acknowledge_alert(session, alert_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="watchdog alert not found") from exc
        await publish_watchdog_event("watchdog_alert_acknowledged", payload, alert_id)
        return payload

    @app.post("/api/internal/watchdog/alerts/{alert_id}/resolve")
    async def post_internal_watchdog_resolve(
        alert_id: str,
        body: Annotated[WatchdogResolveIn, Body()],
    ) -> dict[str, Any]:
        try:
            with session_local() as session:
                payload = alert_to_dict(
                    resolve_alert(
                        session,
                        alert_id,
                        resolved_by="studio",
                        resolution_note=body.resolution_note,
                    )
                )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="watchdog alert not found") from exc
        await publish_watchdog_event("watchdog_alert_resolved", payload, alert_id)
        return payload

    @app.get("/api/internal/policies")
    def get_internal_policies(source: str = Query("all")) -> dict[str, Any]:
        evaluator = app.state.policy_evaluator
        rules = list(getattr(evaluator, "rules", []))
        if source != "all":
            rules = [rule for rule in rules if rule.metadata.get("source") == source]
        return {
            "rules": [_policy_rule_row(rule) for rule in rules],
            "count": len(rules),
        }

    @app.post("/api/internal/policies/reload")
    def post_internal_policies_reload() -> dict[str, Any]:
        rules = reload_policies()
        app.state.policy_evaluator = get_policy_evaluator(session_local)
        active_rules = list(getattr(app.state.policy_evaluator, "rules", rules))
        return {
            "rules": [_policy_rule_row(rule) for rule in active_rules],
            "count": len(active_rules),
        }

    @app.get("/api/internal/policies/active")
    def get_internal_active_policies(entity_id: str) -> dict[str, Any]:
        with session_local() as session:
            entity = session.get(Entity, entity_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="entity not found")
        passport = SimpleNamespace(
            passport_id="policy_probe",
            agent_name="policy_probe",
            scope_clusters=["*"],
            scope_intents=["*"],
            scope_skills=["*"],
            kill_switch=False,
            revoked_at=None,
            expires_at=datetime(2099, 1, 1),
        )
        action = ActionRequest(
            agent_name="policy_probe",
            intent="write",
            target_entity_id=entity_id,
            proposed_action="active policy probe",
            idempotency_key=None,
            payload={},
        )
        rows: list[dict[str, Any]] = []
        for rule in getattr(app.state.policy_evaluator, "rules", []):
            decision = RealPolicyEvaluator([rule], session_local).evaluate(action, passport, entity)
            if decision.policy_id == rule.rule_id:
                rows.append({**_policy_rule_row(rule), "mode": decision.mode})
        return {"rules": rows, "count": len(rows)}

    @app.get("/api/internal/policies/{rule_id}")
    def get_internal_policy(rule_id: str) -> dict[str, Any]:
        evaluator = app.state.policy_evaluator
        for rule in getattr(evaluator, "rules", []):
            if rule.rule_id == rule_id:
                return _policy_rule_row(rule)
        raise HTTPException(status_code=404, detail="policy rule not found")

    async def publish_approval_event(event_type: str, payload: dict[str, Any]) -> None:
        await broadcaster.publish(
            {
                "type": event_type,
                "source_id": None,
                "persisted_id": payload.get("id"),
                "timestamp": datetime_now_ms(),
                "payload": payload,
            }
        )

    @app.get("/api/internal/approvals")
    def get_internal_approvals(
        status: str = Query("pending"),
        role: str | None = None,
    ) -> dict[str, Any]:
        rows = list_pending_approvals(session_local, filter_by_role=role, status=status)
        return {"approvals": [approval_to_dict(row) for row in rows], "count": len(rows)}

    @app.get("/api/internal/approvals/{approval_id}")
    def get_internal_approval(approval_id: str) -> dict[str, Any]:
        try:
            return approval_to_dict(get_approval(session_local, approval_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc

    @app.post("/api/internal/approvals/{approval_id}/approve")
    async def post_internal_approval_approve(
        approval_id: str,
        body: Annotated[ApprovalResolveIn, Body()],
    ) -> dict[str, Any]:
        if not body.by_user:
            raise HTTPException(status_code=422, detail="by_user is required")
        try:
            payload = approval_to_dict(
                approve_request(session_local, approval_id, by_user=body.by_user, note=body.note)
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await publish_approval_event("approval_approved", payload)
        return payload

    @app.post("/api/internal/approvals/{approval_id}/deny")
    async def post_internal_approval_deny(
        approval_id: str,
        body: Annotated[ApprovalResolveIn, Body()],
    ) -> dict[str, Any]:
        if not body.by_user or not body.note:
            raise HTTPException(status_code=422, detail="by_user and note are required")
        try:
            payload = approval_to_dict(
                deny_request(session_local, approval_id, by_user=body.by_user, note=body.note)
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await publish_approval_event("approval_denied", payload)
        return payload

    @app.post("/api/internal/approvals/expire")
    async def post_internal_approvals_expire() -> dict[str, Any]:
        rows = expire_old_requests(session_local)
        for row in rows:
            await publish_approval_event("approval_expired", approval_to_dict(row))
        return {"approvals": [approval_to_dict(row) for row in rows], "count": len(rows)}

    async def publish_skill_event(
        event_type: str,
        payload: dict[str, Any],
        persisted_id: str | None = None,
    ) -> None:
        await broadcaster.publish(
            {
                "type": event_type,
                "source_id": None,
                "persisted_id": persisted_id,
                "timestamp": datetime_now_ms(),
                "payload": payload,
            }
        )

    def _raise_skill_error(exc: Exception) -> NoReturn:
        if isinstance(exc, SkillNotFound):
            raise HTTPException(status_code=404, detail="skill not found") from exc
        if isinstance(exc, SkillManifestError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/internal/skills")
    def get_internal_skills(
        status: str | None = None,
        intent: str | None = None,
        trigger_type: str | None = None,
    ) -> dict[str, Any]:
        try:
            with session_local() as session:
                rows = list_skills_with_session(
                    session,
                    status=status,
                    intent=intent,
                    trigger_type=trigger_type,
                )
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        return {"skills": [skill_to_dict(row) for row in rows]}

    @app.get("/api/internal/skills/{skill_id}")
    def get_internal_skill(skill_id: str) -> dict[str, Any]:
        try:
            with session_local() as session:
                row = get_skill_with_session(session, skill_id)
                return skill_to_dict(row)
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)

    @app.get("/api/internal/skills/{skill_id}/md", response_class=PlainTextResponse)
    def get_internal_skill_md(skill_id: str) -> PlainTextResponse:
        try:
            with session_local() as session:
                row = get_skill_with_session(session, skill_id)
                return PlainTextResponse(
                    serialize_skill_md(row),
                    media_type="text/markdown; charset=utf-8",
                )
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)

    @app.get("/api/internal/skills/{skill_id}/runs")
    def get_internal_skill_runs(skill_id: str) -> dict[str, Any]:
        try:
            with session_local() as session:
                rows = list_skill_runs_with_session(session, skill_id, limit=50)
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        return {"runs": [skill_run_to_dict(row) for row in rows]}

    @app.post("/api/internal/skills")
    async def post_internal_skill(body: Annotated[SkillIn, Body()]) -> dict[str, Any]:
        try:
            with session_local() as session:
                row = register_skill_with_session(
                    session,
                    name=body.name,
                    description=body.description,
                    intent=body.intent,
                    prompt_template=body.prompt_template,
                    llm_provider=body.llm_provider,
                    llm_model=body.llm_model,
                    output_schema=body.output_schema,
                    trigger_config=body.trigger_config,
                    trigger_type=body.trigger_type,
                    created_by=body.created_by,
                )
                payload = skill_to_dict(row)
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        await publish_skill_event("skill_registered", {"skill": payload}, payload["id"])
        return payload

    @app.post("/api/internal/skills/upload-md")
    async def post_internal_skill_upload_md(request: Request) -> dict[str, Any]:
        try:
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                form = await request.form()
                file = form.get("file")
                if file is None or not hasattr(file, "read"):
                    raise SkillManifestError("line 1: multipart upload requires file=SKILL.md")
                raw = await file.read()
                content = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            else:
                body = SkillMdIn.model_validate(await request.json())
                content = body.content
            manifest = parse_skill_md(content)
            with session_local() as session:
                row = register_skill_with_session(
                    session,
                    name=manifest.name,
                    description=manifest.description,
                    intent=manifest.intent,
                    prompt_template=manifest.prompt_template,
                    llm_provider=manifest.llm_provider,
                    llm_model=manifest.llm_model,
                    output_schema=manifest.output_schema,
                    trigger_config={
                        **manifest.trigger_config,
                        "scope_clusters": manifest.scope_clusters,
                    },
                    trigger_type=manifest.trigger_type,
                    created_by="skill_md_upload",
                )
                payload = skill_to_dict(row)
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        await publish_skill_event("skill_registered", {"skill": payload}, payload["id"])
        return payload

    @app.post("/api/internal/skills/compile-from-processes")
    async def post_internal_skills_compile_from_processes(
        body: Annotated[CompileSkillsIn | None, Body()] = None,
    ) -> dict[str, Any]:
        body = body or CompileSkillsIn()
        try:
            with session_local() as session:
                rows = compile_skills_from_processes(
                    session,
                    dry_run=body.dry_run,
                    process_ids=body.process_ids,
                )
                if body.dry_run:
                    manifests = cast(list[SkillManifest], rows)
                    compiled = [manifest_to_dict(row) for row in manifests]
                else:
                    skills = cast(list[Skill], rows)
                    compiled = [skill_to_dict(row) for row in skills]
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        if not body.dry_run:
            for payload in compiled:
                await publish_skill_event("skill_compiled", {"skill": payload}, str(payload["id"]))
        return {"compiled": compiled, "dry_run": body.dry_run, "count": len(compiled)}

    @app.post("/api/internal/skills/{skill_id}/activate")
    def post_internal_skill_activate(skill_id: str) -> dict[str, Any]:
        try:
            with session_local() as session:
                return skill_to_dict(activate_skill_with_session(session, skill_id))
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)

    @app.post("/api/internal/skills/{skill_id}/run")
    def post_internal_skill_run(
        skill_id: str,
        body: Annotated[SkillRunIn, Body()],
    ) -> dict[str, Any]:
        def publish_sync(event_type: str, payload: dict[str, Any]) -> None:
            import anyio

            anyio.from_thread.run(publish_skill_event, event_type, payload, skill_id)

        try:
            return run_skill(
                skill_id,
                body.input_payload,
                body.agent_name,
                session_factory=session_local,
                event_callback=publish_sync,
                idempotency_key=body.idempotency_key,
                policy_evaluator=app.state.policy_evaluator,
            )
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)

    @app.post("/api/internal/skills/{skill_id}/archive")
    async def post_internal_skill_archive(skill_id: str) -> dict[str, Any]:
        try:
            with session_local() as session:
                row = archive_skill_with_session(session, skill_id)
                payload = skill_to_dict(row)
        except Exception as exc:  # noqa: BLE001
            _raise_skill_error(exc)
        await publish_skill_event("skill_archived", {"skill": payload}, skill_id)
        return payload

    # ── SkillFile endpoints (executable workflow YAML) ────────────────────
    # Distinct from /api/internal/skills above (the LLM-call skills). These
    # serve the SkillFile primitive: editable YAML workflows + test runs.

    @app.get("/api/internal/skill-files")
    def list_skill_files_endpoint() -> dict[str, Any]:
        from axiom.skills.skill_file_store import list_skill_files

        with session_local() as session:
            items = list_skill_files(session)
        return {
            "skill_files": [
                {
                    "name": sf.name,
                    "description": sf.description,
                    "current_version": sf.current_version,
                    "validation_status": sf.validation_status,
                    "updated_at": sf.updated_at,
                }
                for sf in items
            ]
        }

    @app.get("/api/internal/skill-files/{name}")
    def get_skill_file_endpoint(name: str) -> dict[str, Any]:
        from axiom.skills.skill_file_store import get_skill_file

        with session_local() as session:
            sf = get_skill_file(session, name)
        if sf is None:
            raise HTTPException(status_code=404, detail=f"skill file not found: {name}")
        return {
            "name": sf.name,
            "yaml_text": sf.yaml_text,
            "description": sf.description,
            "current_version": sf.current_version,
            "validation_status": sf.validation_status,
            "validation_errors": sf.validation_errors,
            "updated_at": sf.updated_at,
        }

    @app.put("/api/internal/skill-files/{name}")
    def save_skill_file_endpoint(
        name: str, payload: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        from axiom.skills.skill_file_parser import SkillFileParseError
        from axiom.skills.skill_file_store import save_skill_file

        yaml_text = payload.get("yaml_text", "")
        if not yaml_text:
            raise HTTPException(status_code=400, detail="missing yaml_text in body")
        with session_local() as session:
            try:
                result = save_skill_file(session, name=name, yaml_text=yaml_text)
            except SkillFileParseError as exc:
                # First-ever save of this name was invalid — nothing to promote.
                return {
                    "name": name,
                    "version": 0,
                    "validation_status": "invalid",
                    "validation_errors": [str(exc)],
                }
        return {
            "name": result.name,
            "version": result.current_version,
            "validation_status": result.validation_status,
            "validation_errors": result.validation_errors,
        }

    @app.get("/api/internal/skill-files/{name}/versions")
    def list_skill_file_versions_endpoint(name: str) -> dict[str, Any]:
        from axiom.skills.skill_file_store import list_versions

        with session_local() as session:
            return {"versions": list_versions(session, name)}

    @app.post("/api/internal/skill-files/{name}/run")
    def run_skill_file_endpoint(
        name: str, payload: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        from axiom.skills.skill_file_parser import (
            SkillFileParseError,
            parse_skill_file_yaml,
        )
        from axiom.skills.skill_file_runner import SkillFileRunner, run_to_dict
        from axiom.skills.skill_file_store import get_skill_file

        with session_local() as session:
            sf_row = get_skill_file(session, name)
        if sf_row is None:
            raise HTTPException(status_code=404, detail=f"skill file not found: {name}")
        if sf_row.validation_status != "valid":
            raise HTTPException(
                status_code=400,
                detail="skill file is not valid; fix the YAML before running",
            )
        try:
            skill_file = parse_skill_file_yaml(sf_row.yaml_text)
        except SkillFileParseError as exc:
            raise HTTPException(status_code=400, detail=f"parse error: {exc}") from exc

        trigger = payload.get("trigger", {})
        if not isinstance(trigger, dict):
            raise HTTPException(
                status_code=400, detail="trigger must be a JSON object"
            )
        runner = SkillFileRunner(session_factory=session_local)
        result = runner.run(skill_file, trigger=trigger)
        return run_to_dict(result)

    @app.get("/api/entities")
    def get_entities(type: str | None = None) -> list[dict[str, Any]]:  # noqa: A002
        with session_local() as session:
            stmt = select(Entity)
            if type is not None:
                stmt = stmt.where(Entity.type == type)
            rows = session.execute(stmt).scalars().all()
            return [EntityDTO.model_validate(r).model_dump(mode="json") for r in rows]

    @app.get("/api/cluster_health")
    def get_cluster_health() -> dict[str, object]:
        with session_local() as session:
            snapshot = cluster_health_monitor.snapshot(session)
            payload: dict[str, object] = {
                cluster_id: item.to_json() for cluster_id, item in snapshot.items()
            }
            rows = session.execute(select(Entity)).scalars().all()
            classified = sum(1 for row in rows if (row.composite_importance or 0.0) > 0.0)
            classified_pct = 0.0 if not rows else (classified / len(rows)) * 100.0
            clusters_present = sum(1 for item in snapshot.values() if item.total_entities > 0)
            events_per_min = float(getattr(app.state, "events_per_min", 0.0))
            fps = float(os.environ.get("AXIOM_TARGET_FPS", "60"))
            score = compute_brain_health_score(
                classified_pct=classified_pct,
                events_per_min=events_per_min,
                fps=fps,
                clusters_present=clusters_present,
                total_clusters=len(snapshot),
            )
            payload["overall"] = {
                "percentage": score,
                "status": health_status_for_score(score).value,
                "classified_pct": classified_pct,
                "events_per_min": events_per_min,
                "fps": fps,
                "clusters_present": clusters_present,
                "total_clusters": len(snapshot),
            }
            return payload

    @app.get("/api/sources")
    def get_sources() -> list[dict[str, object]]:
        with session_local() as session:
            return real_sources_snapshot(session)

    @app.get("/api/entities/search")
    def search_entities_endpoint(
        q: str = Query("", min_length=0),
        limit: int = Query(8, ge=1, le=25),
    ) -> list[EntitySearchResult]:
        with session_local() as session:
            return search_entities(session, q, limit=limit)

    @app.post("/api/internal/search")
    def post_internal_search(body: Annotated[InternalSearchIn, Body()]) -> dict[str, Any]:
        try:
            with session_local() as session:
                return hybrid_search(
                    session,
                    body.query,
                    mode=body.mode,
                    top_k=body.top_k,
                    weights=body.weights,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/edges")
    def get_edges() -> list[dict[str, Any]]:
        with session_local() as session:
            rows = session.execute(select(Edge)).scalars().all()
            return [EdgeDTO.model_validate(r).model_dump(mode="json") for r in rows]

    @app.get("/api/entities/{entity_id}/edges")
    def get_entity_edges(entity_id: str) -> dict[str, list[dict[str, Any]]]:
        with session_local() as session:
            if session.get(Entity, entity_id) is None:
                raise HTTPException(status_code=404, detail="entity not found")
            incoming = (
                session.execute(
                    select(Edge)
                    .where(Edge.target_id == entity_id)
                    .order_by(desc(Edge.created_at), Edge.id)
                )
                .scalars()
                .all()
            )
            outgoing = (
                session.execute(
                    select(Edge)
                    .where(Edge.source_id == entity_id)
                    .order_by(desc(Edge.created_at), Edge.id)
                )
                .scalars()
                .all()
            )
            return {
                "incoming": [
                    EdgeDTO.model_validate(row).model_dump(mode="json") for row in incoming
                ],
                "outgoing": [
                    EdgeDTO.model_validate(row).model_dump(mode="json") for row in outgoing
                ],
            }

    @app.get("/api/entities/{entity_id}/lineage")
    def get_entity_lineage(
        entity_id: str,
        depth: int = Query(2, ge=0, le=5),
    ) -> dict[str, list[dict[str, Any]]]:
        with session_local() as session:
            root = session.get(Entity, entity_id)
            if root is None:
                raise HTTPException(status_code=404, detail="entity not found")

            visited_node_ids = {entity_id}
            frontier = {entity_id}
            lineage_edges: dict[str, Edge] = {}
            for _level in range(depth):
                if not frontier:
                    break
                rows = (
                    session.execute(
                        select(Edge)
                        .where(Edge.target_id.in_(frontier))
                        .order_by(desc(Edge.created_at), Edge.id)
                    )
                    .scalars()
                    .all()
                )
                next_frontier: set[str] = set()
                for edge in rows:
                    lineage_edges.setdefault(edge.id, edge)
                    if edge.source_id not in visited_node_ids:
                        visited_node_ids.add(edge.source_id)
                        next_frontier.add(edge.source_id)
                frontier = next_frontier

            nodes = (
                session.execute(
                    select(Entity).where(Entity.id.in_(visited_node_ids)).order_by(Entity.id)
                )
                .scalars()
                .all()
            )
            return {
                "nodes": [EntityDTO.model_validate(row).model_dump(mode="json") for row in nodes],
                "edges": [
                    EdgeDTO.model_validate(row).model_dump(mode="json")
                    for row in lineage_edges.values()
                ],
            }

    @app.get("/api/governance")
    def get_governance() -> dict[str, Any]:
        now_ms = datetime_now_ms()
        with session_local() as session:
            entities = session.execute(select(Entity)).scalars().all()
            all_edges = session.execute(select(Edge)).scalars().all()
            edges = sorted(all_edges, key=lambda item: item.created_at, reverse=True)[:50]
            sources = (
                session.execute(select(Source).order_by(desc(Source.updated_at))).scalars().all()
            )
            receipts = (
                session.execute(
                    select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(50)
                )
                .scalars()
                .all()
            )
            all_receipts = session.execute(select(Receipt)).scalars().all()
            actions = (
                session.execute(select(Action).order_by(desc(Action.created_at)).limit(50))
                .scalars()
                .all()
            )
            all_actions = session.execute(select(Action)).scalars().all()
            cluster_snapshot = cluster_health_monitor.snapshot(session)

        raw_mcp_events = list(getattr(app.state, "mcp_action_events", []))
        mcp_events = sorted(
            raw_mcp_events,
            key=lambda item: int(item.get("timestamp", 0)),
            reverse=True,
        )[:50]

        policy_entities = sorted(
            [entity for entity in entities if _is_policy_entity(entity)],
            key=lambda entity: entity.updated_at,
            reverse=True,
        )
        policies = [
            {
                "id": entity.id,
                "name": _entity_name(entity),
                "type": entity.type,
                "scope": _text((entity.data or {}).get("scope"))
                or entity.cluster_id
                or entity.type,
                "owner": _text((entity.data or {}).get("owner")),
                "team": _text((entity.data or {}).get("team")),
                "mode": _text((entity.data or {}).get("mode")),
                "status": _text((entity.data or {}).get("status")) or "recorded",
                "updated_at": _iso(entity.updated_at),
                "source_id": entity.source_id,
            }
            for entity in policy_entities[:50]
        ]

        checks = [
            {
                "id": item.cluster_id,
                "entity": item.cluster_id,
                "type": "cluster_health",
                "severity": item.status.value,
                "result": item.status.value,
                "last_run": _iso(item.last_ingest_at),
                "owner": "organizer",
                "ingest_rate_per_min": item.ingest_rate_per_min,
                "total_entities": item.total_entities,
            }
            for item in cluster_snapshot.values()
        ]

        receipt_rows = [_receipt_row(receipt) for receipt in receipts]

        audit_events: list[dict[str, Any]] = [
            {
                "id": receipt.action_id,
                "timestamp": _iso(receipt.created_at),
                "actor": receipt.agent_name,
                "action": receipt.intent,
                "entity": receipt.target_entity_id,
                "category": "persisted_action",
                "result": receipt.decision,
                "source": "receipts",
            }
            for receipt in receipts
        ]
        audit_events.extend(
            [
                {
                    "id": action.id,
                    "timestamp": _iso(action.created_at),
                    "actor": action.agent_id,
                    "action": action.tool,
                    "entity": _text((action.params or {}).get("target_entity_id"))
                    or action.task_id,
                    "category": "persisted_action",
                    "result": action.decision,
                    "source": "actions",
                }
                for action in actions
            ]
        )
        audit_events.extend(
            {
                "id": str(event.get("action_id") or event.get("timestamp") or index),
                "timestamp_ms": int(event.get("timestamp", 0)),
                "actor": _text(event.get("agent_name")),
                "action": _text(event.get("proposed_action")) or _text(event.get("intent")),
                "entity": _text(event.get("action_id")),
                "category": "mcp_event",
                "result": _text(event.get("decision")) or _text(event.get("status")),
                "source": "mcp_event_buffer",
            }
            for index, event in enumerate(mcp_events)
        )
        audit_events.sort(
            key=lambda item: (
                int(item["timestamp_ms"])
                if item.get("timestamp_ms") is not None
                else int(datetime.fromisoformat(item["timestamp"]).timestamp() * 1000)
                if item.get("timestamp")
                else 0
            ),
            reverse=True,
        )

        signed_receipts = sum(1 for receipt in all_receipts if _receipt_signed(receipt))
        healthy_checks = sum(
            1 for item in cluster_snapshot.values() if item.status.value == "healthy"
        )
        degraded_checks = sum(
            1 for item in cluster_snapshot.values() if item.status.value == "degraded"
        )
        critical_checks = sum(
            1 for item in cluster_snapshot.values() if item.status.value == "critical"
        )
        denied_actions = (
            sum(1 for receipt in all_receipts if receipt.decision == "deny")
            + sum(1 for action in all_actions if action.decision == "deny")
            + sum(
                1
                for event in raw_mcp_events
                if event.get("decision") == "deny" or event.get("status") == "deny"
            )
        )
        current_merkle_root = receipts[0].this_hash if receipts else None
        active_policy_count = sum(
            1
            for entity in policy_entities
            if str((entity.data or {}).get("status") or "recorded").lower()
            not in {"archived", "inactive"}
        )

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "source": "database",
            "summary": {
                "policy_count": len(policy_entities),
                "active_policy_count": active_policy_count,
                "check_count": len(checks),
                "healthy_check_count": healthy_checks,
                "degraded_check_count": degraded_checks,
                "critical_check_count": critical_checks,
                "receipt_count": len(all_receipts),
                "signed_receipt_count": signed_receipts,
                "action_count": len(all_receipts) + len(all_actions) + len(raw_mcp_events),
                "denied_action_count": denied_actions,
                "current_merkle_root": current_merkle_root,
                "graph_entity_count": len(entities),
                "graph_edge_count": len(all_edges),
                "source_count": len(sources),
                "latest_event_at": max(
                    (event.get("timestamp") for event in raw_mcp_events), default=None
                ),
                "current_seq": broadcaster.current_seq,
                "generated_at_ms": now_ms,
            },
            "policies": policies,
            "checks": checks,
            "receipts": receipt_rows,
            "audit_events": audit_events[:50],
            "sources": [
                {
                    "id": source.id,
                    "source_type": source.source_type,
                    "display_name": source.display_name,
                    "connected": source.connected,
                    "created_at": _iso(source.created_at),
                    "updated_at": _iso(source.updated_at),
                }
                for source in sources
            ],
            "lineage": {
                "entities": [
                    {
                        "id": entity.id,
                        "name": _entity_name(entity),
                        "type": entity.type,
                        "cluster_id": entity.cluster_id,
                        "updated_at": _iso(entity.updated_at),
                    }
                    for entity in sorted(entities, key=lambda item: item.updated_at, reverse=True)[
                        :25
                    ]
                ],
                "edges": [
                    {
                        "id": edge.id,
                        "source_id": edge.source_id,
                        "target_id": edge.target_id,
                        "relationship": edge.relationship,
                        "created_at": _iso(edge.created_at),
                    }
                    for edge in edges
                ],
            },
        }

    @app.get("/api/internal/receipts")
    def get_internal_receipts(
        limit: int = Query(50, ge=1, le=200),
        before: str | None = None,
        agent: str | None = None,
        decision: str | None = None,
        target_entity_id: str | None = None,
    ) -> dict[str, Any]:
        before_dt: datetime | None = None
        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid before timestamp") from exc

        filters = []
        if agent:
            filters.append(Receipt.agent_name == agent)
        if decision:
            filters.append(Receipt.decision == decision)
        if target_entity_id:
            filters.append(Receipt.target_entity_id == target_entity_id)

        with session_local() as session:
            total_query = select(func.count(Receipt.id))
            data_query = (
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(limit)
            )
            head_query = (
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(1)
            )
            for condition in filters:
                total_query = total_query.where(condition)
                data_query = data_query.where(condition)
                head_query = head_query.where(condition)
            if before_dt is not None:
                data_query = data_query.where(Receipt.created_at < before_dt)
            rows = session.execute(data_query).scalars().all()
            total_count = int(session.execute(total_query).scalar_one())
            head = session.execute(head_query).scalar_one_or_none()

        return {
            "receipts": [_receipt_row(row) for row in rows],
            "total_count": total_count,
            "merkle_head": head.this_hash if head is not None else None,
        }

    @app.get("/api/internal/receipts/{receipt_id}")
    def get_internal_receipt(receipt_id: str) -> dict[str, Any]:
        with session_local() as session:
            receipt = session.get(Receipt, receipt_id)
            if receipt is None:
                raise HTTPException(status_code=404, detail="receipt not found")
            try:
                verification = verify_receipt_chain(session, receipt_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="receipt not found") from exc
            return {
                **_receipt_row(receipt),
                "verification_status": "verified" if verification["verified"] else "broken",
                "chain_verified": verification["chain_verified"],
                "signature_verified": verification["signature_verified"],
                "signature_reason": verification["signature_reason"],
            }

    @app.get("/api/internal/signing-pubkey")
    def get_internal_signing_pubkey() -> dict[str, str]:
        keypair = load_or_create_keypair()
        return {"public_key": base64.b64encode(keypair.public_key_bytes).decode("ascii")}

    @app.get("/api/internal/merkle-status")
    def get_internal_merkle_status() -> dict[str, Any]:
        with session_local() as session:
            chain_length = int(session.execute(select(func.count(Receipt.id))).scalar_one())
            head = session.execute(
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(1)
            ).scalar_one_or_none()
            tail = session.execute(
                select(Receipt).order_by(Receipt.created_at, Receipt.id).limit(1)
            ).scalar_one_or_none()
            scheme_rows = session.execute(
                select(Receipt.signing_scheme, func.count(Receipt.id)).group_by(
                    Receipt.signing_scheme
                )
            ).all()

        distribution = {"ed25519": 0, "ml_dsa_65": 0, "hybrid": 0}
        for scheme, count in scheme_rows:
            if scheme in distribution:
                distribution[str(scheme)] = int(count)

        return {
            "chain_length": chain_length,
            "head_hash": head.this_hash if head is not None else None,
            "tail_hash": tail.this_hash if tail is not None else None,
            "last_appended_at": _iso(head.created_at) if head is not None else None,
            "signing_schemes_distribution": distribution,
        }

    @app.websocket("/ws/brain")
    async def ws_brain(ws: WebSocket, since: int = Query(0)) -> None:
        if auth_required():
            if auth_is_misconfigured():
                await ws.close(code=1011, reason="AXIOM_API_TOKEN is not configured")
                return
            if not websocket_is_authenticated(ws):
                await ws.close(code=1008, reason="Missing or invalid API bearer token")
                return
        await ws.accept(subprotocol=websocket_auth_subprotocol(ws))
        async for envelope in broadcaster.subscribe(since=since):
            await ws.send_text(json.dumps(envelope))

    @app.post("/api/internal/agent-navigation")
    async def publish_agent_navigation(
        batch: Annotated[NavigationBatchIn, Body()],
    ) -> dict[str, int]:
        now_ms = datetime_now_ms()
        emitted = 0
        for step in batch.steps[:50]:
            await broadcaster.publish(
                {
                    "type": "agent_navigation_step",
                    "source_id": None,
                    "persisted_id": None,
                    "timestamp": now_ms,
                    "payload": {
                        "agent_name": batch.agent_name or "external_mcp_client",
                        "from_id": step.from_id,
                        "to_id": step.to_id,
                        "edge_id": step.edge_id,
                        "timestamp": now_ms,
                        "demo": False,
                    },
                }
            )
            emitted += 1
        return {"emitted": emitted}

    @app.post("/api/internal/agent-action-events")
    async def publish_agent_action_events(
        batch: Annotated[AgentActionEventsIn, Body()],
    ) -> dict[str, int]:
        emitted = 0
        for event in batch.events[:50]:
            payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
            intent = str(payload.get("intent", ""))
            proposed = str(payload.get("proposed_action", ""))
            agent_name = str(payload.get("agent_name", ""))
            timestamp = int(event.get("timestamp", datetime_now_ms()))
            matched_tool = next(
                (name for name in MCP_TOOL_NAMES if name in {intent, proposed}), None
            )
            if matched_tool:
                app.state.mcp_tool_counts[matched_tool] = (
                    int(app.state.mcp_tool_counts.get(matched_tool, 0)) + 1
                )
                app.state.mcp_last_called[matched_tool] = timestamp
            app.state.mcp_action_events.append(
                {
                    "agent_name": agent_name,
                    "intent": intent,
                    "proposed_action": proposed,
                    "decision": payload.get("decision"),
                    "status": payload.get("decision") or "running",
                    "action_id": payload.get("action_id"),
                    "timestamp": timestamp,
                    "duration_ms": payload.get("duration_ms"),
                }
            )
            app.state.mcp_action_events = app.state.mcp_action_events[-250:]
            await broadcaster.publish(
                {
                    "type": str(event.get("type", "agent_action")),
                    "source_id": event.get("source_id"),
                    "persisted_id": event.get("persisted_id"),
                    "timestamp": timestamp,
                    "payload": payload,
                }
            )
            emitted += 1
        return {"emitted": emitted}

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
