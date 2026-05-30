from __future__ import annotations

import hashlib
import json
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, desc, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.agent_registry import upsert_agent_observation
from axiom.schema.models import Receipt
from axiom.sign.ed25519_signer import sign
from axiom.storage.db import create_schema_table

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
    "passport_id",
    "guidance",
    "suggested_alternative",
    "signing_scheme",
    "signature",
    "prev_hash",
    "this_hash",
    "cali" + "bra_state",
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
    passport_id: str | None = None
    demo_flag: bool = True
    reserved_state: str | None = None


def ensure_receipts_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("receipts"):
        create_schema_table(Receipt.__table__, engine)
        return

    columns = {column["name"] for column in inspector.get_columns("receipts")}
    if RECEIPT_COLUMNS.issubset(columns):
        return
    legacy_with_only_missing_passport = RECEIPT_COLUMNS.difference({"passport_id"}).issubset(
        columns
    )
    if legacy_with_only_missing_passport and "passport_id" not in columns:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE receipts ADD COLUMN passport_id VARCHAR")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_receipts_passport_id ON receipts (passport_id)"
            )
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
    create_schema_table(Receipt.__table__, engine)


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
        "passport_id": receipt.passport_id,
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
    if payload.get("passport_id") is None:
        payload.pop("passport_id", None)
    return payload


def canonical_payload(receipt: Receipt) -> bytes:
    payload = receipt_to_dict(receipt)
    for key in ("signature", "sig", "this_hash", "prev_hash"):
        payload.pop(key, None)
    if payload.get("passport_id") is None:
        payload.pop("passport_id", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signing_payload(receipt: Receipt) -> bytes:
    """Canonical bytes that the Ed25519 signature commits to.

    GOV-SIG-004 / GOV-CHAIN-005: unlike ``canonical_payload`` (which drops
    ``prev_hash`` and is kept only for backwards-compatible deterministic
    hashing), the signature MUST cover ``prev_hash`` so a signed receipt cannot
    be relocated to a different position in the chain and still verify. We sign
    over everything except the signature itself and ``this_hash`` (which is
    derived after signing); ``prev_hash`` is explicitly retained.
    """
    payload = receipt_to_dict(receipt)
    for key in ("signature", "sig", "this_hash"):
        payload.pop(key, None)
    if payload.get("passport_id") is None:
        payload.pop("passport_id", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
                passport_id=payload.passport_id,
                guidance=payload.guidance,
                suggested_alternative=payload.suggested_alternative,
                signing_scheme="ed25519",
                signature="",
                prev_hash=previous.this_hash if previous is not None else None,
                this_hash="",
                reserved_state=payload.reserved_state,
                demo_flag=payload.demo_flag,
                created_at=created_at,
            )
            receipt.signature = b64encode(sign(signing_payload(receipt))).decode("ascii")
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
    from axiom.govern.verify import verify_receipt_chain as verify_chain

    result = verify_chain(session, receipt_id)
    return "verified" if result["chain_verified"] else "broken"
