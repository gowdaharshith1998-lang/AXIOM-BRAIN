"""Same-cluster edge proposer for the living brain organizer."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity
from axiom.storage import crud

logger = logging.getLogger("axiom.organize.edge_proposer")


class _Broadcaster(Protocol):
    async def publish(self, envelope: dict[str, Any]) -> int: ...


class EdgeProposer:
    def __init__(self, *, broadcaster: _Broadcaster | None = None) -> None:
        self._broadcaster = broadcaster

    async def propose_once(self, session: Session, *, limit: int = 4) -> int:
        """Create up to ``limit`` missing relationships within the same cluster."""

        created = 0
        rows = (
            session.execute(
                select(Entity)
                .where(Entity.cluster_id.is_not(None))
                .order_by(
                    Entity.cluster_id,
                    Entity.composite_importance.desc(),
                    Entity.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )
        by_cluster: dict[str, list[Entity]] = {}
        for entity in rows:
            if entity.cluster_id is None:
                continue
            by_cluster.setdefault(entity.cluster_id, []).append(entity)

        for cluster_id, entities in by_cluster.items():
            if created >= limit:
                break
            for i, source in enumerate(entities):
                if created >= limit:
                    break
                for target in entities[i + 1 :]:
                    if self._edge_exists(session, source.id, target.id):
                        continue
                    try:
                        edge = crud.add_edge(
                            session,
                            source.id,
                            target.id,
                            "same_cluster_related",
                            {"proposed_by": "organizer", "cluster_id": cluster_id},
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("edge proposer: create_edge failed")
                        session.rollback()
                        return created
                    created += 1
                    await self._broadcast(edge.id, source.id, target.id, cluster_id)
                    break

        return created

    @staticmethod
    def _edge_exists(session: Session, source_id: str, target_id: str) -> bool:
        return (
            session.execute(
                select(Edge.id).where(
                    or_(
                        (Edge.source_id == source_id) & (Edge.target_id == target_id),
                        (Edge.source_id == target_id) & (Edge.target_id == source_id),
                    )
                )
            ).first()
            is not None
        )

    async def _broadcast(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        cluster_id: str,
    ) -> None:
        if self._broadcaster is None:
            return
        try:
            await self._broadcaster.publish(
                {
                    "type": "entity_edge_created",
                    "timestamp": int(time.time() * 1000),
                    "source_id": source_id,
                    "persisted_id": edge_id,
                    "payload": {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation_type": "same_cluster_related",
                        "cluster_id": cluster_id,
                    },
                }
            )
        except Exception:  # noqa: BLE001
            logger.exception("edge proposer: broadcast failed")
