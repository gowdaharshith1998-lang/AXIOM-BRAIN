from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Any, cast

from fastapi import Body, FastAPI, Query, WebSocket
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select
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
from axiom.schema.models import Edge, Entity
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


def datetime_now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


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
        agent_action_task = asyncio.create_task(
            emit_demo_agent_actions(broadcaster, session_factory=session_local)
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
                agent_action_task.cancel()
                warden_task.cancel()
                with suppress(asyncio.CancelledError):
                    await health_task
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
                    agent_action_task.cancel()
                    warden_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await health_task
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

    return app
