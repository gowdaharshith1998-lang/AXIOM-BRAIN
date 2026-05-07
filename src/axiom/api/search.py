from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity


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


def search_entities(session: Session, query: str, *, limit: int = 8) -> list[EntitySearchResult]:
    q = query.strip()
    if not q:
        return []

    safe_limit = min(max(limit, 1), 25)
    entities = session.execute(select(Entity)).scalars().all()
    edges = session.execute(select(Edge)).scalars().all()
    connection_counts: Counter[str] = Counter()
    for edge in edges:
        connection_counts[edge.source_id] += 1
        connection_counts[edge.target_id] += 1

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
