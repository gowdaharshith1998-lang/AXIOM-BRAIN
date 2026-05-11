from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, desc, func, select
from sqlalchemy.orm import sessionmaker

from axiom.api.search import EntitySearchResult, search_entities
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
from axiom.govern.policy_evaluator import get_policy_evaluator
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
    AgentRegistry,
    ClusterCheckRun,
    Edge,
    Entity,
    MetricsSnapshot,
    Receipt,
    Source,
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
from axiom.skills.skill_md import SkillManifestError, parse_skill_md, serialize_skill_md
from axiom.sources.base import IngestEvent
from axiom.sources.live_synthetic import LiveSyntheticSource
from axiom.studio.llm_keys_api import router as llm_keys_router
from axiom.studio.sources import ensure_sources_schema, real_sources_snapshot
from axiom.studio.vault_api import router as vault_router


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


class PassportIn(BaseModel):
    agent_name: str
    agent_class: str
    owner_email: str
    scope_clusters: list[str] = Field(default_factory=lambda: ["*"])
    scope_intents: list[str] = Field(default_factory=lambda: ["*"])
    scope_skills: list[str] = Field(default_factory=lambda: ["*"])
    ttl_hours: int = Field(default=1, gt=0)


class AgentRegisterIn(BaseModel):
    name: str
    agent_class: str
    owner_email: str
    passport_id: str | None = None
    issue_new_passport: bool = False
    ttl_hours: int = Field(default=24, gt=0)


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


def _entity_name(entity: Entity) -> str:
    data = entity.data or {}
    return (
        _text(data.get("title"))
        or _text(data.get("name"))
        or _text(data.get("label"))
        or entity.id
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
    return entity.type.lower() in {"policy", "governance"} or (entity.cluster_id or "").lower() == "governance" or "policy" in haystack


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
MCP_TOOL_NAMES = [
    "axiom_query_brain",
    "axiom_get_entity",
    "axiom_traverse",
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


def create_app(
    *,
    db_url: str = "sqlite:///./axiom.db",
    live: bool = False,
    live_rate: float = 0.125,
    live_pause_after: int | None = None,
    enable_organizer: bool = True,
) -> FastAPI:
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
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()
    policy_evaluator = get_policy_evaluator(session_local)
    cluster_health_monitor = ClusterHealthMonitor()
    live_source = (
        LiveSyntheticSource(rate_per_second=live_rate, max_events=live_pause_after)
        if live
        else None
    )
    demo_simulator_enabled = os.environ.get("AXIOM_DEMO_SIMULATOR") == "1"

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
        app.state.organizer = None
        app.state.events_per_min = 0.0
        app.state.studio_settings = {}
        app.state.mcp_action_events = []
        app.state.mcp_tool_counts = {name: 0 for name in MCP_TOOL_NAMES}
        app.state.mcp_last_called = {name: None for name in MCP_TOOL_NAMES}
        app.state.policy_evaluator = policy_evaluator
        if SETTINGS_FILE.exists():
            try:
                app.state.studio_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
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
                    pass

        async def cluster_check_retention_loop() -> None:
            while True:
                try:
                    with session_local() as session:
                        cleanup_cluster_check_runs(session, retention_limit_from_env())
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(21_600)

        health_task = asyncio.create_task(cluster_health_loop())
        cluster_check_retention_task = asyncio.create_task(cluster_check_retention_loop())
        agent_action_task = (
            asyncio.create_task(
                emit_demo_agent_actions(broadcaster, session_factory=session_local)
            )
            if demo_simulator_enabled
            else None
        )
        warden_task = (
            asyncio.create_task(emit_demo_warden_insights(broadcaster, session_local))
            if os.environ.get("AXIOM_DEMO_WARDEN") == "1"
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
            pass

        try:
            with session_local() as session:
                bootstrap_embeddings(session)
        except Exception:  # noqa: BLE001
            pass

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
                pass
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
                pass
            organizer.start()
            app.state.organizer = organizer

        watchdog = WatchdogAgent(
            session_factory=session_local,
            broadcaster=broadcaster,
        )
        watchdog.start()
        app.state.watchdog = watchdog

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
                    engine.dispose()

    app = FastAPI(title="AXIOM Studio API", lifespan=lifespan)
    app.state.policy_evaluator = policy_evaluator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(vault_router)
    app.include_router(llm_keys_router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "current_seq": broadcaster.current_seq,
            "live": live_source is not None,
            "events_emitted": live_source.events_emitted if live_source is not None else 0,
        }

    @app.get("/api/internal/settings")
    def get_studio_settings() -> dict[str, Any]:
        return {"settings": dict(getattr(app.state, "studio_settings", {}))}

    @app.put("/api/internal/settings")
    def put_studio_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        existing = dict(getattr(app.state, "studio_settings", {}))
        existing.update(payload)
        app.state.studio_settings = existing
        try:
            SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception:
            pass
        return {"settings": existing}

    @app.get("/api/internal/agent-registry")
    def get_agent_registry(
        days: int = Query(30, ge=1, le=365),
        type: AgentType | None = Query(None),  # noqa: A002
    ) -> dict[str, Any]:
        with session_local() as session:
            rows = get_agents(session, days=days, agent_type=type)
        passports = list_passports(session_local, active_only=False)
        passports_by_agent = {}
        for passport in passports:
            existing = passports_by_agent.get(passport.agent_name)
            if existing is None or passport.issued_at > existing.issued_at:
                passports_by_agent[passport.agent_name] = passport
        enriched = []
        for row in rows:
            payload = agent_registry_row(row)
            passport = passports_by_agent.get(row.agent_name)
            if passport is not None:
                passport_payload = passport_to_dict(passport)
                payload.update(
                    {
                        "name": row.agent_name,
                        "agent_class": passport.agent_class,
                        "owner_email": passport.owner_email,
                        "passport_id": passport.passport_id,
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
    async def post_agent_registry(body: AgentRegisterIn = Body(...)) -> dict[str, Any]:
        name = body.name.strip()
        agent_class = body.agent_class.strip()
        owner_email = body.owner_email.strip()
        if not name or not agent_class or not owner_email:
            raise HTTPException(status_code=422, detail="name, class, and owner_email are required")

        issued_token: str | None = None
        passport_payload: dict[str, Any] | None = None
        if body.issue_new_passport or not body.passport_id:
            row, issued_token = issue_passport(
                session_local,
                agent_name=name,
                agent_class=agent_class,
                owner_email=owner_email,
                scope_clusters=["*"],
                scope_intents=["*"],
                scope_skills=["*"],
                ttl_hours=body.ttl_hours,
            )
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

    @app.get("/api/internal/mcp-stats")
    def get_mcp_stats() -> dict[str, Any]:
        now_ms = datetime_now_ms()
        one_hour_ago = now_ms - 3600_000
        raw_events = list(getattr(app.state, "mcp_action_events", []))
        events = [event for event in raw_events if int(event.get("timestamp", 0)) >= one_hour_ago]
        active_agents = sorted({str(event.get("agent_name", "")).strip() for event in events if event.get("agent_name")})
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
            "recent_actions": sorted(events, key=lambda item: int(item.get("timestamp", 0)), reverse=True)[:20],
        }

    async def publish_passport_event(event_type: str, payload: dict[str, Any], persisted_id: str) -> None:
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
    async def post_internal_passport(body: PassportIn = Body(...)) -> dict[str, Any]:
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
    async def delete_internal_passport(passport_id: str, reason: str | None = None) -> dict[str, Any]:
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
        body: KillSwitchIn = Body(...),
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
                    pass
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
        body: WatchdogResolveIn = Body(...),
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
        body: ApprovalResolveIn = Body(...),
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
        body: ApprovalResolveIn = Body(...),
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

    def _raise_skill_error(exc: Exception) -> None:
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
    async def post_internal_skill(body: SkillIn = Body(...)) -> dict[str, Any]:
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
        body: CompileSkillsIn = Body(default_factory=CompileSkillsIn),
    ) -> dict[str, Any]:
        try:
            with session_local() as session:
                rows = compile_skills_from_processes(
                    session,
                    dry_run=body.dry_run,
                    process_ids=body.process_ids,
                )
                if body.dry_run:
                    compiled = [manifest_to_dict(row) for row in rows]
                else:
                    compiled = [skill_to_dict(row) for row in rows]
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
    def post_internal_skill_run(skill_id: str, body: SkillRunIn = Body(...)) -> dict[str, Any]:
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
            payload = {cluster_id: item.to_json() for cluster_id, item in snapshot.items()}
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
    def post_internal_search(body: InternalSearchIn = Body(...)) -> dict[str, Any]:
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
            incoming = session.execute(
                select(Edge).where(Edge.target_id == entity_id).order_by(desc(Edge.created_at), Edge.id)
            ).scalars().all()
            outgoing = session.execute(
                select(Edge).where(Edge.source_id == entity_id).order_by(desc(Edge.created_at), Edge.id)
            ).scalars().all()
            return {
                "incoming": [EdgeDTO.model_validate(row).model_dump(mode="json") for row in incoming],
                "outgoing": [EdgeDTO.model_validate(row).model_dump(mode="json") for row in outgoing],
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
                rows = session.execute(
                    select(Edge)
                    .where(Edge.target_id.in_(frontier))
                    .order_by(desc(Edge.created_at), Edge.id)
                ).scalars().all()
                next_frontier: set[str] = set()
                for edge in rows:
                    lineage_edges.setdefault(edge.id, edge)
                    if edge.source_id not in visited_node_ids:
                        visited_node_ids.add(edge.source_id)
                        next_frontier.add(edge.source_id)
                frontier = next_frontier

            nodes = session.execute(
                select(Entity).where(Entity.id.in_(visited_node_ids)).order_by(Entity.id)
            ).scalars().all()
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
            sources = session.execute(select(Source).order_by(desc(Source.updated_at))).scalars().all()
            receipts = session.execute(
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(50)
            ).scalars().all()
            all_receipts = session.execute(select(Receipt)).scalars().all()
            actions = session.execute(select(Action).order_by(desc(Action.created_at)).limit(50)).scalars().all()
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
                "scope": _text((entity.data or {}).get("scope")) or entity.cluster_id or entity.type,
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
                "entity": _text((action.params or {}).get("target_entity_id")) or action.task_id,
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
        healthy_checks = sum(1 for item in cluster_snapshot.values() if item.status.value == "healthy")
        degraded_checks = sum(1 for item in cluster_snapshot.values() if item.status.value == "degraded")
        critical_checks = sum(1 for item in cluster_snapshot.values() if item.status.value == "critical")
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
                "latest_event_at": max((event.get("timestamp") for event in raw_mcp_events), default=None),
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
                    for entity in sorted(entities, key=lambda item: item.updated_at, reverse=True)[:25]
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
        await ws.accept()
        async for envelope in broadcaster.subscribe(since=since):
            await ws.send_text(json.dumps(envelope))

    @app.post("/api/internal/agent-navigation")
    async def publish_agent_navigation(batch: NavigationBatchIn = Body(...)) -> dict[str, int]:
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
    async def publish_agent_action_events(batch: AgentActionEventsIn = Body(...)) -> dict[str, int]:
        emitted = 0
        for event in batch.events[:50]:
            payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
            intent = str(payload.get("intent", ""))
            proposed = str(payload.get("proposed_action", ""))
            agent_name = str(payload.get("agent_name", ""))
            timestamp = int(event.get("timestamp", datetime_now_ms()))
            matched_tool = next((name for name in MCP_TOOL_NAMES if name in {intent, proposed}), None)
            if matched_tool:
                app.state.mcp_tool_counts[matched_tool] = int(app.state.mcp_tool_counts.get(matched_tool, 0)) + 1
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

    return app
