from __future__ import annotations

import logging
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from sqlalchemy import func, nulls_last, or_, select
from sqlalchemy.orm import Session

from axiom.api.search import _score_title, title_for_entity
from axiom.retrieval.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    vector_from_blob,
)
from axiom.schema.models import Edge, Entity, EntityEmbedding

log = logging.getLogger("axiom.retrieval.search")

SearchMode = Literal["hybrid", "lexical", "semantic", "graph", "ppr"]
METHODS: tuple[str, ...] = ("lexical", "semantic", "graph")

# Upper bound on how many entity rows any single query will pull from the DB
# and score in Python (DB-003). The lexical/graph candidate scan and the
# semantic embedding scan are otherwise unbounded ``select(Entity)`` queries
# over the whole table, which does not scale. The candidate window is now
# ordered by ``composite_importance DESC, updated_at DESC`` (see
# ``_filtered_entities``) so that when the entity count exceeds this cap the
# most important / most recent rows are retained rather than an arbitrary set.
MAX_CANDIDATES = 2000


def _max_edge_scan() -> int:
    """Hard cap on how many edge rows any single query will scan (DB-003).

    ``_connection_counts`` / ``graph_search`` push counting and neighbor
    expansion into SQL restricted to the candidate id set, but a pathological
    candidate set could still touch a huge number of edges. This ceiling
    bounds that worst case; when it truncates we log a warning so the gap is
    visible rather than silent. Configurable via ``AXIOM_MAX_EDGE_SCAN``.
    """

    raw = os.environ.get("AXIOM_MAX_EDGE_SCAN")
    if raw is None:
        return 20000
    try:
        value = int(raw)
    except ValueError:
        return 20000
    return value if value > 0 else 20000


# --- Optional FTS5 keyword pushdown (DB-003) ---------------------------------
#
# When ``AXIOM_FTS_ENABLED`` is truthy and the active sqlite build supports
# FTS5, lexical candidate selection can be pushed into SQL via a contentless
# ``entities_fts`` virtual table instead of pulling the whole capped window
# into Python. The flag defaults OFF so production behavior is unchanged until
# explicitly opted in; the Python scorer in ``lexical_search`` remains the
# fallback and the final ranker either way.
#
# STATUS: the feature flag, capability probe, table creation, and the
# MATCH-based query path are implemented and tested. POPULATION of the
# virtual table from a live brain (keeping it in sync as entities change) is
# DEFERRED — there is no owned write/ingest path here to hook into. As a
# result, with an unpopulated table ``fts_candidate_ids`` returns an empty set
# and ``_lexical_candidates`` degrades to the importance-ordered scan. A
# caller (or a future ingest hook) that populates ``entities_fts`` makes the
# pushdown active; ``_populate_entities_fts`` below is provided so tests and
# such callers can build the table from the current entity set.

_FTS_TABLE = "entities_fts"
_fts_supported: bool | None = None


def fts_enabled() -> bool:
    """Whether the FTS5 keyword pushdown is opted in via ``AXIOM_FTS_ENABLED``."""

    raw = os.environ.get("AXIOM_FTS_ENABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _raw_sqlite(session: Session) -> Any:
    """Return the underlying DBAPI (sqlite3) connection for ``session``.

    Raises if the driver connection is absent so callers' ``try/except`` blocks
    fall back to the Python scan rather than dereferencing ``None``.
    """

    driver = session.connection().connection.driver_connection
    if driver is None:  # pragma: no cover - sqlite always exposes a connection
        raise RuntimeError("no DBAPI connection available")
    return driver


def _sqlite_supports_fts5(session: Session) -> bool:
    """Probe (and cache) whether the bound sqlite build has FTS5 compiled in."""

    global _fts_supported
    if _fts_supported is not None:
        return _fts_supported
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        _fts_supported = False
        return False
    try:
        cur = _raw_sqlite(session).cursor()
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _axiom_fts_probe USING fts5(x)")
        cur.execute("DROP TABLE IF EXISTS _axiom_fts_probe")
        _fts_supported = True
    except Exception:  # noqa: BLE001 - any failure means FTS5 is unavailable
        log.debug("sqlite build does not support FTS5; keyword pushdown disabled", exc_info=True)
        _fts_supported = False
    return _fts_supported


def ensure_entities_fts(session: Session) -> bool:
    """Create the contentless ``entities_fts`` virtual table if needed.

    Returns True when the table exists and is usable after the call, False when
    FTS5 is unsupported or creation failed. Safe to call repeatedly.
    """

    if not _sqlite_supports_fts5(session):
        return False
    try:
        _raw_sqlite(session).cursor().execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS_TABLE} "
            "USING fts5(entity_id UNINDEXED, searchable)"
        )
        return True
    except Exception:  # noqa: BLE001 - fall back to Python scan on any failure
        log.warning("failed to create %s virtual table; FTS pushdown disabled", _FTS_TABLE)
        return False


def _populate_entities_fts(session: Session, entities: list[Entity]) -> int:
    """Rebuild ``entities_fts`` from ``entities`` (population is otherwise deferred).

    Provided for tests and explicit callers; the live ingest population hook is
    not owned by this module (see module docstring). Returns the row count.
    """

    if not ensure_entities_fts(session):
        return 0
    from axiom.retrieval.embeddings import canonical_entity_text

    raw = _raw_sqlite(session)
    cur = raw.cursor()
    cur.execute(f"DELETE FROM {_FTS_TABLE}")
    rows = [(entity.id, canonical_entity_text(entity)) for entity in entities]
    cur.executemany(
        f"INSERT INTO {_FTS_TABLE}(entity_id, searchable) VALUES (?, ?)",
        rows,
    )
    raw.commit()
    return len(rows)


def _safe_fts_query(query: str) -> str:
    """Turn a raw user query into a safe FTS5 MATCH expression.

    Each whitespace token becomes a double-quoted prefix term ANDed together,
    which avoids FTS5 syntax injection from punctuation in the user string.
    """

    tokens = [token for token in query.replace('"', " ").split() if token]
    if not tokens:
        return ""
    return " ".join(f'"{token}"*' for token in tokens)


def fts_candidate_ids(session: Session, query: str, *, limit: int) -> set[str] | None:
    """Keyword candidate entity ids via FTS5, or None when unavailable.

    Returns ``None`` (caller should fall back to the Python scan) when FTS5 is
    unsupported or the virtual table is missing. Returns a possibly-empty set
    when the table exists but yields no/zero matches.
    """

    if not _sqlite_supports_fts5(session):
        return None
    match_expr = _safe_fts_query(query)
    if not match_expr:
        return None
    try:
        cur = _raw_sqlite(session).cursor()
        # An unpopulated (or missing) table means population is deferred; signal
        # the caller to fall back to the Python scan rather than returning an
        # empty match set that would hide real lexical hits.
        cur.execute(f"SELECT 1 FROM {_FTS_TABLE} LIMIT 1")
        if cur.fetchone() is None:
            return None
        cur.execute(
            f"SELECT entity_id FROM {_FTS_TABLE} WHERE {_FTS_TABLE} MATCH ? LIMIT ?",
            (match_expr, max(int(limit), 1)),
        )
        return {str(row[0]) for row in cur.fetchall()}
    except Exception:  # noqa: BLE001 - missing/empty table -> Python fallback
        log.debug("FTS query failed (table missing or unpopulated)", exc_info=True)
        return None


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
    entities = _lexical_candidates(session, q, entity_types=entity_types, cluster_id=cluster_id)
    connection_counts = _connection_counts(session, {entity.id for entity in entities})
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
    # Order so the MAX_CANDIDATES cap retains the most important / recent
    # embedded entities rather than an arbitrary window (DB-003).
    stmt = stmt.order_by(
        nulls_last(Entity.composite_importance.desc()),
        Entity.updated_at.desc(),
    ).limit(MAX_CANDIDATES)
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
    # Only edges that touch a seed on either endpoint can contribute, so
    # restrict the scan to the seed set instead of loading the whole edge table
    # (127k rows in the live DB). Bounded by AXIOM_MAX_EDGE_SCAN (DB-003).
    edges = _edges_touching(session, seed_ids)
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
    if mode not in {"hybrid", "lexical", "semantic", "graph", "ppr"}:
        raise ValueError("mode must be one of hybrid, lexical, semantic, graph, ppr")
    safe_top_k = _safe_limit(top_k)
    if not query.strip():
        return {"results": [], "breakdown": _empty_breakdown(), "count": 0, "mode": mode}

    if mode == "ppr":
        # Lazy import keeps graph_rank's dependency on this module one-directional.
        from axiom.retrieval.graph_rank import personalized_pagerank_search

        ppr_results = personalized_pagerank_search(
            session,
            query,
            top_k=safe_top_k,
            entity_types=entity_types,
            cluster_id=cluster_id,
            provider=provider,
        )
        return {
            "results": ppr_results,
            "breakdown": _empty_breakdown(),
            "count": len(ppr_results),
            "mode": mode,
        }

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


def _lexical_candidates(
    session: Session,
    query: str,
    *,
    entity_types: list[str] | None,
    cluster_id: str | None,
) -> list[Entity]:
    """Candidate entities for lexical scoring.

    When the FTS5 pushdown is enabled and supported (``AXIOM_FTS_ENABLED``),
    keyword candidates are fetched in SQL via the ``entities_fts`` virtual
    table — only matching rows are pulled into Python instead of the whole
    capped window. The match set is still scored and ranked in Python (FTS5 is
    a recall filter, not the final ranker). Any failure, or the flag being off,
    degrades to the importance-ordered ``_filtered_entities`` scan, so behavior
    is unchanged when the feature is not active.
    """

    if fts_enabled():
        candidate_ids = fts_candidate_ids(session, query, limit=MAX_CANDIDATES)
        if candidate_ids is not None:
            if not candidate_ids:
                return []
            stmt = select(Entity).where(Entity.id.in_(candidate_ids))
            if entity_types:
                stmt = stmt.where(Entity.type.in_(entity_types))
            if cluster_id is not None:
                stmt = stmt.where(Entity.cluster_id == cluster_id)
            stmt = stmt.order_by(
                nulls_last(Entity.composite_importance.desc()),
                Entity.updated_at.desc(),
            ).limit(MAX_CANDIDATES)
            return list(session.execute(stmt).scalars().all())
    return _filtered_entities(session, entity_types=entity_types, cluster_id=cluster_id)


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
    # When the entity count exceeds MAX_CANDIDATES the LIMIT would otherwise
    # keep an arbitrary window. Order so the cap retains the most important and
    # most recent entities (DB-003): highest composite_importance first (nulls
    # last), then most recently updated.
    stmt = stmt.order_by(
        nulls_last(Entity.composite_importance.desc()),
        Entity.updated_at.desc(),
    ).limit(MAX_CANDIDATES)
    return list(session.execute(stmt).scalars().all())


def _edges_touching(session: Session, entity_ids: set[str]) -> list[Edge]:
    """Load only edges with an endpoint in ``entity_ids``, capped for safety.

    Replaces a full ``select(Edge)`` scan (DB-003). The result is bounded by
    ``_max_edge_scan()``; a warning is logged when the cap truncates so the
    silent gap is visible.
    """

    if not entity_ids:
        return []
    cap = _max_edge_scan()
    stmt = (
        select(Edge)
        .where(or_(Edge.source_id.in_(entity_ids), Edge.target_id.in_(entity_ids)))
        .limit(cap)
    )
    edges = list(session.execute(stmt).scalars().all())
    if len(edges) >= cap:
        log.warning(
            "edge scan hit AXIOM_MAX_EDGE_SCAN cap (%d edges for %d seeds); "
            "graph expansion may be truncated",
            cap,
            len(entity_ids),
        )
    return edges


def _connection_counts(session: Session, entity_ids: set[str] | None = None) -> Counter[str]:
    """Count edges incident to each entity, pushing the aggregation into SQL.

    Previously this loaded *every* edge row (127k in the live DB) on every
    query. It now runs two grouped ``COUNT(*)`` aggregates restricted to the
    candidate ``entity_ids`` (DB-003), so only counts for entities we actually
    score are computed. ``entity_ids=None`` preserves the old whole-graph
    behavior for callers that need it. Each grouped scan is bounded by
    ``_max_edge_scan()``; a warning is logged when the cap truncates.
    """

    counts: Counter[str] = Counter()
    cap = _max_edge_scan()
    for column in (Edge.source_id, Edge.target_id):
        stmt = select(column, func.count()).group_by(column)
        if entity_ids is not None:
            if not entity_ids:
                continue
            stmt = stmt.where(column.in_(entity_ids))
        stmt = stmt.limit(cap)
        rows = session.execute(stmt).all()
        if len(rows) >= cap:
            log.warning(
                "edge-count scan hit AXIOM_MAX_EDGE_SCAN cap (%d groups on %s); "
                "connection counts may be truncated",
                cap,
                column.key,
            )
        for entity_id, count in rows:
            counts[entity_id] += int(count)
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
