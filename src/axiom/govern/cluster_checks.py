from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, asc, desc, func, inspect, select
from sqlalchemy.orm import Session

from axiom.organize.cluster_health import ClusterHealthSnapshot
from axiom.organize.clusters import CLUSTER_IDS
from axiom.schema.models import ClusterCheckRun
from axiom.storage.db import create_schema_table

SEVERITIES = ("healthy", "degraded", "critical")


def ensure_cluster_check_runs_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("cluster_check_runs"):
        create_schema_table(ClusterCheckRun.__table__, engine)


def retention_limit_from_env() -> int:
    raw = os.environ.get("AXIOM_CHECK_RETENTION", "10000")
    try:
        return int(raw)
    except ValueError:
        return 10000


def _reason_for(item: ClusterHealthSnapshot) -> str:
    if item.status.value == "healthy":
        return "recent ingest volume is healthy"
    if item.status.value == "degraded":
        return "recent ingest volume is below healthy threshold"
    return "no recent ingest observed"


def cluster_check_run_row(row: ClusterCheckRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_at": row.run_at.isoformat(),
        "cluster_id": row.cluster_id,
        "check_type": row.check_type,
        "severity": row.severity,
        "entity_count": row.entity_count,
        "last_ingest_at": row.last_ingest_at.isoformat() if row.last_ingest_at else None,
        "owner": row.owner,
        "reason": row.reason,
    }


def record_cluster_check_runs(
    session: Session,
    snapshot: dict[str, ClusterHealthSnapshot],
    *,
    run_at: datetime | None = None,
) -> int:
    observed_at = run_at or datetime.utcnow()
    for item in snapshot.values():
        session.add(
            ClusterCheckRun(
                run_at=observed_at,
                cluster_id=item.cluster_id,
                check_type="cluster_health",
                severity=item.status.value,
                entity_count=item.total_entities,
                last_ingest_at=item.last_ingest_at,
                owner="organizer",
                reason=_reason_for(item),
            )
        )
    session.commit()
    return len(snapshot)


def cleanup_cluster_check_runs(session: Session, retention_limit: int | None = None) -> int:
    limit = retention_limit_from_env() if retention_limit is None else retention_limit
    if limit <= 0:
        return 0
    total = int(session.execute(select(func.count(ClusterCheckRun.id))).scalar_one())
    overflow = total - limit
    if overflow <= 0:
        return 0

    stale_ids = [
        row[0]
        for row in session.execute(
            select(ClusterCheckRun.id)
            .order_by(asc(ClusterCheckRun.run_at), asc(ClusterCheckRun.id))
            .limit(overflow)
        ).all()
    ]
    for row_id in stale_ids:
        row = session.get(ClusterCheckRun, row_id)
        if row is not None:
            session.delete(row)
    session.commit()
    return len(stale_ids)


def get_cluster_check_runs(
    session: Session,
    *,
    cluster: str | None = None,
    severity: str | None = None,
    limit: int = 200,
) -> list[ClusterCheckRun]:
    query = select(ClusterCheckRun)
    if cluster:
        query = query.where(ClusterCheckRun.cluster_id == cluster)
    if severity:
        query = query.where(ClusterCheckRun.severity == severity)
    bounded_limit = max(1, min(limit, 1000))
    return list(
        session.execute(
            query.order_by(desc(ClusterCheckRun.run_at), desc(ClusterCheckRun.id)).limit(
                bounded_limit
            )
        )
        .scalars()
        .all()
    )


def summarize_cluster_check_runs(session: Session) -> dict[str, dict[str, Any]]:
    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        session.execute(
            select(ClusterCheckRun)
            .where(ClusterCheckRun.run_at >= since)
            .order_by(ClusterCheckRun.cluster_id, ClusterCheckRun.run_at, ClusterCheckRun.id)
        )
        .scalars()
        .all()
    )
    by_cluster: dict[str, list[ClusterCheckRun]] = {cluster_id: [] for cluster_id in CLUSTER_IDS}
    for row in rows:
        by_cluster.setdefault(row.cluster_id, []).append(row)

    summary: dict[str, dict[str, Any]] = {}
    for cluster_id, cluster_rows in by_cluster.items():
        total = len(cluster_rows)
        counts = dict.fromkeys(SEVERITIES, 0)
        last_change_at: datetime | None = None
        previous: str | None = None
        for row in cluster_rows:
            if row.severity in counts:
                counts[row.severity] += 1
            if previous is None or row.severity != previous:
                last_change_at = row.run_at
            previous = row.severity

        pct = {
            f"{severity}_pct": (counts[severity] / total) * 100.0 if total else 0.0
            for severity in SEVERITIES
        }
        summary[cluster_id] = {
            **pct,
            "last_change_at": last_change_at.isoformat() if last_change_at else None,
            "total_runs": total,
        }
    return summary
