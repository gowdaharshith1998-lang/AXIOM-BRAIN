from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, desc, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.agent_registry import upsert_agent_observation
from axiom.schema.models import Receipt

RECEIPT_COLUMNS = {
    "id",
    "action_id",
    "agent_name",
    "intent",
    "target_entity_id",
    "cluster_id",
    "decision",
    "reason",
    "policy_id",
    "guidance",
    "suggested_alternative",
    "signing_scheme",
    "signature",
    "prev_hash",
    "this_hash",
    "cali" "bra_state",
    "demo_flag",
    "created_at",
}


@dataclass(frozen=True, slots=True)
class ReceiptInsert:
    id: str
    action_id: str
    agent_name: str
    intent: str
    target_entity_id: str | None
    cluster_id: str | None
    decision: str
    reason: str
    policy_id: str
    guidance: str | None
    suggested_alternative: str | None
    signing_scheme: str
    signature: str
    demo_flag: bool = True
    reserved_state: str | None = None


def ensure_receipts_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("receipts"):
        Receipt.__table__.create(bind=engine, checkfirst=True)
        return

    columns = {column["name"] for column in inspector.get_columns("receipts")}
    if RECEIPT_COLUMNS.issubset(columns):
        return

    legacy_name = f"receipts_legacy_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    with engine.begin() as conn:
        conn.exec_driver_sql(f"ALTER TABLE receipts RENAME TO {legacy_name}")
        for index_name in (
            "ix_receipts_created_at",
            "ix_receipts_merkle_leaf_index",
            "ix_receipts_receipt_type",
        ):
            conn.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
    Receipt.__table__.create(bind=engine, checkfirst=True)


def receipt_to_dict(receipt: Receipt) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "action_id": receipt.action_id,
        "agent_name": receipt.agent_name,
        "intent": receipt.intent,
        "target_entity_id": receipt.target_entity_id,
        "cluster_id": receipt.cluster_id,
        "decision": receipt.decision,
        "reason": receipt.reason,
        "policy_id": receipt.policy_id,
        "guidance": receipt.guidance,
        "suggested_alternative": receipt.suggested_alternative,
        "signing_scheme": receipt.signing_scheme,
        "signature": receipt.signature,
        "prev_hash": receipt.prev_hash,
        "this_hash": receipt.this_hash,
        "cali" + "bra_state": receipt.reserved_state,
        "demo_flag": receipt.demo_flag,
        "created_at": receipt.created_at.isoformat(),
    }


def canonical_receipt_payload(receipt: Receipt) -> dict[str, Any]:
    payload = receipt_to_dict(receipt)
    payload.pop("this_hash")
    return payload


def compute_receipt_hash(receipt: Receipt) -> str:
    canonical = json.dumps(
        canonical_receipt_payload(receipt),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def chain_insert_receipt(
    session_factory: sessionmaker[Session],
    payload: ReceiptInsert,
) -> tuple[Receipt, bool]:
    bind = session_factory.kw.get("bind")
    if not isinstance(bind, Engine):
        raise TypeError("session_factory must be bound to an Engine")

    with bind.connect() as conn:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            transaction = None
        else:
            transaction = conn.begin()
        session = Session(bind=conn, expire_on_commit=False, future=True)
        try:
            existing = session.execute(
                select(Receipt).where(Receipt.action_id == payload.action_id)
            ).scalar_one_or_none()
            if existing is not None:
                session.expunge(existing)
                conn.commit() if transaction is None else transaction.commit()
                return existing, False

            previous = session.execute(
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id)).limit(1)
            ).scalar_one_or_none()
            created_at = datetime.utcnow()
            if previous is not None and created_at <= previous.created_at:
                created_at = previous.created_at + timedelta(microseconds=1)

            receipt = Receipt(
                id=payload.id,
                action_id=payload.action_id,
                agent_name=payload.agent_name,
                intent=payload.intent,
                target_entity_id=payload.target_entity_id,
                cluster_id=payload.cluster_id,
                decision=payload.decision,
                reason=payload.reason,
                policy_id=payload.policy_id,
                guidance=payload.guidance,
                suggested_alternative=payload.suggested_alternative,
                signing_scheme=payload.signing_scheme,
                signature=payload.signature,
                prev_hash=previous.this_hash if previous is not None else None,
                this_hash="",
                reserved_state=payload.reserved_state,
                demo_flag=payload.demo_flag,
                created_at=created_at,
            )
            receipt.this_hash = compute_receipt_hash(receipt)
            session.add(receipt)
            upsert_agent_observation(
                session,
                agent_name=payload.agent_name,
                decision=payload.decision,
                intent=payload.intent,
                action_id=payload.action_id,
                observed_at=created_at,
                demo_flag=payload.demo_flag,
            )
            session.flush()
            session.expunge(receipt)
            conn.commit() if transaction is None else transaction.commit()
            return receipt, True
        except Exception:
            conn.rollback() if transaction is None else transaction.rollback()
            raise
        finally:
            session.close()


def verify_receipt_chain(session: Session, receipt_id: str) -> str:
    rows = session.execute(
        select(Receipt).order_by(Receipt.created_at, Receipt.id)
    ).scalars().all()
    previous_hash: str | None = None
    for row in rows:
        if row.prev_hash != previous_hash:
            return "broken"
        if compute_receipt_hash(row) != row.this_hash:
            return "broken"
        previous_hash = row.this_hash
        if row.id == receipt_id:
            return "verified"
    raise LookupError(receipt_id)
