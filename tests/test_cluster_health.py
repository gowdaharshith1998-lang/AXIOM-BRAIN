from __future__ import annotations

from datetime import datetime, timedelta

from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from axiom.organize.cluster_health import (
    ClusterHealth,
    ClusterHealthMonitor,
    compute_brain_health_score,
    health_status_for_score,
)
from axiom.schema.models import Entity


def _entity(cluster_id: str, created_at: datetime) -> Entity:
    return Entity(
        type="thread",
        data={},
        source_id=None,
        created_at=created_at,
        updated_at=created_at,
        cluster_id=cluster_id,
        composite_importance=0.5,
    )


def test_cluster_health_healthy_with_three_recent_entities(db_session: Session) -> None:
    now = datetime.utcnow()
    db_session.add_all([_entity("billing_payments", now - timedelta(seconds=i)) for i in range(3)])
    db_session.commit()

    snapshot = ClusterHealthMonitor().snapshot(db_session)

    assert snapshot["billing_payments"].status is ClusterHealth.HEALTHY
    assert snapshot["billing_payments"].ingest_rate_per_min == 3.0


def test_cluster_health_degraded_with_one_recent_entity(db_session: Session) -> None:
    db_session.add(_entity("incidents_ops", datetime.utcnow()))
    db_session.commit()

    snapshot = ClusterHealthMonitor().snapshot(db_session)

    assert snapshot["incidents_ops"].status is ClusterHealth.DEGRADED


def test_cluster_health_critical_with_no_recent_entities(db_session: Session) -> None:
    db_session.add(_entity("engineering_code", datetime.utcnow() - timedelta(minutes=5)))
    db_session.commit()

    snapshot = ClusterHealthMonitor().snapshot(db_session)

    assert snapshot["engineering_code"].status is ClusterHealth.CRITICAL


def test_cluster_health_env_override(monkeypatch: MonkeyPatch, db_session: Session) -> None:
    db_session.add_all([_entity("billing_payments", datetime.utcnow()) for _ in range(4)])
    db_session.commit()
    monkeypatch.setenv("AXIOM_DEMO_FORCE_HEALTH_billing_payments", "critical")

    snapshot = ClusterHealthMonitor().snapshot(db_session)

    assert snapshot["billing_payments"].status is ClusterHealth.CRITICAL


def test_brain_health_score_full_healthy_state() -> None:
    score = compute_brain_health_score(
        classified_pct=100.0,
        events_per_min=190.0,
        fps=60.0,
        clusters_present=8,
        total_clusters=8,
    )
    assert score >= 0.85
    assert health_status_for_score(score) is ClusterHealth.HEALTHY


def test_brain_health_score_zero_events_is_critical() -> None:
    score = compute_brain_health_score(
        classified_pct=100.0,
        events_per_min=0.0,
        fps=60.0,
        clusters_present=8,
        total_clusters=8,
    )
    assert score < 0.60
    assert health_status_for_score(score) is ClusterHealth.CRITICAL


def test_brain_health_score_half_classified_is_degraded() -> None:
    score = compute_brain_health_score(
        classified_pct=50.0,
        events_per_min=190.0,
        fps=60.0,
        clusters_present=8,
        total_clusters=8,
    )
    assert 0.60 <= score < 0.85
    assert health_status_for_score(score) is ClusterHealth.DEGRADED
