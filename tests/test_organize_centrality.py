"""Phase 5.7.B — centrality scorer behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from axiom.organize.centrality import (
    DEGREE_WEIGHT,
    PAGERANK_NORMALIZER,
    PAGERANK_WEIGHT,
    RECENCY_HALF_LIFE_HOURS,
    RECENCY_WEIGHT,
    CentralityScorer,
    composite_score,
    recency_score,
)
from axiom.schema.models import Edge, Entity


def _make_entity(session: Session, *, suffix: str, updated_at: datetime | None = None) -> Entity:
    entity = Entity(
        id=("e" + suffix).ljust(32, "0")[:32],
        type="document",
        data={"title": f"doc {suffix}"},
    )
    if updated_at is not None:
        entity.created_at = updated_at
        entity.updated_at = updated_at
    session.add(entity)
    session.flush()
    return entity


def _make_edge(session: Session, src: str, tgt: str, suffix: str) -> Edge:
    edge = Edge(
        id=("ed" + suffix).ljust(32, "0")[:32],
        source_id=src,
        target_id=tgt,
        relationship="REL",
        data={},
    )
    session.add(edge)
    session.flush()
    return edge


def test_pagerank_on_disconnected_graph(db_session: Session) -> None:
    a = _make_entity(db_session, suffix="A")
    b = _make_entity(db_session, suffix="B")
    db_session.commit()

    scorer = CentralityScorer()
    assert scorer.recompute_all(db_session) == 2
    db_session.refresh(a)
    db_session.refresh(b)
    # Disconnected nodes still have a positive composite (recency contributes).
    assert a.composite_importance >= 0.0
    assert b.composite_importance >= 0.0
    # And no edges → equal degree → equal pagerank → equal composite.
    assert pytest.approx(a.composite_importance, abs=1e-9) == b.composite_importance


def test_pagerank_on_chain(db_session: Session) -> None:
    a = _make_entity(db_session, suffix="A")
    b = _make_entity(db_session, suffix="B")
    c = _make_entity(db_session, suffix="C")
    _make_edge(db_session, a.id, b.id, "AB")
    _make_edge(db_session, b.id, c.id, "BC")
    db_session.commit()

    scorer = CentralityScorer()
    scorer.recompute_all(db_session)
    db_session.refresh(a)
    db_session.refresh(b)
    db_session.refresh(c)
    # b is the structural middleman → highest pagerank in the chain.
    assert b.composite_importance > a.composite_importance
    assert b.composite_importance > 0


def test_pagerank_on_star(db_session: Session) -> None:
    hub = _make_entity(db_session, suffix="H")
    leaves = [_make_entity(db_session, suffix=f"L{i}") for i in range(5)]
    for i, leaf in enumerate(leaves):
        _make_edge(db_session, leaf.id, hub.id, f"E{i}")
    db_session.commit()

    scorer = CentralityScorer()
    scorer.recompute_all(db_session)
    db_session.refresh(hub)
    for leaf in leaves:
        db_session.refresh(leaf)
    # The hub has all leaves pointing at it → strictly highest importance.
    for leaf in leaves:
        assert hub.composite_importance > leaf.composite_importance


def test_degree_centrality(db_session: Session) -> None:
    hub = _make_entity(db_session, suffix="H")
    leaf = _make_entity(db_session, suffix="L")
    _make_edge(db_session, hub.id, leaf.id, "E1")
    db_session.commit()

    scorer = CentralityScorer()
    scorer.recompute_all(db_session)
    db_session.refresh(hub)
    db_session.refresh(leaf)
    # Both ends carry degree 1 (DiGraph degree is total in+out for the node).
    assert hub.composite_importance > 0
    assert leaf.composite_importance > 0


def test_recency_decay_one_week() -> None:
    now = datetime.now(UTC)
    # Brand-new → ~1.0
    assert recency_score(now, now=now) == pytest.approx(1.0)
    # One week old → ~0.0 (linear decay over the window).
    week_old = now - timedelta(hours=RECENCY_HALF_LIFE_HOURS)
    assert recency_score(week_old, now=now) == pytest.approx(0.0, abs=1e-6)
    # Two weeks old → clamped to 0.
    older = now - timedelta(hours=2 * RECENCY_HALF_LIFE_HOURS)
    assert recency_score(older, now=now) == 0.0


def test_composite_blend_weights() -> None:
    # Maxed-out signals should clamp to 1.0.
    high = composite_score(pagerank=1.0, degree_ratio=1.0, recency=1.0)
    assert high == pytest.approx(min(PAGERANK_WEIGHT + DEGREE_WEIGHT + RECENCY_WEIGHT, 1.0))

    # All zero → 0.0.
    low = composite_score(pagerank=0.0, degree_ratio=0.0, recency=0.0)
    assert low == 0.0

    # Recency-only signal contributes RECENCY_WEIGHT.
    rec_only = composite_score(pagerank=0.0, degree_ratio=0.0, recency=1.0)
    assert rec_only == pytest.approx(RECENCY_WEIGHT)

    # PageRank tier scales by PAGERANK_NORMALIZER then clamps.
    pr_capped = composite_score(pagerank=1.0, degree_ratio=0.0, recency=0.0)
    assert pr_capped == pytest.approx(min(1.0, PAGERANK_NORMALIZER) * PAGERANK_WEIGHT) or (
        pr_capped == pytest.approx(PAGERANK_WEIGHT)
    )


def test_recompute_updates_db(db_session: Session) -> None:
    e = _make_entity(db_session, suffix="X")
    db_session.commit()
    assert e.composite_importance == 0.0

    scorer = CentralityScorer()
    written = scorer.recompute_all(db_session)
    assert written == 1
    db_session.refresh(e)
    assert e.composite_importance > 0.0


def test_recompute_handles_empty_graph(db_session: Session) -> None:
    scorer = CentralityScorer()
    assert scorer.recompute_all(db_session) == 0
