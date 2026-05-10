from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.receipts import (
    ReceiptInsert,
    chain_insert_receipt,
    compute_receipt_hash,
    verify_receipt_chain,
)
from axiom.mcp.server import AxiomMCPService
from axiom.schema.models import Base, Entity, Receipt
from axiom.studio.server import create_app


def _session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'receipts.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="low_1",
                type="task",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Low Importance"},
            )
        )
        session.commit()
    return sf


def _receipt_payload(index: int, action_id: str | None = None) -> ReceiptInsert:
    return ReceiptInsert(
        id=f"receipt_{index}",
        action_id=action_id or f"act_{index}",
        agent_name="agent_a",
        intent="read",
        target_entity_id="low_1",
        cluster_id="engineering_code",
        decision="allow",
        reason="Allowed by test policy",
        policy_id="policy.demo",
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature=f"sig_{index}",
    )


def _rows(sf: sessionmaker[Session]) -> list[Receipt]:
    with sf() as session:
        return (
            session.execute(select(Receipt).order_by(Receipt.created_at, Receipt.id))
            .scalars()
            .all()
        )


def test_receipts_chain_first_row_has_null_prev_hash(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    receipt, inserted = chain_insert_receipt(sf, _receipt_payload(1))

    assert inserted is True
    assert receipt.prev_hash is None
    assert receipt.this_hash == compute_receipt_hash(receipt)


def test_receipts_chain_subsequent_rows_link_to_previous(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    first, _ = chain_insert_receipt(sf, _receipt_payload(1))
    second, _ = chain_insert_receipt(sf, _receipt_payload(2))

    assert second.prev_hash == first.this_hash
    with sf() as session:
        assert verify_receipt_chain(session, second.id) == "verified"


def test_receipts_chain_break_detection(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    first, _ = chain_insert_receipt(sf, _receipt_payload(1))
    second, _ = chain_insert_receipt(sf, _receipt_payload(2))
    with sf() as session:
        session.execute(update(Receipt).where(Receipt.id == first.id).values(this_hash="bogus"))
        session.commit()

    app = create_app(db_url=f"sqlite:///{tmp_path / 'receipts.db'}", enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get(f"/api/internal/receipts/{second.id}").json()

    assert payload["verification_status"] == "broken"


def test_record_action_persists_receipt(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    service = AxiomMCPService(session_factory=sf)

    out = service.record_action(
        agent_name="agent_record",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read low entity",
        idempotency_key=None,
    )

    rows = _rows(sf)
    assert len(rows) == 1
    assert rows[0].id == out["receipt_id"]
    assert rows[0].action_id == out["action_id"]
    assert rows[0].prev_hash is None


def test_record_action_idempotency_returns_existing_db_row(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    service = AxiomMCPService(session_factory=sf)

    first = service.record_action(
        agent_name="agent_idem",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read low entity",
        idempotency_key="idem-1",
    )
    second = service.record_action(
        agent_name="agent_idem",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read altered",
        idempotency_key="idem-1",
    )

    assert second == first
    assert len(_rows(sf)) == 1


def test_record_action_concurrent_calls_serialize(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    service = AxiomMCPService(session_factory=sf)

    def record(index: int) -> dict[str, object]:
        return service.record_action(
            agent_name=f"agent_{index}",
            intent="read",
            target_entity_id="low_1",
            proposed_action="read low entity",
            idempotency_key=None,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(record, range(12)))

    rows = _rows(sf)
    assert len(rows) == len(results)
    previous_hash: str | None = None
    with sf() as session:
        for row in rows:
            assert row.prev_hash == previous_hash
            assert verify_receipt_chain(session, row.id) == "verified"
            previous_hash = row.this_hash


def test_receipts_endpoint_pagination(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    for index in range(4):
        chain_insert_receipt(sf, _receipt_payload(index))
    rows = list(reversed(_rows(sf)))

    app = create_app(db_url=f"sqlite:///{tmp_path / 'receipts.db'}", enable_organizer=False)
    with TestClient(app) as client:
        first_page = client.get("/api/internal/receipts?limit=2").json()
        second_page = client.get(
            f"/api/internal/receipts?limit=2&before={first_page['receipts'][-1]['created_at']}"
        ).json()

    assert first_page["total_count"] == 4
    assert first_page["merkle_head"] == rows[0].this_hash
    assert [row["id"] for row in first_page["receipts"]] == [rows[0].id, rows[1].id]
    assert [row["id"] for row in second_page["receipts"]] == [rows[2].id, rows[3].id]


def test_merkle_status_endpoint(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    first, _ = chain_insert_receipt(sf, _receipt_payload(1))
    second, _ = chain_insert_receipt(sf, _receipt_payload(2))

    app = create_app(db_url=f"sqlite:///{tmp_path / 'receipts.db'}", enable_organizer=False)
    with TestClient(app) as client:
        payload = client.get("/api/internal/merkle-status").json()

    assert payload["chain_length"] == 2
    assert payload["head_hash"] == second.this_hash
    assert payload["tail_hash"] == first.this_hash
    assert payload["signing_schemes_distribution"]["ed25519"] == 2


def test_action_history_hydrates_from_receipts_on_startup(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    first_service = AxiomMCPService(session_factory=sf)
    recorded = first_service.record_action(
        agent_name="agent_hydrate",
        intent="read",
        target_entity_id="low_1",
        proposed_action="read low entity",
        idempotency_key=None,
    )

    restarted = AxiomMCPService(session_factory=sf)
    approval = restarted.request_human_approval(
        action_id=str(recorded["action_id"]),
        reason="review",
        agent_name="agent_hydrate",
    )

    assert approval["action_id"] == recorded["action_id"]
