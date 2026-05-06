from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.dto import EdgeDTO, EntityDTO
from axiom.schema.models import Edge, Entity


def create_app(*, db_url: str = "sqlite:///./axiom.db") -> FastAPI:
    engine = create_engine(db_url, future=True)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.broadcaster = broadcaster
        app.state.SessionLocal = session_local
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="AXIOM Studio API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "current_seq": broadcaster.current_seq}

    @app.get("/api/entities")
    def get_entities() -> list[dict[str, Any]]:
        with session_local() as session:
            rows = session.execute(select(Entity)).scalars().all()
            return [EntityDTO.model_validate(r).model_dump(mode="json") for r in rows]

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

    return app

