from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import func, nulls_last, select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity

# Hard ceiling on how many entity rows ``search_entities`` pulls into Python to
# score per call (DB-003). Mirrors ``retrieval.search.MAX_CANDIDATES`` but is
# defined locally to avoid a circular import (``retrieval.search`` imports from
# this module). The candidate window is importance-ordered so the cap keeps the
# most important / recent entities rather than an arbitrary set.
MAX_CANDIDATES = 2000


class EntitySearchResult(TypedDict):
    id: str
    type: str
    title: str
    connection_count: int


@dataclass(frozen=True)
class _RankedEntity:
    score: float
    connection_count: int
    title: str
    entity: Entity


TITLE_KEYS = ("title", "name", "subject", "label")


def title_for_entity(entity: Entity) -> str:
    for key in TITLE_KEYS:
        value = entity.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity.id


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if ca == cb else 1),
                )
            )
        previous = current
    return previous[-1]


def _score_title(query: str, title: str) -> float:
    q = query.casefold().strip()
    t = title.casefold().strip()
    if not q:
        return 0.0

    if len(q) <= 3:
        return 1.0 if t.startswith(q) else 0.0

    if t == q:
        return 1.0
    if t.startswith(q):
        return 0.96
    if q in t:
        return 0.86 - min(t.index(q), 40) / 400

    words = [word for word in t.replace("(", " ").replace(")", " ").split() if word]
    candidates = words + [t]
    best_distance = min(_levenshtein(q, candidate[: len(q) + 2]) for candidate in candidates)
    max_len = max(len(q), 1)
    similarity = 1 - best_distance / max_len
    return max(0.0, similarity * 0.75)


def _connection_counts(session: Session, entity_ids: set[str]) -> Counter[str]:
    """Edges incident to each candidate entity, aggregated in SQL (DB-003).

    Two grouped ``COUNT(*)`` queries restricted to ``entity_ids`` replace a
    full ``select(Edge)`` scan, so only counts for entities we actually score
    are computed.
    """

    counts: Counter[str] = Counter()
    if not entity_ids:
        return counts
    for column in (Edge.source_id, Edge.target_id):
        rows = session.execute(
            select(column, func.count()).where(column.in_(entity_ids)).group_by(column)
        ).all()
        for entity_id, count in rows:
            counts[entity_id] += int(count)
    return counts


def search_entities(session: Session, query: str, *, limit: int = 8) -> list[EntitySearchResult]:
    q = query.strip()
    if not q:
        return []

    safe_limit = min(max(limit, 1), 25)
    # Bound the candidate scan and order it so the cap retains the most
    # important / recent entities rather than an arbitrary window (DB-003).
    entities = list(
        session.execute(
            select(Entity)
            .order_by(
                nulls_last(Entity.composite_importance.desc()),
                Entity.updated_at.desc(),
            )
            .limit(MAX_CANDIDATES)
        )
        .scalars()
        .all()
    )
    # Count edges incident to only the candidate entities, pushing the
    # aggregation into SQL instead of loading the whole edge table (DB-003).
    connection_counts = _connection_counts(session, {entity.id for entity in entities})

    ranked: list[_RankedEntity] = []
    for entity in entities:
        title = title_for_entity(entity)
        score = _score_title(q, title)
        if score <= 0:
            continue
        connections = connection_counts[entity.id]
        ranked.append(
            _RankedEntity(
                score=score,
                connection_count=connections,
                title=title,
                entity=entity,
            )
        )

    ranked.sort(key=lambda item: (-item.score, -item.connection_count, item.title.casefold()))
    return [
        {
            "id": item.entity.id,
            "type": item.entity.type,
            "title": item.title,
            "connection_count": item.connection_count,
        }
        for item in ranked[:safe_limit]
    ]
