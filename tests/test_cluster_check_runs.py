from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.cluster_checks import (
    cleanup_cluster_check_runs,
    get_cluster_check_runs,
    record_cluster_check_runs,
    summarize_cluster_check_runs,
)
from axiom.organize.cluster_health import ClusterHealth, ClusterHealthSnapshot
from axiom.organize.clusters import CLUSTER_IDS
from axiom.schema.models import Base, ClusterCheckRun
from axiom.studio.server import create_app


def _snapshot(status: ClusterHealth = ClusterHealth.CRITICAL) -> dict[str, ClusterHealthSnapshot]:
    return {
        cluster_id: ClusterHealthSnapshot(
            cluster_id=cluster_id,
            status=status,
            ingest_rate_per_min=0.0,
            last_ingest_at=None,
            total_entities=0,
        )
        for cluster_id in CLUSTER_IDS
    }


def _db(tmp_path: Path, name: str = "cluster_checks.db") -> tuple[str, sessionmaker[Session]]:
    db_url = f"sqlite:///{tmp_path / name}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()
    return db_url, sf


def test_record_cluster_check_runs_writes_one_row_per_cluster(db_session: Session) -> None:
    written = record_cluster_check_runs(db_session, _snapshot())

    rows = db_session.execute(select(ClusterCheckRun)).scalars().all()
    assert written == len(CLUSTER_IDS)
    assert len(rows) == len(CLUSTER_IDS)
    assert {row.cluster_id for row in rows} == set(CLUSTER_IDS)
    assert {row.check_type for row in rows} == {"cluster_health"}
    assert {row.owner for row in rows} == {"organizer"}


def test_cluster_checks_endpoint_filters_cluster_and_severity(tmp_path: Path) -> None:
    db_url, sf = _db(tmp_path)
    snapshot = _snapshot(ClusterHealth.HEALTHY)
    snapshot["billing_payments"] = ClusterHealthSnapshot(
        cluster_id="billing_payments",
        status=ClusterHealth.DEGRADED,
        ingest_rate_per_min=1.0,
        last_ingest_at=None,
        total_entities=1,
    )
    with sf() as session:
        record_cluster_check_runs(session, snapshot)

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get(
            "/api/internal/cluster-checks?cluster=billing_payments&severity=degraded"
        ).json()

    assert len(payload["checks"]) == 1
    assert payload["checks"][0]["cluster_id"] == "billing_payments"
    assert payload["checks"][0]["severity"] == "degraded"


def test_cluster_checks_summary_percentages_and_last_change(db_session: Session) -> None:
    first = datetime.utcnow() - timedelta(minutes=10)
    second = datetime.utcnow() - timedelta(minutes=5)
    old = datetime.utcnow() - timedelta(days=2)
    db_session.add_all(
        [
            ClusterCheckRun(
                id="old",
                run_at=old,
                cluster_id="billing_payments",
                check_type="cluster_health",
                severity="degraded",
                entity_count=0,
                last_ingest_at=None,
                owner="organizer",
                reason="old",
            ),
            ClusterCheckRun(
                id="first",
                run_at=first,
                cluster_id="billing_payments",
                check_type="cluster_health",
                severity="healthy",
                entity_count=3,
                last_ingest_at=first,
                owner="organizer",
                reason="ok",
            ),
            ClusterCheckRun(
                id="second",
                run_at=second,
                cluster_id="billing_payments",
                check_type="cluster_health",
                severity="critical",
                entity_count=0,
                last_ingest_at=None,
                owner="organizer",
                reason="bad",
            ),
        ]
    )
    db_session.commit()

    summary = summarize_cluster_check_runs(db_session)["billing_payments"]

    assert summary["total_runs"] == 2
    assert summary["healthy_pct"] == 50.0
    assert summary["critical_pct"] == 50.0
    assert summary["degraded_pct"] == 0.0
    assert summary["last_change_at"] == second.isoformat()


def test_cluster_check_retention_keeps_newest_rows(db_session: Session) -> None:
    now = datetime.utcnow()
    for index in range(5):
        db_session.add(
            ClusterCheckRun(
                id=f"run_{index}",
                run_at=now + timedelta(seconds=index),
                cluster_id="billing_payments",
                check_type="cluster_health",
                severity="critical",
                entity_count=0,
                last_ingest_at=None,
                owner="organizer",
                reason="test",
            )
        )
    db_session.commit()

    deleted = cleanup_cluster_check_runs(db_session, retention_limit=3)
    remaining = [
        row[0]
        for row in db_session.execute(
            select(ClusterCheckRun.id).order_by(ClusterCheckRun.run_at)
        ).all()
    ]

    assert deleted == 2
    assert remaining == ["run_2", "run_3", "run_4"]


def test_cluster_health_loop_records_all_clusters(tmp_path: Path) -> None:
    db_url, _sf = _db(tmp_path, "loop.db")
    app = create_app(db_url=db_url, enable_organizer=False)

    with TestClient(app):
        deadline = time.time() + 2.0
        rows = 0
        while time.time() < deadline:
            with app.state.SessionLocal() as session:
                rows = int(session.execute(select(func.count(ClusterCheckRun.id))).scalar_one())
            if rows >= len(CLUSTER_IDS):
                break
            time.sleep(0.05)

    assert rows >= len(CLUSTER_IDS)
