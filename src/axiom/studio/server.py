from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Any, cast

from fastapi import Body, FastAPI, Query, WebSocket
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import sessionmaker

from axiom.api.search import EntitySearchResult, search_entities
from axiom.govern.agent_actions import emit_demo_agent_actions
from axiom.govern.warden import emit_demo_warden_insights
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.organize.agent import OrganizerAgent
from axiom.organize.cluster_health import (
    ClusterHealthMonitor,
    compute_brain_health_score,
    health_status_for_score,
)
from axiom.schema.dto import EdgeDTO, EntityDTO
from axiom.schema.models import Action, Edge, Entity, Receipt, Source
from axiom.sources.base import IngestEvent
from axiom.sources.live_synthetic import LiveSyntheticSource
from axiom.studio.sources import synthetic_sources_snapshot
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


def _receipt_key(receipt: Receipt) -> str:
    payload = receipt.payload or {}
    return str(payload.get("receipt_id") or receipt.id)


def _receipt_signed(receipt: Receipt) -> bool:
    return bool(receipt.signature_ed25519_b64 or receipt.signature_mldsa_b64)

SETTINGS_FILE = Path("axiom_studio_settings.json")
MCP_TOOL_NAMES = [
    "axiom_query_brain",
    "axiom_get_entity",
    "axiom_traverse",
    "axiom_list_sources",
    "axiom_record_action",
    "axiom_check_policy",
    "axiom_request_human_approval",
]


def create_app(
    *,
    db_url: str = "sqlite:///./axiom.db",
    live: bool = False,
    live_rate: float = 0.125,
    live_pause_after: int | None = None,
    enable_organizer: bool = True,
) -> FastAPI:
    engine = create_engine(db_url, future=True)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()
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
        app.state.organizer = None
        app.state.events_per_min = 0.0
        app.state.studio_settings = {}
        app.state.mcp_action_events = []
        app.state.mcp_tool_counts = {name: 0 for name in MCP_TOOL_NAMES}
        app.state.mcp_last_called = {name: None for name in MCP_TOOL_NAMES}
        if SETTINGS_FILE.exists():
            try:
                app.state.studio_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                app.state.studio_settings = {}
        previous_health: dict[str, str] = {}
        last_seq = broadcaster.current_seq
        last_seq_at = asyncio.get_running_loop().time()

        async def cluster_health_loop() -> None:
            nonlocal last_seq, last_seq_at
            while True:
                with session_local() as session:
                    snapshot = cluster_health_monitor.snapshot(session)
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

        health_task = asyncio.create_task(cluster_health_loop())
        agent_action_task = (
            asyncio.create_task(
                emit_demo_agent_actions(broadcaster, session_factory=session_local)
            )
            if demo_simulator_enabled
            else None
        )
        warden_task = asyncio.create_task(emit_demo_warden_insights(broadcaster, session_local))
        app.state.cluster_health_task = health_task
        app.state.agent_action_task = agent_action_task
        app.state.warden_task = warden_task

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

        if live_source is None:
            try:
                yield
            finally:
                if organizer is not None:
                    await organizer.cancel()
                health_task.cancel()
                if agent_action_task is not None:
                    agent_action_task.cancel()
                warden_task.cancel()
                with suppress(asyncio.CancelledError):
                    await health_task
                if agent_action_task is not None:
                    with suppress(asyncio.CancelledError):
                        await agent_action_task
                with suppress(asyncio.CancelledError):
                    await warden_task
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
                    if organizer is not None:
                        await organizer.cancel()
                    health_task.cancel()
                    if agent_action_task is not None:
                        agent_action_task.cancel()
                    warden_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await health_task
                    if agent_action_task is not None:
                        with suppress(asyncio.CancelledError):
                            await agent_action_task
                    with suppress(asyncio.CancelledError):
                        await warden_task
                    engine.dispose()

    app = FastAPI(title="AXIOM Studio API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(vault_router)

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

    @app.get("/api/internal/mcp-stats")
    def get_mcp_stats() -> dict[str, Any]:
        now_ms = datetime_now_ms()
        one_hour_ago = now_ms - 3600_000
        raw_events = list(getattr(app.state, "mcp_action_events", []))
        events = [event for event in raw_events if int(event.get("timestamp", 0)) >= one_hour_ago]
        active_agents = sorted({str(event.get("agent_name", "")).strip() for event in events if event.get("agent_name")})
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
            "last_tool_call": max((event.get("timestamp") for event in raw_events), default=None),
            "recent_actions": sorted(events, key=lambda item: int(item.get("timestamp", 0)), reverse=True)[:20],
        }

    @app.get("/api/entities")
    def get_entities() -> list[dict[str, Any]]:
        with session_local() as session:
            rows = session.execute(select(Entity)).scalars().all()
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
            return synthetic_sources_snapshot(session)

    @app.get("/api/entities/search")
    def search_entities_endpoint(
        q: str = Query("", min_length=0),
        limit: int = Query(8, ge=1, le=25),
    ) -> list[EntitySearchResult]:
        with session_local() as session:
            return search_entities(session, q, limit=limit)

    @app.get("/api/edges")
    def get_edges() -> list[dict[str, Any]]:
        with session_local() as session:
            rows = session.execute(select(Edge)).scalars().all()
            return [EdgeDTO.model_validate(r).model_dump(mode="json") for r in rows]

    @app.get("/api/governance")
    def get_governance() -> dict[str, Any]:
        now_ms = datetime_now_ms()
        with session_local() as session:
            entities = session.execute(select(Entity)).scalars().all()
            all_edges = session.execute(select(Edge)).scalars().all()
            edges = sorted(all_edges, key=lambda item: item.created_at, reverse=True)[:50]
            sources = session.execute(select(Source).order_by(desc(Source.updated_at))).scalars().all()
            receipts = session.execute(select(Receipt).order_by(desc(Receipt.created_at)).limit(50)).scalars().all()
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

        receipt_rows = [
            {
                "id": receipt.id,
                "receipt_id": _receipt_key(receipt),
                "receipt_type": receipt.receipt_type,
                "action_id": _text((receipt.payload or {}).get("action_id")),
                "decision": _text((receipt.payload or {}).get("decision")),
                "agent_name": _text((receipt.payload or {}).get("agent_name")),
                "signing_scheme": _text((receipt.payload or {}).get("signing_scheme")),
                "merkle_root": _text((receipt.payload or {}).get("merkle_root")),
                "signed": _receipt_signed(receipt),
                "created_at": _iso(receipt.created_at),
            }
            for receipt in receipts
        ]

        audit_events: list[dict[str, Any]] = [
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
        denied_actions = sum(1 for action in all_actions if action.decision == "deny") + sum(
            1 for event in raw_mcp_events if event.get("decision") == "deny" or event.get("status") == "deny"
        )
        current_merkle_root = next(
            (
                str(receipt.payload.get("merkle_root"))
                for receipt in receipts
                if isinstance(receipt.payload, dict) and receipt.payload.get("merkle_root")
            ),
            None,
        )
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
                "action_count": len(all_actions) + len(raw_mcp_events),
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
