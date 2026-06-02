"""HippoRAG-style Personalized PageRank retrieval.

The lexical/semantic retrievers in ``search.py`` rank entities by how well they
match the query *text*. They miss entities that are highly relevant by
*association* — a decision two hops from the query terms, a policy that governs
a matched process. Personalized PageRank fixes that in a single pass: seed a
random-walk restart distribution on the query-matched entities, run PageRank
over the entity/edge graph, and rank by the stationary distribution. Entities
that many query-relevant nodes point to bubble up even when their own text
never matched.

This is intentionally additive — it reuses ``lexical_search`` /
``semantic_search`` for seeding and returns the same ``SearchResult`` shape, so
it slots into ``hybrid_search`` as the ``"ppr"`` mode without touching the RRF
fusion path.
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from axiom.api.search import title_for_entity
from axiom.retrieval.embeddings import EmbeddingProvider
from axiom.retrieval.search import (
    SearchResult,
    _edges_touching,
    _filtered_entities,
    _safe_limit,
    lexical_search,
    semantic_search,
)

log = logging.getLogger("axiom.retrieval.graph_rank")

DEFAULT_DAMPING = 0.85
DEFAULT_SEED_TOP_K = 15
_PPR_MAX_ITER = 100
_PPR_TOLERANCE = 1.0e-6


def _seed_scores(
    session: Session,
    query: str,
    *,
    seed_top_k: int,
    entity_types: list[str] | None,
    cluster_id: str | None,
    provider: EmbeddingProvider | None,
) -> dict[str, float]:
    """Collect query-matched entities and a positive seed weight for each.

    Lexical is always available; semantic is blended in when an embedding
    table exists. Scores are kept as-is here and normalized by the caller.
    """

    seeds: dict[str, float] = {}
    for row in lexical_search(
        session,
        query,
        top_k=seed_top_k,
        entity_types=entity_types,
        cluster_id=cluster_id,
    ):
        seeds[row["id"]] = max(seeds.get(row["id"], 0.0), float(row["score"]))

    try:
        semantic_rows = semantic_search(
            session,
            query,
            top_k=seed_top_k,
            entity_types=entity_types,
            cluster_id=cluster_id,
            provider=provider,
        )
    except Exception:  # noqa: BLE001 - semantic is best-effort (no embeddings yet)
        log.debug("semantic seeding skipped for PPR query", exc_info=True)
        semantic_rows = []
    for row in semantic_rows:
        seeds[row["id"]] = max(seeds.get(row["id"], 0.0), float(row["score"]))

    return seeds


def _build_graph(
    session: Session,
    *,
    entity_types: list[str] | None,
    cluster_id: str | None,
) -> tuple[nx.DiGraph, dict[str, Any]]:
    """Build a directed graph over the (optionally filtered) entity set.

    Returns the graph plus an ``id -> Entity`` map for result hydration.
    """

    entities = _filtered_entities(session, entity_types=entity_types, cluster_id=cluster_id)
    entity_map = {entity.id: entity for entity in entities}
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(entity_map)
    # Only edges with an endpoint in the candidate set can become graph edges,
    # so restrict the scan to that set instead of loading the whole edge table
    # (127k rows in the live DB). Bounded by AXIOM_MAX_EDGE_SCAN (DB-003).
    for edge in _edges_touching(session, set(entity_map)):
        if edge.source_id in entity_map and edge.target_id in entity_map:
            # Multiple edges between the same pair just reinforce the link.
            if graph.has_edge(edge.source_id, edge.target_id):
                graph[edge.source_id][edge.target_id]["weight"] += 1.0
            else:
                graph.add_edge(edge.source_id, edge.target_id, weight=1.0)
    return graph, entity_map


def _ppr_result(
    entity: Any,
    *,
    score: float,
    matched_on: str,
) -> SearchResult:
    return {
        "id": entity.id,
        "type": entity.type,
        "title": title_for_entity(entity),
        "data": entity.data or {},
        "source_id": entity.source_id,
        "cluster_id": entity.cluster_id,
        "composite_importance": float(entity.composite_importance or 0.0),
        "score": round(float(score), 6),
        "matched_on": matched_on,
        "methods": ["ppr"],
        "breakdown": {"ppr": {"rank": 1, "score": round(float(score), 6)}},
    }


def personalized_pagerank_search(
    session: Session,
    query: str,
    *,
    top_k: int = 8,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
    provider: EmbeddingProvider | None = None,
    seed_top_k: int = DEFAULT_SEED_TOP_K,
    damping: float = DEFAULT_DAMPING,
) -> list[SearchResult]:
    """Rank entities by Personalized PageRank seeded on query matches.

    Falls back to plain lexical results when the query matches nothing or the
    graph has no edges — PPR cannot add signal without either.
    """

    cleaned = query.strip()
    if not cleaned:
        return []
    safe_top_k = _safe_limit(top_k)

    seeds = _seed_scores(
        session,
        cleaned,
        seed_top_k=max(seed_top_k, safe_top_k),
        entity_types=entity_types,
        cluster_id=cluster_id,
        provider=provider,
    )
    if not seeds:
        return []

    graph, entity_map = _build_graph(session, entity_types=entity_types, cluster_id=cluster_id)
    # Keep only seeds that survived filtering and exist as graph nodes.
    seeds = {sid: weight for sid, weight in seeds.items() if sid in graph}
    if not seeds or graph.number_of_edges() == 0:
        # No graph signal to propagate — degrade gracefully to lexical.
        return lexical_search(
            session,
            cleaned,
            top_k=safe_top_k,
            entity_types=entity_types,
            cluster_id=cluster_id,
        )

    total = sum(seeds.values()) or 1.0
    personalization = {node: (seeds.get(node, 0.0) / total) for node in graph.nodes}

    try:
        ranks = nx.pagerank(
            graph,
            alpha=damping,
            personalization=personalization,
            max_iter=_PPR_MAX_ITER,
            tol=_PPR_TOLERANCE,
            weight="weight",
        )
    except nx.PowerIterationFailedConvergence:
        log.warning("PPR failed to converge for query %r; falling back to lexical", cleaned)
        return lexical_search(
            session,
            cleaned,
            top_k=safe_top_k,
            entity_types=entity_types,
            cluster_id=cluster_id,
        )

    ranked = sorted(
        (
            (entity_map[node_id], rank)
            for node_id, rank in ranks.items()
            if rank > 0.0 and node_id in entity_map
        ),
        key=lambda item: (
            -item[1],
            -float(item[0].composite_importance or 0.0),
            title_for_entity(item[0]).casefold(),
        ),
    )

    results: list[SearchResult] = []
    for entity, rank in ranked[:safe_top_k]:
        matched_on = "ppr_seed" if entity.id in seeds else "ppr_assoc"
        results.append(_ppr_result(entity, score=rank, matched_on=matched_on))
    return results


__all__ = ["DEFAULT_DAMPING", "DEFAULT_SEED_TOP_K", "personalized_pagerank_search"]
