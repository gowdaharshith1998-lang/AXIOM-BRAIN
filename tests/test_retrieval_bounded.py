"""Bounded-retrieval tests (DB-003).

The retriever historically issued unbounded ``select(Entity)`` queries and
scored the entire table in Python. ``MAX_CANDIDATES`` caps how many entity
rows any single query pulls and scores. These tests monkeypatch the cap to a
small value, seed more entities than that, and assert the cap is actually
applied to the lexical/graph candidate scan and the semantic embedding scan.

Network-free and deterministic.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.retrieval import search as search_mod
from axiom.retrieval.embeddings import embed_entities_batch
from axiom.retrieval.search import lexical_search, semantic_search
from axiom.schema.models import Base, Entity


class _Provider:
    """Deterministic embedding provider (no network)."""

    model = "test-embeddings"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'bounded.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield sf
    finally:
        engine.dispose()


def _seed(sf: sessionmaker[Session], count: int) -> None:
    with sf() as session:
        # Every title shares the "refund" token so, without a cap, the lexical
        # pre-filter would pull in (and score) every single row.
        session.add_all(
            [
                Entity(id=f"e{i}", type="doc", data={"title": f"Refund Note {i}"})
                for i in range(count)
            ]
        )
        session.commit()


def test_default_cap_is_large_enough_for_existing_callers() -> None:
    # The production default must not silently truncate small datasets.
    assert search_mod.MAX_CANDIDATES >= 2000


def test_lexical_scan_is_bounded_by_max_candidates(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_mod, "MAX_CANDIDATES", 5)
    _seed(session_factory, 20)

    # Spy on the candidate scan to assert at most MAX_CANDIDATES rows are
    # pulled into Python for scoring.
    original = search_mod._filtered_entities
    sizes: list[int] = []

    def _spy(session: Session, **kwargs: object) -> list[Entity]:
        rows = original(session, **kwargs)
        sizes.append(len(rows))
        return rows

    monkeypatch.setattr(search_mod, "_filtered_entities", _spy)

    with session_factory() as session:
        rows = lexical_search(session, "refund", top_k=50)

    assert sizes, "expected _filtered_entities to be invoked"
    assert all(size <= 5 for size in sizes), sizes
    # The scored/returned candidate set is likewise bounded.
    assert len(rows) <= 5


def test_filtered_entities_applies_limit_directly(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_mod, "MAX_CANDIDATES", 3)
    _seed(session_factory, 12)

    with session_factory() as session:
        scanned = search_mod._filtered_entities(
            session, entity_types=None, cluster_id=None
        )

    assert len(scanned) == 3


def test_semantic_scan_is_bounded_by_max_candidates(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_mod, "MAX_CANDIDATES", 4)
    _seed(session_factory, 15)

    provider = _Provider()
    with session_factory() as session:
        embed_entities_batch(
            session, session.execute(select(Entity)).scalars().all(), provider=provider
        )
        rows = semantic_search(session, "refund", top_k=50, provider=provider)

    # semantic_search joins entities to embeddings, limited to MAX_CANDIDATES,
    # so the result set can never exceed the cap.
    assert len(rows) <= 4
