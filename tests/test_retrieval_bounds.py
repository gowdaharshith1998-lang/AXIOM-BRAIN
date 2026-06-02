"""Completion tests for bounded retrieval (DB-003 / P1-6).

``test_retrieval_bounded.py`` already proves the ``MAX_CANDIDATES`` cap is
applied. This file covers the remaining gaps:

* the capped candidate window is *importance-ordered*, so a high-importance
  entity is always retrieved even when the entity count exceeds the cap;
* ``_connection_counts`` pushes counting into SQL (a grouped ``COUNT(*)``
  restricted to the candidate ids) and returns results identical to the old
  full-table Python implementation on a small dataset;
* ``graph_search`` / ``_build_graph`` only scan edges touching the seed /
  candidate set, bounded by ``AXIOM_MAX_EDGE_SCAN``;
* the optional FTS5 keyword pushdown (``AXIOM_FTS_ENABLED``) creates and uses a
  contentless virtual table, falling back to the Python scan when off or
  unpopulated;
* ``api.search.search_entities`` applies the same cap + ordering treatment.

Network-free and deterministic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.api import search as api_search
from axiom.retrieval import search as search_mod
from axiom.retrieval.graph_rank import personalized_pagerank_search
from axiom.retrieval.search import (
    fts_candidate_ids,
    graph_search,
    lexical_search,
)
from axiom.schema.models import Base, Edge, Entity


class _Provider:
    """Deterministic embedding provider (no network)."""

    model = "test-embeddings"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture(autouse=True)
def _reset_fts_probe() -> Iterator[None]:
    """Reset the cached FTS5 capability probe around each test (isolation)."""

    search_mod._fts_supported = None
    try:
        yield
    finally:
        search_mod._fts_supported = None


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'bounds.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield sf
    finally:
        engine.dispose()


def _seed_entities(sf: sessionmaker[Session], count: int) -> None:
    with sf() as session:
        # Every title shares the "refund" token. Importance ascends with the
        # index so the very last entity is the single most important.
        session.add_all(
            [
                Entity(
                    id=f"e{i:04d}",
                    type="doc",
                    composite_importance=float(i),
                    data={"title": f"Refund Note {i}"},
                )
                for i in range(count)
            ]
        )
        session.commit()


# --- Importance-ordered candidate window --------------------------------------


def test_candidate_window_is_importance_ordered(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_mod, "MAX_CANDIDATES", 5)
    _seed_entities(session_factory, 50)

    with session_factory() as session:
        scanned = search_mod._filtered_entities(session, entity_types=None, cluster_id=None)

    assert len(scanned) == 5
    # Highest composite_importance first, capped to 5: e0049..e0045.
    assert [e.id for e in scanned] == [f"e{i:04d}" for i in range(49, 44, -1)]
    importances = [e.composite_importance for e in scanned]
    assert importances == sorted(importances, reverse=True)


def test_high_importance_entity_always_retrieved(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_mod, "MAX_CANDIDATES", 3)
    # 40 low-importance entities + 1 dominant one that must survive the cap.
    with session_factory() as session:
        session.add_all(
            Entity(
                id=f"low{i:03d}",
                type="doc",
                composite_importance=0.01,
                data={"title": f"Refund Note {i}"},
            )
            for i in range(40)
        )
        session.add(
            Entity(
                id="vip",
                type="doc",
                composite_importance=99.0,
                data={"title": "Refund VIP Note"},
            )
        )
        session.commit()

    with session_factory() as session:
        rows = lexical_search(session, "refund", top_k=10)

    assert "vip" in {row["id"] for row in rows}


# --- _connection_counts pushes counting into SQL ------------------------------


def _old_connection_counts(session: Session) -> Counter[str]:
    """The pre-DB-003 implementation: full edge scan in Python."""

    counts: Counter[str] = Counter()
    for edge in session.execute(select(Edge)).scalars().all():
        counts[edge.source_id] += 1
        counts[edge.target_id] += 1
    return counts


def _seed_graph(sf: sessionmaker[Session]) -> None:
    with sf() as session:
        session.add_all(
            [
                Entity(id="a", type="person", data={"title": "Alice"}),
                Entity(id="b", type="project", data={"title": "Beta"}),
                Entity(id="c", type="doc", data={"title": "Gamma"}),
                Entity(id="d", type="doc", data={"title": "Delta"}),
            ]
        )
        session.add_all(
            [
                Edge(id="x1", source_id="a", target_id="b", relationship="owns", data={}),
                Edge(id="x2", source_id="a", target_id="c", relationship="owns", data={}),
                Edge(id="x3", source_id="b", target_id="c", relationship="refs", data={}),
                Edge(id="x4", source_id="c", target_id="a", relationship="refs", data={}),
            ]
        )
        session.commit()


def test_connection_counts_matches_old_implementation(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    all_ids = {"a", "b", "c", "d"}
    with session_factory() as session:
        new_counts = search_mod._connection_counts(session, all_ids)
        old_counts = _old_connection_counts(session)

    # Restricted to the full id set, the new aggregate must equal the old
    # full-table Python scan exactly.
    assert dict(new_counts) == dict(old_counts)
    # Sanity: a has edges x1,x2 (out) + x4 (in) = 3; c has x2,x3 (in) + x4 (out) = 3.
    assert new_counts["a"] == 3
    assert new_counts["c"] == 3
    assert new_counts["b"] == 2
    assert new_counts.get("d", 0) == 0


def test_connection_counts_issues_group_by_query(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    bind = session_factory.kw["bind"]
    assert isinstance(bind, Engine)
    seen: list[str] = []

    @event.listens_for(bind, "before_cursor_execute")
    def _capture(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        seen.append(statement)

    try:
        with session_factory() as session:
            search_mod._connection_counts(session, {"a", "b", "c"})
    finally:
        event.remove(bind, "before_cursor_execute", _capture)

    edge_statements = [s for s in seen if "edges" in s.lower()]
    assert edge_statements, "expected at least one edge query"
    assert all("group by" in s.lower() for s in edge_statements), edge_statements
    # The old implementation issued a bare `SELECT ... FROM edges` with no
    # GROUP BY; the new one must never do that.
    assert not any("from edges" in s.lower() and "group by" not in s.lower() for s in seen), seen


def test_connection_counts_empty_id_set_is_noop(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    with session_factory() as session:
        assert search_mod._connection_counts(session, set()) == Counter()


# --- Bounded edge scans for graph search / PPR --------------------------------


def test_edges_touching_is_bounded(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_MAX_EDGE_SCAN", "2")
    _seed_graph(session_factory)
    with session_factory() as session:
        edges = search_mod._edges_touching(session, {"a", "b", "c"})
    assert len(edges) <= 2


def test_edges_touching_only_returns_incident_edges(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    with session_factory() as session:
        # Only edges with an endpoint == "b": x1 (a->b) and x3 (b->c).
        edges = search_mod._edges_touching(session, {"b"})
    assert {e.id for e in edges} == {"x1", "x3"}


def test_graph_search_does_not_full_scan_edges(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    bind = session_factory.kw["bind"]
    assert isinstance(bind, Engine)
    seen: list[str] = []

    @event.listens_for(bind, "before_cursor_execute")
    def _capture(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        seen.append(statement)

    try:
        with session_factory() as session:
            graph_search(session, "alice", top_k=5)
    finally:
        event.remove(bind, "before_cursor_execute", _capture)

    # Every edge query must be scoped (WHERE ... IN / GROUP BY), never a bare
    # full-table scan of `edges`.
    bare_edge_scans = [
        s
        for s in seen
        if "from edges" in s.lower() and "where" not in s.lower() and "group by" not in s.lower()
    ]
    assert not bare_edge_scans, bare_edge_scans


def test_ppr_still_surfaces_neighbors_with_bounded_scan(
    session_factory: sessionmaker[Session],
) -> None:
    # PPR's _build_graph now scans only edges touching the candidate set; the
    # graph signal must still propagate to neighbors.
    _seed_graph(session_factory)
    with session_factory() as session:
        results = personalized_pagerank_search(session, "alice", top_k=10)
    ids = {row["id"] for row in results}
    assert "a" in ids
    # b and c are reachable from seed a via x1 / x2.
    assert "b" in ids or "c" in ids


# --- Optional FTS5 keyword pushdown -------------------------------------------


def test_fts_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXIOM_FTS_ENABLED", raising=False)
    assert search_mod.fts_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_fts_flag_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("AXIOM_FTS_ENABLED", value)
    assert search_mod.fts_enabled() is True


def test_fts_candidate_ids_falls_back_when_table_missing(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_entities(session_factory, 5)
    # No table created -> None signals the caller to use the Python scan.
    with session_factory() as session:
        assert fts_candidate_ids(session, "refund", limit=10) is None


def test_fts_populate_and_query_path(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_entities(session_factory, 6)
    with session_factory() as session:
        # Reset the cached capability probe so the table can be built.
        search_mod._fts_supported = None
        written = search_mod._populate_entities_fts(
            session, list(session.execute(select(Entity)).scalars().all())
        )
        assert written == 6
        ids = fts_candidate_ids(session, "refund", limit=10)
    assert ids is not None
    # Every entity shares the "refund" token, so all are matched.
    assert ids == {f"e{i:04d}" for i in range(6)}


def test_fts_query_is_injection_safe(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_entities(session_factory, 3)
    with session_factory() as session:
        search_mod._fts_supported = None
        search_mod._populate_entities_fts(
            session, list(session.execute(select(Entity)).scalars().all())
        )
        # Punctuation that would be FTS5 syntax must not raise.
        result = fts_candidate_ids(session, 'refund" OR x:(', limit=10)
    assert result is not None


def test_lexical_search_uses_fts_when_enabled(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_FTS_ENABLED", "1")
    with session_factory() as session:
        session.add_all(
            [
                Entity(id="m1", type="doc", data={"title": "Refund handling guide"}),
                Entity(id="m2", type="doc", data={"title": "Vacation policy"}),
            ]
        )
        session.commit()
    with session_factory() as session:
        search_mod._fts_supported = None
        search_mod._populate_entities_fts(
            session, list(session.execute(select(Entity)).scalars().all())
        )
    with session_factory() as session:
        rows = lexical_search(session, "refund", top_k=10)
    ids = {row["id"] for row in rows}
    assert "m1" in ids
    assert "m2" not in ids


def test_lexical_search_falls_back_when_fts_unpopulated(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Flag on, but the table was never populated -> must still return matches
    # via the Python fallback rather than an empty result set.
    monkeypatch.setenv("AXIOM_FTS_ENABLED", "1")
    search_mod._fts_supported = None
    _seed_entities(session_factory, 4)
    with session_factory() as session:
        rows = lexical_search(session, "refund", top_k=10)
    assert rows, "FTS enabled but unpopulated must fall back to the Python scan"


# --- api.search.search_entities bounding --------------------------------------


def test_search_entities_candidate_scan_is_bounded(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_search, "MAX_CANDIDATES", 5)
    _seed_entities(session_factory, 30)
    bind = session_factory.kw["bind"]
    assert isinstance(bind, Engine)
    seen: list[str] = []

    @event.listens_for(bind, "before_cursor_execute")
    def _capture(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        seen.append(statement)

    try:
        with session_factory() as session:
            api_search.search_entities(session, "refund", limit=25)
    finally:
        event.remove(bind, "before_cursor_execute", _capture)

    # The entity scan must carry a LIMIT and an ORDER BY composite_importance.
    entity_scans = [s for s in seen if "from entities" in s.lower()]
    assert entity_scans
    assert all("limit" in s.lower() for s in entity_scans), entity_scans
    assert any("composite_importance" in s.lower() for s in entity_scans), entity_scans
    # No bare full edge scan.
    assert not any("from edges" in s.lower() and "group by" not in s.lower() for s in seen), seen


def test_search_entities_high_importance_survives_cap(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_search, "MAX_CANDIDATES", 3)
    with session_factory() as session:
        session.add_all(
            Entity(
                id=f"low{i:03d}",
                type="doc",
                composite_importance=0.01,
                data={"title": f"Refund {i}"},
            )
            for i in range(20)
        )
        session.add(
            Entity(
                id="vip",
                type="doc",
                composite_importance=50.0,
                data={"title": "Refund VIP"},
            )
        )
        session.commit()
    with session_factory() as session:
        rows = api_search.search_entities(session, "refund", limit=10)
    assert "vip" in {row["id"] for row in rows}


def test_search_entities_connection_counts_match_old(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_graph(session_factory)
    with session_factory() as session:
        new_counts = api_search._connection_counts(session, {"a", "b", "c", "d"})
        old_counts = _old_connection_counts(session)
    assert dict(new_counts) == dict(old_counts)
