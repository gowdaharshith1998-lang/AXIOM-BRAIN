from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.snapshots import backfill_snapshots_from_receipts, get_snapshots, take_snapshot
from axiom.schema.models import Base, Edge, Entity, MetricsSnapshot, Receipt
from axiom.studio.server import create_app


def _receipt(
    *,
    id_: str,
    action_id: str,
    agent_name: str,
    decision: str,
    created_at: datetime,
) -> Receipt:
    return Receipt(
        id=id_,
        action_id=action_id,
        agent_name=agent_name,
        intent="read",
        target_entity_id=None,
        cluster_id="engineering_code",
        decision=decision,
        reason="test",
        policy_id="policy.test",
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature=f"sig-{id_}",
        prev_hash=None,
        this_hash=f"hash-{id_}",
        demo_flag=True,
        created_at=created_at,
    )


def _session_factory(tmp_path: Path) -> tuple[str, sessionmaker[Session]]:
    db_url = f"sqlite:///{tmp_path / 'snapshots.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    return db_url, sessionmaker(bind=create_engine(db_url, future=True), future=True)


def test_snapshot_creates_row_for_today(db_session: Session) -> None:
    db_session.add(Entity(type="thread", data={"title": "T"}))
    db_session.add(
        _receipt(
            id_="r1",
            action_id="a1",
            agent_name="agent_a",
            decision="allow",
            created_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    snapshot = take_snapshot(db_session)

    assert snapshot.id == datetime.utcnow().date().isoformat()
    assert snapshot.entity_count == 1
    assert snapshot.receipt_count == 1
    assert snapshot.allow_count == 1
    assert snapshot.agent_count == 1


def test_snapshot_idempotent_within_same_day(db_session: Session) -> None:
    first = take_snapshot(db_session)
    second = take_snapshot(db_session)

    rows = db_session.execute(select(MetricsSnapshot)).scalars().all()
    assert len(rows) == 1
    assert first.id == second.id


def test_snapshot_respects_disabled_env_var(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_SNAPSHOT_ENABLED", "0")
    db_url, sf = _session_factory(tmp_path)
    with sf() as session:
        session.add(
            _receipt(
                id_="r1",
                action_id="a1",
                agent_name="agent_a",
                decision="allow",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/metrics-snapshots").json()
        assert payload["snapshots"] == []
        assert app.state.snapshot_task is None


def test_get_snapshots_returns_chronological(db_session: Session) -> None:
    for day in (date(2026, 5, 7), date(2026, 5, 8), date(2026, 5, 9)):
        db_session.add(
            MetricsSnapshot(
                id=day.isoformat(),
                snapshot_date=day,
                entity_count=0,
                edge_count=0,
                receipt_count=0,
                allow_count=0,
                correct_count=0,
                deny_count=0,
                agent_count=0,
                created_at=datetime.utcnow(),
            )
        )
    db_session.commit()

    rows = get_snapshots(db_session, days=2)

    assert [row.id for row in rows] == ["2026-05-08", "2026-05-09"]


def test_backfill_from_receipts_creates_per_day_rows(db_session: Session) -> None:
    db_session.add(
        Entity(id="e1", type="thread", data={}, created_at=datetime(2026, 5, 7, 9, 0, 0))
    )
    db_session.add(
        Entity(id="e2", type="thread", data={}, created_at=datetime(2026, 5, 9, 9, 0, 0))
    )
    db_session.add(
        Edge(
            id="edge1",
            source_id="e1",
            target_id="e2",
            relationship="mentions",
            created_at=datetime(2026, 5, 8, 9, 0, 0),
        )
    )
    db_session.add(
        _receipt(
            id_="r1",
            action_id="a1",
            agent_name="agent_a",
            decision="allow",
            created_at=datetime(2026, 5, 8, 10, 0, 0),
        )
    )
    db_session.add(
        _receipt(
            id_="r2",
            action_id="a2",
            agent_name="agent_b",
            decision="deny",
            created_at=datetime(2026, 5, 9, 10, 0, 0),
        )
    )
    db_session.commit()

    written = backfill_snapshots_from_receipts(db_session)
    rows = {row.id: row for row in get_snapshots(db_session, days=30)}

    assert written == 2
    assert rows["2026-05-08"].entity_count == 1
    assert rows["2026-05-08"].edge_count == 1
    assert rows["2026-05-08"].receipt_count == 1
    assert rows["2026-05-08"].allow_count == 1
    assert rows["2026-05-08"].deny_count == 0
    assert rows["2026-05-08"].agent_count == 1
    assert rows["2026-05-09"].entity_count == 2
    assert rows["2026-05-09"].receipt_count == 2
    assert rows["2026-05-09"].deny_count == 1
    assert rows["2026-05-09"].agent_count == 1


def test_metrics_endpoint_pagination(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_SNAPSHOT_ENABLED", "0")
    db_url, sf = _session_factory(tmp_path)
    with sf() as session:
        for index, day in enumerate((date(2026, 5, 7), date(2026, 5, 8), date(2026, 5, 9))):
            session.add(
                MetricsSnapshot(
                    id=day.isoformat(),
                    snapshot_date=day,
                    entity_count=index,
                    edge_count=index,
                    receipt_count=index,
                    allow_count=index,
                    correct_count=0,
                    deny_count=0,
                    agent_count=0,
                    created_at=datetime.utcnow(),
                )
            )
        session.commit()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/metrics-snapshots?days=2").json()

    assert payload["range_days"] == 2
    assert [row["date"] for row in payload["snapshots"]] == ["2026-05-08", "2026-05-09"]
