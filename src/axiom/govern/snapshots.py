from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Engine, distinct, func, inspect, select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity, MetricsSnapshot, Receipt


def ensure_snapshots_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("metrics_snapshots"):
        MetricsSnapshot.__table__.create(bind=engine, checkfirst=True)


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
