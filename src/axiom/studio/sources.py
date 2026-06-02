from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session

from axiom.schema.models import Entity, Source
from axiom.storage.db import create_schema_table


@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    name: str
    count: int
    last_event_at: str
    live: bool


def ensure_sources_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("sources"):
        create_schema_table(Source.__table__, engine)
    # Defense in depth: seed both synthetic source rows so any synthetic ingest
    # path (entities.source_id = 'synthetic-default' or 'live-synthetic') always
    # has its referenced row present, even though entities.source_id is no longer
    # a hard FK to sources.id.
    seeds = [
        Source(
            id="synthetic-default",
            source_type="synthetic",
            display_name="Synthetic",
            connected=True,
            metadata_json={},
        ),
        Source(
            id="live-synthetic",
            source_type="synthetic",
            display_name="Live Synthetic",
            connected=True,
            metadata_json={},
        ),
    ]
    with Session(engine, expire_on_commit=False, future=True) as session:
        added = False
        for seed in seeds:
            if session.get(Source, seed.id) is None:
                session.add(seed)
                added = True
        if added:
            session.commit()


def real_sources_snapshot(session: Session) -> list[dict[str, object]]:
    stmt = (
        select(
            Source.id,
            Source.source_type,
            Source.display_name,
            Source.connected,
            func.count(Entity.id),
            func.max(Entity.created_at),
        )
        .join(Entity, Entity.source_id == Source.id)
        .group_by(Source.id, Source.source_type, Source.display_name, Source.connected)
        .order_by(Source.display_name)
    )
    rows: list[dict[str, object]] = []
    for source_id, source_type, display_name, connected, count, last_event_at in session.execute(
        stmt
    ):
        rows.append(
            {
                "source_id": source_id,
                "source_type": source_type,
                "name": display_name,
                "display_name": display_name,
                "count": int(count),
                "last_event_at": last_event_at.isoformat() if last_event_at is not None else None,
                "freshness": last_event_at.isoformat() if last_event_at is not None else None,
                "live": bool(connected),
                "connected": bool(connected),
            }
        )
    return rows


synthetic_sources_snapshot = real_sources_snapshot
