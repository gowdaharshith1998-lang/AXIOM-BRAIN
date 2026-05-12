from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.organize.clusters import CLUSTER_IDS
from axiom.schema.models import Entity


class ClusterHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ClusterHealthSnapshot:
    cluster_id: str
    status: ClusterHealth
    ingest_rate_per_min: float
    last_ingest_at: datetime | None
    total_entities: int

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["last_ingest_at"] = self.last_ingest_at.isoformat() if self.last_ingest_at else None
        return payload


class ClusterHealthMonitor:
    def snapshot(self, session: Session) -> dict[str, ClusterHealthSnapshot]:
        now = datetime.utcnow()
        since_60 = now - timedelta(seconds=60)
        since_90 = now - timedelta(seconds=90)
        rows = session.execute(select(Entity)).scalars().all()
        output: dict[str, ClusterHealthSnapshot] = {}

        for cluster_id in CLUSTER_IDS:
            cluster_rows = [row for row in rows if row.cluster_id == cluster_id]
            recent_60 = [row for row in cluster_rows if row.created_at >= since_60]
            recent_90 = [row for row in cluster_rows if row.created_at >= since_90]
            last_ingest = max((row.created_at for row in cluster_rows), default=None)
            status = self._status_for(len(recent_60), len(recent_90))
            override = os.environ.get(f"AXIOM_DEMO_FORCE_HEALTH_{cluster_id}")
            if override in {item.value for item in ClusterHealth}:
                status = ClusterHealth(override)
            output[cluster_id] = ClusterHealthSnapshot(
                cluster_id=cluster_id,
                status=status,
                ingest_rate_per_min=float(len(recent_60)),
                last_ingest_at=last_ingest,
                total_entities=len(cluster_rows),
            )

        return output

    @staticmethod
    def _status_for(last_60_count: int, last_90_count: int) -> ClusterHealth:
        if last_60_count >= 3:
            return ClusterHealth.HEALTHY
        if last_60_count >= 1:
            return ClusterHealth.DEGRADED
        if last_90_count == 0:
            return ClusterHealth.CRITICAL
        return ClusterHealth.DEGRADED


def compute_brain_health_score(
    *,
    classified_pct: float,
    events_per_min: float,
    fps: float,
    clusters_present: int,
    total_clusters: int,
) -> float:
    """
    Composite score in [0, 1].
    Formula:
      0.40 * classified_ratio + 0.35 * events_component
      + 0.15 * fps_component + 0.10 * cluster_coverage
    with a hard idle-penalty of -0.15 when events_per_min <= 0.
    """
    classified_ratio = min(max(classified_pct / 100.0, 0.0), 1.0)
    events_component = 1.0 if events_per_min > 0 else 0.0
    fps_component = min(max(fps / 50.0, 0.0), 1.0)
    coverage = (
        0.0 if total_clusters <= 0 else min(max(clusters_present / float(total_clusters), 0.0), 1.0)
    )
    score = (
        0.40 * classified_ratio + 0.35 * events_component + 0.15 * fps_component + 0.10 * coverage
    )
    if events_per_min <= 0:
        score -= 0.15
    return min(max(score, 0.0), 1.0)


def health_status_for_score(score: float) -> ClusterHealth:
    if score >= 0.85:
        return ClusterHealth.HEALTHY
    if score >= 0.60:
        return ClusterHealth.DEGRADED
    return ClusterHealth.CRITICAL
