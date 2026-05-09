"""Phase 5.7.B — composite centrality scoring.

Blends three signals into one importance score in [0.0, 1.0]:
  * PageRank — global graph influence.
  * Degree   — local connection density.
  * Recency  — exponential-ish decay from most recent edit.

The scorer is sync (uses a sync SQLAlchemy ``Session``) to match the
rest of the studio surface.  A background loop in ``organize.agent``
calls ``recompute_all`` every 30 s.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Final

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity

logger = logging.getLogger("axiom.organize.centrality")


# ── Tunables (kept module-level so tests can introspect them) ─────────
RECENCY_HALF_LIFE_HOURS: Final[float] = 168.0  # 1 week
PAGERANK_NORMALIZER: Final[float] = 10.0
PAGERANK_WEIGHT: Final[float] = 0.5
DEGREE_WEIGHT: Final[float] = 0.3
RECENCY_WEIGHT: Final[float] = 0.2
PAGERANK_ALPHA: Final[float] = 0.85
PAGERANK_MAX_ITER: Final[int] = 100
PAGERANK_TOL: Final[float] = 1e-4


def _coerce_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def recency_score(updated_at: datetime, *, now: datetime | None = None) -> float:
    """Linear decay over a one-week window, clamped to [0, 1]."""

    reference = _coerce_aware(now or datetime.now(UTC))
    when = _coerce_aware(updated_at)
    hours = (reference - when).total_seconds() / 3600.0
    if hours <= 0:
        return 1.0
    return max(0.0, 1.0 - (hours / RECENCY_HALF_LIFE_HOURS))


def composite_score(
    *,
    pagerank: float,
    degree_ratio: float,
    recency: float,
) -> float:
    pr_normalized = min(pagerank * PAGERANK_NORMALIZER, 1.0)
    blended = (
        pr_normalized * PAGERANK_WEIGHT
        + degree_ratio * DEGREE_WEIGHT
        + recency * RECENCY_WEIGHT
    )
    return max(0.0, min(blended, 1.0))


class ImportanceDelta:
    """Records an entity's old and new composite_importance values."""

    __slots__ = ("entity_id", "old_value", "new_value")

    def __init__(self, entity_id: str, old_value: float, new_value: float) -> None:
        self.entity_id = entity_id
        self.old_value = old_value
        self.new_value = new_value

    @property
    def delta(self) -> float:
        return self.new_value - self.old_value

    @property
    def direction(self) -> str:
        return "rising" if self.delta >= 0 else "falling"


class CentralityResult:
    """Return value from recompute_all with traversal + delta info."""

    __slots__ = ("updated", "traversal_steps", "importance_deltas")

    def __init__(self) -> None:
        self.updated: int = 0
        self.traversal_steps: list[tuple[str, str, str | None]] = []
        self.importance_deltas: list[ImportanceDelta] = []


IMPORTANCE_DELTA_THRESHOLD: Final[float] = 0.05


class CentralityScorer:
    """Recomputes ``Entity.composite_importance`` for every node."""

    def recompute_all(
        self, session: Session, *, now: datetime | None = None
    ) -> int:
        result = self.recompute_all_rich(session, now=now)
        return result.updated

    def recompute_all_rich(
        self, session: Session, *, now: datetime | None = None
    ) -> CentralityResult:
        result = CentralityResult()
        entities = session.execute(select(Entity)).scalars().all()
        if not entities:
            return result

        edges = session.execute(select(Edge)).scalars().all()
        graph = nx.DiGraph()
        for entity in entities:
            graph.add_node(entity.id)
        edge_map: dict[tuple[str, str], str] = {}
        for edge in edges:
            if edge.source_id in graph and edge.target_id in graph:
                graph.add_edge(edge.source_id, edge.target_id)
                edge_map[(edge.source_id, edge.target_id)] = edge.id

        if graph.number_of_nodes() == 0:
            return result

        pagerank = self._safe_pagerank(graph)

        for u, v in graph.edges():
            result.traversal_steps.append(
                (str(u), str(v), edge_map.get((str(u), str(v))))
            )

        degree = dict(graph.degree())
        max_degree = max(degree.values()) if degree else 1
        if max_degree == 0:
            max_degree = 1

        reference = _coerce_aware(now or datetime.now(UTC))

        for entity in entities:
            old_value = entity.composite_importance or 0.0
            pr_score = pagerank.get(entity.id, 0.0)
            deg_ratio = degree.get(entity.id, 0) / max_degree
            rec = recency_score(entity.updated_at, now=reference)
            new_value = composite_score(
                pagerank=pr_score,
                degree_ratio=deg_ratio,
                recency=rec,
            )
            entity.composite_importance = new_value
            result.updated += 1
            if abs(new_value - old_value) >= IMPORTANCE_DELTA_THRESHOLD:
                result.importance_deltas.append(
                    ImportanceDelta(entity.id, old_value, new_value)
                )

        session.commit()
        return result

    @staticmethod
    def _safe_pagerank(graph: nx.DiGraph) -> dict[str, float]:
        try:
            result = nx.pagerank(
                graph,
                alpha=PAGERANK_ALPHA,
                max_iter=PAGERANK_MAX_ITER,
                tol=PAGERANK_TOL,
            )
            return {str(k): float(v) for k, v in result.items()}
        except nx.PowerIterationFailedConvergence:
            logger.warning("pagerank did not converge — falling back to uniform")
            n = graph.number_of_nodes() or 1
            uniform = 1.0 / n
            return dict.fromkeys((str(node) for node in graph.nodes()), uniform)
