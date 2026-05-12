from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from axiom.connectors.base import ConnectorEvent
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.sources.base import IngestEvent, Source


def normalize_to_entity(vendor: str, event: ConnectorEvent) -> dict[str, Any]:
    entity_type = str(event.payload.get("entity_type") or event.event_type)
    data = dict(event.payload)
    data["vendor"] = vendor
    data["external_id"] = event.external_id
    return {
        "nick": f"{vendor}:{event.external_id}",
        "type": entity_type,
        "source_id": f"{vendor}:{event.external_id}",
        "cluster_id": event.payload.get("cluster_id"),
        "data": data,
    }


def normalize_to_edges(_vendor: str, event: ConnectorEvent) -> list[dict[str, Any]]:
    raw_edges = event.payload.get("edges", [])
    return [dict(edge) for edge in raw_edges if isinstance(edge, dict)]


async def apply_to_brain(
    session: Session,
    entities: Sequence[dict[str, Any]],
    edges: Sequence[dict[str, Any]],
    *,
    broadcaster: EventBroadcaster,
) -> int:
    source = _ConnectorSource(entities, edges)
    pipeline = IngestPipeline(source=cast(Source, source), session=session, broadcaster=broadcaster)
    return await pipeline.run()


class _ConnectorSource:
    source_id = "connector"
    source_type = "github"

    def __init__(self, entities: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> None:
        self._entities = entities
        self._edges = edges

    async def discover(self) -> Any:
        raise NotImplementedError

    async def ingest(self, since: datetime | None = None):  # type: ignore[no-untyped-def]
        del since
        for index, entity in enumerate(self._entities):
            source_id = str(entity.get("source_id") or "connector")
            yield IngestEvent(
                event_id=f"connector-entity-{index}",
                event_type="entity_added",
                source_id=source_id,
                occurred_at=datetime.utcnow(),
                entity={
                    "nick": entity.get("nick") or source_id,
                    "type": entity["type"],
                    "cluster_id": entity.get("cluster_id"),
                    "data": entity.get("data", {}),
                    "metadata": {
                        "source_id": source_id,
                        "upsert_by_source_id": True,
                    },
                },
            )
        for index, edge in enumerate(self._edges):
            yield IngestEvent(
                event_id=f"connector-edge-{index}",
                event_type="edge_added",
                source_id="connector",
                occurred_at=datetime.utcnow(),
                edge=dict(edge),
            )

    def metadata(self) -> dict[str, Any]:
        return {}

    def watch(self, on_event):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def disconnect(self) -> None:
        return None
