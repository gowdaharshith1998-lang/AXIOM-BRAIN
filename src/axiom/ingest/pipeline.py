from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.dto import EntityDTO
from axiom.schema.models import Entity
from axiom.sources.base import IngestEvent, Source
from axiom.storage import crud


class IngestPipeline:
    """Reads from a Source, writes to storage, broadcasts envelopes.

    Universal-entity discipline: no branching on entity.type strings.
    """

    def __init__(self, *, source: Source, session: Session, broadcaster: EventBroadcaster) -> None:
        self.source = source
        self.session = session
        self.broadcaster = broadcaster
        self._nick_to_id: dict[str, str] = {}

    async def run(self, *, since: datetime | None = None) -> int:
        count = 0
        async for event in self.source.ingest(since=since):
            await self._handle(event)
            count += 1
        return count

    async def _handle(self, event: IngestEvent) -> None:
        now_ms = int(time.time() * 1000)

        if event.event_type == "entity_added" and event.entity is not None:
            payload = event.entity
            entity_type = str(payload["type"])
            data = payload.get("data", {})
            metadata = payload.get("metadata", {})
            nick = payload.get("nick")
            upsert_by_source_id = bool(metadata.get("upsert_by_source_id"))

            full_data = dict(data)
            full_data["metadata"] = metadata

            entity_dto, event_type = self._persist_entity(
                entity_type=entity_type,
                data=full_data,
                source_id=event.source_id,
                cluster_id=payload.get("cluster_id"),
                upsert_by_source_id=upsert_by_source_id,
            )
            if isinstance(nick, str) and nick:
                self._nick_to_id[nick] = entity_dto.id

            await self.broadcaster.publish(
                {
                    "type": event_type,
                    "timestamp": now_ms,
                    "source_id": event.source_id,
                    "persisted_id": entity_dto.id,
                    "payload": payload,
                }
            )
            return

        if event.event_type == "edge_added" and event.edge is not None:
            payload = event.edge
            src_nick = str(payload["source_nick"])
            tgt_nick = str(payload["target_nick"])
            relationship = str(payload["relationship"])

            src_id = self._nick_to_id.get(src_nick)
            tgt_id = self._nick_to_id.get(tgt_nick)
            if src_id is None or tgt_id is None:
                return

            edge_dto = crud.add_edge(
                self.session,
                source_id=src_id,
                target_id=tgt_id,
                type_=relationship,
                data=payload.get("data", {}),
            )

            await self.broadcaster.publish(
                {
                    "type": event.event_type,
                    "timestamp": now_ms,
                    "source_id": event.source_id,
                    "persisted_id": edge_dto.id,
                    "payload": payload,
                }
            )
            return

        # Other event types are reserved for real connectors (Phase 12+).
        await self.broadcaster.publish(
            {
                "type": event.event_type,
                "timestamp": now_ms,
                "source_id": event.source_id,
                "persisted_id": None,
                "payload": {},
            }
        )

    def _persist_entity(
        self,
        *,
        entity_type: str,
        data: dict[str, Any],
        source_id: str | None,
        cluster_id: str | None,
        upsert_by_source_id: bool,
    ) -> tuple[EntityDTO, str]:
        if upsert_by_source_id and source_id:
            existing = (
                self.session.execute(select(Entity).where(Entity.source_id == source_id).limit(1))
                .scalars()
                .first()
            )
            if existing is not None:
                existing.type = entity_type
                existing.data = data
                existing.cluster_id = cluster_id
                existing.updated_at = datetime.utcnow()
                self.session.add(existing)
                self.session.commit()
                self.session.refresh(existing)
                return EntityDTO.model_validate(existing), "entity_modified"

        return (
            crud.create_entity(
                self.session,
                entity_type,
                data,
                source_id=source_id,
                cluster_id=cluster_id,
            ),
            "entity_added",
        )
