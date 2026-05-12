from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Engine, distinct, func, inspect, select
from sqlalchemy.orm import Session

from axiom.organize.cluster_health import compute_brain_health_score
from axiom.organize.clusters import CLUSTER_IDS
from axiom.schema.models import Edge, Entity, MetricsSnapshot, Receipt
from axiom.storage.db import create_schema_table


def ensure_snapshots_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("metrics_snapshots"):
        create_schema_table(MetricsSnapshot.__table__, engine)
        return
    columns = {column["name"] for column in inspector.get_columns("metrics_snapshots")}
    if "brain_health_score" not in columns:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE metrics_snapshots "
                "ADD COLUMN brain_health_score FLOAT NOT NULL DEFAULT 0.0"
            )


def _day_bounds(snapshot_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(snapshot_date, time.min)
    return start, start + timedelta(days=1)


def _count_before(session: Session, model: type[Any], cutoff: datetime) -> int:
    return int(
        session.execute(select(func.count(model.id)).where(model.created_at < cutoff)).scalar_one()
    )


def _decision_count_before(session: Session, decision: str, cutoff: datetime) -> int:
    return int(
        session.execute(
            select(func.count(Receipt.id)).where(
                Receipt.created_at < cutoff,
                Receipt.decision == decision,
            )
        ).scalar_one()
    )


def _agent_count_for_day(session: Session, snapshot_date: date) -> int:
    start, end = _day_bounds(snapshot_date)
    return int(
        session.execute(
            select(func.count(distinct(Receipt.agent_name))).where(
                Receipt.created_at >= start,
                Receipt.created_at < end,
            )
        ).scalar_one()
    )


def _classified_pct_before(session: Session, cutoff: datetime, entity_count: int) -> float:
    if entity_count <= 0:
        return 0.0
    classified_count = int(
        session.execute(
            select(func.count(Entity.id)).where(
                Entity.created_at < cutoff,
                Entity.composite_importance > 0.0,
            )
        ).scalar_one()
    )
    return (classified_count / entity_count) * 100.0


def _clusters_present_before(session: Session, cutoff: datetime) -> int:
    return int(
        session.execute(
            select(func.count(distinct(Entity.cluster_id))).where(
                Entity.created_at < cutoff,
                Entity.cluster_id.is_not(None),
            )
        ).scalar_one()
    )


def _events_per_min_before(session: Session, cutoff: datetime) -> float:
    start = cutoff - timedelta(seconds=60)
    return float(
        session.execute(
            select(func.count(Receipt.id)).where(
                Receipt.created_at >= start,
                Receipt.created_at < cutoff,
            )
        ).scalar_one()
    )


def _brain_health_score(session: Session, cutoff: datetime, entity_count: int) -> float:
    return compute_brain_health_score(
        classified_pct=_classified_pct_before(session, cutoff, entity_count),
        events_per_min=_events_per_min_before(session, cutoff),
        fps=float(os.environ.get("AXIOM_TARGET_FPS", "60")),
        clusters_present=_clusters_present_before(session, cutoff),
        total_clusters=len(CLUSTER_IDS),
    )


def _write_snapshot(session: Session, snapshot_date: date, cutoff: datetime) -> MetricsSnapshot:
    snapshot_id = snapshot_date.isoformat()
    snapshot = session.get(MetricsSnapshot, snapshot_id)
    if snapshot is None:
        snapshot = MetricsSnapshot(id=snapshot_id, snapshot_date=snapshot_date)

    snapshot.entity_count = _count_before(session, Entity, cutoff)
    snapshot.edge_count = _count_before(session, Edge, cutoff)
    snapshot.receipt_count = _count_before(session, Receipt, cutoff)
    snapshot.allow_count = _decision_count_before(session, "allow", cutoff)
    snapshot.correct_count = _decision_count_before(session, "correct", cutoff)
    snapshot.deny_count = _decision_count_before(session, "deny", cutoff)
    snapshot.agent_count = _agent_count_for_day(session, snapshot_date)
    snapshot.brain_health_score = _brain_health_score(session, cutoff, snapshot.entity_count)
    snapshot.created_at = datetime.utcnow()

    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def take_snapshot(session: Session) -> MetricsSnapshot:
    now = datetime.utcnow()
    today = now.date()
    return _write_snapshot(session, today, now + timedelta(microseconds=1))


def get_snapshots(session: Session, days: int = 30) -> list[MetricsSnapshot]:
    bounded_days = max(1, min(days, 365))
    rows = (
        session.execute(
            select(MetricsSnapshot)
            .order_by(MetricsSnapshot.snapshot_date.desc())
            .limit(bounded_days)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def backfill_snapshots_from_receipts(session: Session) -> int:
    dates = [
        row[0]
        for row in session.execute(select(Receipt.created_at).order_by(Receipt.created_at)).all()
        if row[0] is not None
    ]
    snapshot_dates = sorted({created_at.date() for created_at in dates})
    today = datetime.utcnow().date()
    written = 0
    for snapshot_date in snapshot_dates:
        cutoff = datetime.utcnow() + timedelta(microseconds=1)
        if snapshot_date < today:
            _start, cutoff = _day_bounds(snapshot_date)
        _write_snapshot(session, snapshot_date, cutoff)
        written += 1
    return written
