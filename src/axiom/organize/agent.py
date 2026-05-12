"""Phase 5.7.D — background organizer agent.

The agent runs two cooperative loops:

  * ``classify_loop``  — every ``CLASSIFY_INTERVAL_SEC`` seconds, finds up
    to ``CLASSIFY_BATCH_SIZE`` unclassified entities, picks a cluster
    via the hybrid classifier, persists it, and broadcasts an
    ``entity_classified`` event so the brain can lerp the node to its
    cluster centroid.

  * ``centrality_loop`` — every ``CENTRALITY_INTERVAL_SEC`` seconds, runs
    the PageRank+degree+recency scorer over the whole graph.

Both loops survive individual exceptions; the only way to stop them is
via ``cancel()`` (called by the FastAPI lifespan).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from axiom.organize.centrality import CentralityScorer
from axiom.organize.classifier import HybridClassifier
from axiom.organize.clusters import is_valid_cluster_id
from axiom.organize.edge_proposer import EdgeProposer
from axiom.retrieval.embeddings import canonical_content_hash, embed_entities_batch
from axiom.schema.models import Entity, EntityEmbedding

logger = logging.getLogger("axiom.organize.agent")

CLASSIFY_INTERVAL_SEC: Final[float] = 5.0
CLASSIFY_BATCH_SIZE: Final[int] = 20
CENTRALITY_INTERVAL_SEC: Final[float] = 30.0
EDGE_PROPOSAL_INTERVAL_SEC: Final[float] = 15.0
EMBEDDING_DEBOUNCE_SEC: Final[float] = 1.0


class _Broadcaster(Protocol):
    async def publish(self, envelope: dict[str, Any]) -> int: ...


SessionFactory = Callable[[], Session]


class OrganizerAgent:
    """Background classification + centrality loop.

    Designed for FastAPI lifespan: the caller wires ``broadcaster`` and a
    sync ``session_factory`` (matches the rest of studio/server.py),
    starts the loops, and cancels them on shutdown.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory | sessionmaker[Session],
        broadcaster: _Broadcaster | None = None,
        classifier: HybridClassifier | None = None,
        scorer: CentralityScorer | None = None,
        edge_proposer: EdgeProposer | None = None,
        classify_interval_sec: float = CLASSIFY_INTERVAL_SEC,
        centrality_interval_sec: float = CENTRALITY_INTERVAL_SEC,
        edge_proposal_interval_sec: float = EDGE_PROPOSAL_INTERVAL_SEC,
        embedding_debounce_sec: float = EMBEDDING_DEBOUNCE_SEC,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._session_factory: SessionFactory = (
            session_factory if not isinstance(session_factory, sessionmaker) else session_factory
        )
        self._broadcaster = broadcaster
        self.classifier: HybridClassifier = classifier or HybridClassifier()
        self.scorer: CentralityScorer = scorer or CentralityScorer()
        self.edge_proposer: EdgeProposer = edge_proposer or EdgeProposer(broadcaster=broadcaster)
        self.classify_interval_sec = classify_interval_sec
        self.centrality_interval_sec = centrality_interval_sec
        self.edge_proposal_interval_sec = edge_proposal_interval_sec
        self.embedding_debounce_sec = embedding_debounce_sec
        self._sleep: Callable[[float], Awaitable[None]] = sleeper or asyncio.sleep
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = False

    # ── one-shot hooks (used directly in tests + during boot backfill) ──

    def classify_one(self, entity: Entity) -> str | None:
        """Classify a single entity via the underlying hybrid classifier."""

        return self.classifier.classify(entity)

    async def classify_pending(self) -> int:
        """Classify up to one batch of unclassified entities. Returns count."""

        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("organizer: failed to open db session")
            return 0
        try:
            unclassified = (
                session.execute(
                    select(Entity).where(Entity.cluster_id.is_(None)).limit(CLASSIFY_BATCH_SIZE)
                )
                .scalars()
                .all()
            )
            if not unclassified:
                return 0

            classified_payloads: list[dict[str, Any]] = []
            for entity in unclassified:
                cluster_id = self.classify_one(entity)
                if not is_valid_cluster_id(cluster_id):
                    continue
                entity.cluster_id = cluster_id
                classified_payloads.append(
                    {
                        "type": "entity_classified",
                        "timestamp": int(time.time() * 1000),
                        "source_id": entity.source_id,
                        "persisted_id": entity.id,
                        "payload": {
                            "entity_id": entity.id,
                            "cluster_id": cluster_id,
                        },
                    }
                )

            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("organizer: classification batch failed")
            session.rollback()
            return 0
        finally:
            session.close()

        if self._broadcaster is None:
            return len(classified_payloads)
        for envelope in classified_payloads:
            try:
                await self._broadcaster.publish(envelope)
            except Exception:  # noqa: BLE001
                logger.exception("organizer: broadcast failed")
        return len(classified_payloads)

    async def recompute_centrality(self) -> int:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("organizer: failed to open db session for centrality")
            return 0
        try:
            result = self.scorer.recompute_all_rich(session)
            if self._broadcaster is not None:
                await self._emit_navigation_steps(result.traversal_steps)
                await self._emit_confidence_changes(result.importance_deltas)
            return result.updated
        except Exception:  # noqa: BLE001
            logger.exception("organizer: centrality recompute failed")
            session.rollback()
            return 0
        finally:
            session.close()

    async def _emit_navigation_steps(self, steps: list[tuple[str, str, str | None]]) -> None:
        if not steps or self._broadcaster is None:
            return
        max_events = 50
        sampled: list[tuple[str, str, str | None]]
        if len(steps) <= max_events:
            sampled = steps
        else:
            first_10 = steps[:10]
            last_10 = steps[-10:]
            middle = steps[10:-10]
            stride = max(1, len(middle) // (max_events - 20))
            sampled = first_10 + middle[::stride][: max_events - 20] + last_10

        now_ms = int(time.time() * 1000)
        for from_id, to_id, edge_id in sampled:
            try:
                await self._broadcaster.publish(
                    {
                        "type": "agent_navigation_step",
                        "source_id": None,
                        "persisted_id": None,
                        "timestamp": now_ms,
                        "payload": {
                            "agent_name": "organizer",
                            "from_id": from_id,
                            "to_id": to_id,
                            "edge_id": edge_id,
                            "timestamp": now_ms,
                            "demo": False,
                        },
                    }
                )
            except Exception:  # noqa: BLE001
                logger.exception("organizer: navigation step broadcast failed")

    async def _emit_confidence_changes(self, deltas: list[Any]) -> None:
        if not deltas or self._broadcaster is None:
            return
        now_ms = int(time.time() * 1000)
        for delta in deltas:
            try:
                await self._broadcaster.publish(
                    {
                        "type": "confidence_changed",
                        "source_id": None,
                        "persisted_id": delta.entity_id,
                        "timestamp": now_ms,
                        "payload": {
                            "entity_id": delta.entity_id,
                            "old_value": round(delta.old_value, 4),
                            "new_value": round(delta.new_value, 4),
                            "delta": round(delta.delta, 4),
                            "direction": delta.direction,
                            "timestamp": now_ms,
                            "demo": False,
                        },
                    }
                )
            except Exception:  # noqa: BLE001
                logger.exception("organizer: confidence change broadcast failed")

    async def propose_edges(self) -> int:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("organizer: failed to open db session for edge proposal")
            return 0
        try:
            return await self.edge_proposer.propose_once(session)
        except Exception:  # noqa: BLE001
            logger.exception("organizer: edge proposal failed")
            session.rollback()
            return 0
        finally:
            session.close()

    async def embed_changed_entities(self) -> int:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("organizer: failed to open db session for embeddings")
            return 0
        try:
            rows = session.execute(select(Entity)).scalars().all()
            changed: list[Entity] = []
            for entity in rows:
                existing = session.get(EntityEmbedding, entity.id)
                if existing is None or existing.content_hash != canonical_content_hash(entity):
                    changed.append(entity)
            if not changed:
                return 0
            embed_entities_batch(session, changed)
            return len(changed)
        except Exception:  # noqa: BLE001
            logger.exception("organizer: embedding batch failed")
            session.rollback()
            return 0
        finally:
            session.close()

    async def backfill_once(self) -> int:
        """Drain every unclassified entity in batches. Used at app boot."""

        total = 0
        while True:
            count = await self.classify_pending()
            total += count
            if count == 0:
                break
        return total

    # ── long-running loops ──────────────────────────────────────────────

    async def classify_loop(self) -> None:
        while not self._stop:
            try:
                await self.classify_pending()
            except Exception:  # noqa: BLE001 — loop must survive
                logger.exception("organizer: classify_loop iteration failed")
            await self._sleep(self.classify_interval_sec)

    async def centrality_loop(self) -> None:
        while not self._stop:
            try:
                await self.recompute_centrality()
            except Exception:  # noqa: BLE001
                logger.exception("organizer: centrality_loop iteration failed")
            await self._sleep(self.centrality_interval_sec)

    async def edge_proposal_loop(self) -> None:
        while not self._stop:
            try:
                await self.propose_edges()
            except Exception:  # noqa: BLE001
                logger.exception("organizer: edge_proposal_loop iteration failed")
            await self._sleep(self.edge_proposal_interval_sec)

    async def embedding_loop(self) -> None:
        while not self._stop:
            await self._sleep(self.embedding_debounce_sec)
            try:
                await self.embed_changed_entities()
            except Exception:  # noqa: BLE001
                logger.exception("organizer: embedding_loop iteration failed")

    def start(self) -> list[asyncio.Task[None]]:
        if self._tasks:
            return self._tasks
        self._stop = False
        self._tasks = [
            asyncio.create_task(self.classify_loop(), name="organizer.classify"),
            asyncio.create_task(self.centrality_loop(), name="organizer.centrality"),
            asyncio.create_task(self.edge_proposal_loop(), name="organizer.edge_proposal"),
            asyncio.create_task(self.embedding_loop(), name="organizer.embedding"),
        ]
        return self._tasks

    async def cancel(self) -> None:
        self._stop = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks = []
