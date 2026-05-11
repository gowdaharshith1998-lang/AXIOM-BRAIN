from __future__ import annotations

from base64 import b64decode
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.govern.receipts import canonical_payload, compute_receipt_hash
from axiom.schema.models import Receipt
from axiom.sign.ed25519_signer import load_or_create_keypair, verify


def verify_receipt_signature(receipt: Receipt, pubkey: bytes | str) -> dict[str, Any]:
    if receipt.signing_scheme != "ed25519":
        return {"verified": False, "reason": f"unsupported signing scheme: {receipt.signing_scheme}"}
    try:
        signature = b64decode(receipt.signature, validate=True)
    except Exception:  # noqa: BLE001
        return {"verified": False, "reason": "signature is not valid base64"}
    if len(signature) != 64:
        return {"verified": False, "reason": "signature is not 64 bytes"}
    if not verify(canonical_payload(receipt), signature, pubkey):
        return {"verified": False, "reason": "signature verification failed"}
    return {"verified": True, "reason": "verified"}


def verify_receipt_chain(
    session: Session,
    receipt_id: str,
    pubkey: bytes | str | None = None,
) -> dict[str, Any]:
    rows = session.execute(select(Receipt).order_by(Receipt.created_at, Receipt.id)).scalars().all()
    key = pubkey or load_or_create_keypair().public_key_bytes
    previous_hash: str | None = None
    signature_verified = True
    signature_reason = "verified"
    for row in rows:
        if row.prev_hash != previous_hash:
            return {
                "verified": False,
                "chain_verified": False,
                "signature_verified": False,
                "reason": "prev_hash mismatch",
                "signature_reason": signature_reason,
            }
        sig_result = verify_receipt_signature(row, key)
        if not sig_result["verified"]:
            signature_verified = False
            signature_reason = str(sig_result["reason"])
        if compute_receipt_hash(row) != row.this_hash:
            return {
                "verified": False,
                "chain_verified": False,
                "signature_verified": signature_verified,
                "reason": "receipt hash mismatch",
                "signature_reason": signature_reason,
            }
        previous_hash = row.this_hash
        if row.id == receipt_id:
            return {
                "verified": signature_verified,
                "chain_verified": signature_verified,
                "signature_verified": signature_verified,
                "reason": "verified" if signature_verified else signature_reason,
                "signature_reason": signature_reason,
            }
    raise LookupError(receipt_id)
