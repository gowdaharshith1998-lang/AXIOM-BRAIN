from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.api.search import _score_title, title_for_entity
from axiom.retrieval.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    vector_from_blob,
)
from axiom.schema.models import Edge, Entity, EntityEmbedding

SearchMode = Literal["hybrid", "lexical", "semantic", "graph"]
METHODS: tuple[str, ...] = ("lexical", "semantic", "graph")


class MethodBreakdown(TypedDict):
    rank: int
    score: float


class SearchResult(TypedDict, total=False):
    id: str
    type: str
    title: str
    data: dict[str, Any]
    source_id: str | None
    cluster_id: str | None
    composite_importance: float
    score: float
    matched_on: str
    methods: list[str]
    breakdown: dict[str, MethodBreakdown]


@dataclass(frozen=True, slots=True)
class RankedEntity:
    entity: Entity
    score: float
    matched_on: str


def lexical_search(
    session: Session,
    query: str,
    *,
    top_k: int = 8,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
) -> list[SearchResult]:
    q = query.strip()
    if not q:
        return []
    entities = _filtered_entities(session, entity_types=entity_types, cluster_id=cluster_id)
    connection_counts = _connection_counts(session)
    ranked: list[RankedEntity] = []
    for entity in entities:
        title = title_for_entity(entity)
        title_score = _score_title(q, title)
        text_score = _text_score(q, entity)
        score = max(title_score, text_score)
        if score <= 0:
            continue
        score += min(connection_counts[entity.id], 10) * 0.005
        ranked.append(RankedEntity(entity=entity, score=score, matched_on="lexical"))
    ranked.sort(
        key=lambda item: (
            -item.score,
            -float(item.entity.composite_importance or 0.0),
            title_for_entity(item.entity).casefold(),
        )
    )
    return [
        _result(item.entity, score=item.score, method="lexical")
        for item in ranked[: _safe_limit(top_k)]
    ]


def semantic_search(
    session: Session,
    query: str,
    *,
    top_k: int = 8,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[SearchResult]:
    q = query.strip()
    if not q:
        return []
    resolved_provider = provider or get_embedding_provider(session)
    query_vector = resolved_provider.embed_texts([q])[0]
    stmt = select(Entity, EntityEmbedding).join(
        EntityEmbedding, Entity.id == EntityEmbedding.entity_id
    )
    if entity_types:
        stmt = stmt.where(Entity.type.in_(entity_types))
    if cluster_id is not None:
        stmt = stmt.where(Entity.cluster_id == cluster_id)
    ranked: list[tuple[Entity, float]] = []
    for entity, embedding in session.execute(stmt).all():
        score = cosine_similarity(query_vector, vector_from_blob(embedding.embedding))
        if score <= 0:
            continue
        ranked.append((entity, score))
    ranked.sort(
        key=lambda item: (
            -item[1],
            -float(item[0].composite_importance or 0.0),
            title_for_entity(item[0]).casefold(),
        )
    )
    return [
        _result(entity, score=score, method="semantic")
        for entity, score in ranked[: _safe_limit(top_k)]
    ]


def graph_search(
    session: Session,
    query: str,
    *,
    top_k: int = 8,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
) -> list[SearchResult]:
    q = query.strip()
    if not q:
        return []
    seeds = lexical_search(
        session,
        q,
        top_k=25,
        entity_types=entity_types,
        cluster_id=cluster_id,
    )
    if not seeds:
        return []
    seed_scores = {item["id"]: float(item["score"]) for item in seeds}
    seed_ids = set(seed_scores)
    edges = session.execute(select(Edge)).scalars().all()
    entity_map = {
        entity.id: entity
        for entity in _filtered_entities(session, entity_types=entity_types, cluster_id=cluster_id)
    }
    scores: dict[str, float] = defaultdict(float)
    matched_on: dict[str, str] = {}
    for edge in edges:
        if edge.source_id in seed_ids and edge.target_id in entity_map:
            scores[edge.target_id] = max(scores[edge.target_id], seed_scores[edge.source_id] * 0.86)
            matched_on.setdefault(edge.target_id, f"neighbor_of:{edge.source_id}")
        if edge.target_id in seed_ids and edge.source_id in entity_map:
            scores[edge.source_id] = max(scores[edge.source_id], seed_scores[edge.target_id] * 0.86)
            matched_on.setdefault(edge.source_id, f"neighbor_of:{edge.target_id}")
    for seed_id, score in seed_scores.items():
        if seed_id in entity_map:
            scores[seed_id] = max(scores[seed_id], score * 0.72)
            matched_on.setdefault(seed_id, "query_match")
    ranked = sorted(
        ((entity_map[entity_id], score) for entity_id, score in scores.items()),
        key=lambda item: (
            -item[1],
            -float(item[0].composite_importance or 0.0),
            title_for_entity(item[0]).casefold(),
        ),
    )
    results = [
        _result(entity, score=score, method="graph")
        for entity, score in ranked[: _safe_limit(top_k)]
    ]
    for row in results:
        row["matched_on"] = matched_on.get(row["id"], "graph_match")
    return results


def hybrid_search(
    session: Session,
    query: str,
    *,
    mode: SearchMode = "hybrid",
    top_k: int = 8,
    weights: dict[str, float] | None = None,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    if mode not in {"hybrid", "lexical", "semantic", "graph"}:
        raise ValueError("mode must be one of hybrid, lexical, semantic, graph")
    safe_top_k = _safe_limit(top_k)
    if not query.strip():
        return {"results": [], "breakdown": _empty_breakdown(), "count": 0, "mode": mode}

    method_results: dict[str, list[SearchResult]] = {}
    selected_methods = METHODS if mode == "hybrid" else (mode,)
    if "lexical" in selected_methods:
        method_results["lexical"] = lexical_search(
            session,
            query,
            top_k=max(safe_top_k * 4, 25),
            entity_types=entity_types,
            cluster_id=cluster_id,
        )
    if "semantic" in selected_methods:
        method_results["semantic"] = semantic_search(
            session,
            query,
            top_k=max(safe_top_k * 4, 25),
            entity_types=entity_types,
            cluster_id=cluster_id,
            provider=provider,
        )
    if "graph" in selected_methods:
        method_results["graph"] = graph_search(
            session,
            query,
            top_k=max(safe_top_k * 4, 25),
            entity_types=entity_types,
            cluster_id=cluster_id,
        )

    fused = _rrf(method_results, weights=weights or {})
    results = fused[:safe_top_k]
    return {
        "results": results,
        "breakdown": {
            method: [
                {"id": row["id"], "rank": rank, "score": round(float(row["score"]), 6)}
                for rank, row in enumerate(method_results.get(method, []), start=1)
            ]
            for method in METHODS
        },
        "count": len(results),
        "mode": mode,
    }


def _rrf(
    method_results: dict[str, list[SearchResult]],
    *,
    weights: dict[str, float],
    k: int = 60,
) -> list[SearchResult]:
    by_id: dict[str, SearchResult] = {}
    breakdown: dict[str, dict[str, MethodBreakdown]] = defaultdict(dict)
    scores: dict[str, float] = defaultdict(float)
    for method, rows in method_results.items():
        weight = float(weights.get(method, 1.0))
        for rank, row in enumerate(rows, start=1):
            entity_id = row["id"]
            base: SearchResult = row.copy()
            base.pop("score", None)
            base.pop("methods", None)
            base.pop("breakdown", None)
            by_id.setdefault(entity_id, base)
            breakdown[entity_id][method] = {
                "rank": rank,
                "score": round(float(row["score"]), 6),
            }
            scores[entity_id] += weight * (1.0 / (k + rank))

    fused: list[SearchResult] = []
    for entity_id, base in by_id.items():
        methods = sorted(breakdown[entity_id], key=lambda name: METHODS.index(name))
        fused.append(
            {
                **base,
                "score": round(scores[entity_id], 6),
                "methods": methods,
                "breakdown": breakdown[entity_id],
            }
        )
    fused.sort(
        key=lambda item: (
            -float(item["score"]),
            -len(item["methods"]),
            str(item["title"]).casefold(),
        )
    )
    return fused


def _result(entity: Entity, *, score: float, method: str) -> SearchResult:
    return {
        "id": entity.id,
        "type": entity.type,
        "title": title_for_entity(entity),
        "data": entity.data or {},
        "source_id": entity.source_id,
        "cluster_id": entity.cluster_id,
        "composite_importance": float(entity.composite_importance or 0.0),
        "score": round(float(score), 6),
        "methods": [method],
        "breakdown": {method: {"rank": 1, "score": round(float(score), 6)}},
    }


def _filtered_entities(
    session: Session,
    *,
    entity_types: list[str] | None,
    cluster_id: str | None,
) -> list[Entity]:
    stmt = select(Entity)
    if entity_types:
        stmt = stmt.where(Entity.type.in_(entity_types))
    if cluster_id is not None:
        stmt = stmt.where(Entity.cluster_id == cluster_id)
    return list(session.execute(stmt).scalars().all())


def _connection_counts(session: Session) -> Counter[str]:
    counts: Counter[str] = Counter()
    for edge in session.execute(select(Edge)).scalars().all():
        counts[edge.source_id] += 1
        counts[edge.target_id] += 1
    return counts


def _text_score(query: str, entity: Entity) -> float:
    q = query.casefold().strip()
    if not q or len(q) <= 3:
        return 0.0
    haystack = " ".join(str(value) for value in (entity.data or {}).values()).casefold()
    if q in haystack:
        return 0.76
    tokens = [token for token in q.split() if token]
    if tokens and all(token in haystack for token in tokens):
        return 0.68
    return 0.0


def _safe_limit(top_k: int) -> int:
    return min(max(int(top_k), 1), 50)


def _empty_breakdown() -> dict[str, list[dict[str, Any]]]:
    return {method: [] for method in METHODS}
