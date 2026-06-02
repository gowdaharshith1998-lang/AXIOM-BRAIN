"""Tamper-evidence of the signed receipt chain (GOV-SIG-004 / GOV-CHAIN-005).

The Ed25519 signature now commits to ``prev_hash`` (via ``signing_payload``),
so a signed receipt cannot be relocated to a different position in the chain —
or have its ``prev_hash`` altered — and still verify. An untampered chain must
keep verifying.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.receipts import (
    ReceiptInsert,
    chain_insert_receipt,
    compute_receipt_hash,
)
from axiom.govern.verify import verify_receipt_chain, verify_receipt_signature
from axiom.schema.models import Base, Entity, Receipt
from axiom.sign import ed25519_signer


@pytest.fixture(autouse=True)
def _isolated_signing_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AXIOM_VAULT_KEY", Fernet.generate_key().decode("utf-8"))
    ed25519_signer.clear_keypair_cache()


@pytest.fixture()
def chain_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'tamper.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="ent_1",
                type="document",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Entity One"},
            )
        )
        session.commit()
    return sf


def _payload(index: int) -> ReceiptInsert:
    return ReceiptInsert(
        id=f"receipt_{index}",
        action_id=f"act_{index}",
        agent_name="agent_a",
        intent="read",
        target_entity_id="ent_1",
        cluster_id="engineering_code",
        decision="allow",
        reason="allowed",
        policy_id="policy.test",
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature="",
    )


def test_untampered_chain_verifies(chain_sf: sessionmaker[Session]) -> None:
    first, _ = chain_insert_receipt(chain_sf, _payload(1))
    second, _ = chain_insert_receipt(chain_sf, _payload(2))

    pubkey = ed25519_signer.load_or_create_keypair().public_key_bytes
    with chain_sf() as session:
        rows = session.execute(select(Receipt)).scalars().all()
        for row in rows:
            assert verify_receipt_signature(row, pubkey)["verified"] is True
        result = verify_receipt_chain(session, second.id)
    assert result["chain_verified"] is True
    assert result["signature_verified"] is True


def test_altering_prev_hash_breaks_signature(chain_sf: sessionmaker[Session]) -> None:
    """A signed receipt whose prev_hash is changed must fail signature verify.

    This is the relocation attack: an attacker moves a validly-signed receipt to
    a new chain position by rewriting its prev_hash (and the dependent this_hash
    so the bare hash-chain check still passes). Because the signature now covers
    prev_hash, the signature no longer matches.
    """
    chain_insert_receipt(chain_sf, _payload(1))
    second, _ = chain_insert_receipt(chain_sf, _payload(2))

    pubkey = ed25519_signer.load_or_create_keypair().public_key_bytes

    # Pre-condition: the signature is valid before tampering.
    with chain_sf() as session:
        original = session.get(Receipt, second.id)
        assert original is not None
        assert verify_receipt_signature(original, pubkey)["verified"] is True

    # Rewrite prev_hash (relocation), and recompute this_hash so a naive
    # hash-only check could still pass — the signature must catch it.
    with chain_sf() as session:
        row = session.get(Receipt, second.id)
        assert row is not None
        row.prev_hash = "0" * 64
        row.this_hash = compute_receipt_hash(row)
        session.add(row)
        session.commit()

    with chain_sf() as session:
        tampered = session.get(Receipt, second.id)
        assert tampered is not None
        assert verify_receipt_signature(tampered, pubkey)["verified"] is False
        assert verify_receipt_chain(session, second.id)["signature_verified"] is False


def test_relocating_signed_receipt_fails_verification(chain_sf: sessionmaker[Session]) -> None:
    """Swap a later receipt's prev_hash to point at the genesis (None).

    Even keeping a self-consistent hash chain, the moved receipt's signature was
    computed over its original prev_hash, so verification fails after relocation.
    """
    first, _ = chain_insert_receipt(chain_sf, _payload(1))
    second, _ = chain_insert_receipt(chain_sf, _payload(2))
    assert second.prev_hash == first.this_hash

    pubkey = ed25519_signer.load_or_create_keypair().public_key_bytes

    # Relocate to the genesis position (prev_hash -> None) via ORM attribute
    # mutation in a single session, keeping the hash chain self-consistent so
    # that only the signature — which committed to the original prev_hash —
    # betrays the move.
    with chain_sf() as session:
        row = session.get(Receipt, second.id)
        assert row is not None
        row.prev_hash = None
        row.this_hash = compute_receipt_hash(row)
        session.add(row)
        session.commit()

    with chain_sf() as session:
        relocated = session.get(Receipt, second.id)
        assert relocated is not None
        assert relocated.prev_hash is None
        assert verify_receipt_signature(relocated, pubkey)["verified"] is False
