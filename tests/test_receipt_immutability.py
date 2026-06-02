"""Receipt-row append-only immutability (P1-3 / GOV-CHAIN-005).

After the 0005 migration runs, UPDATE and DELETE against the receipts table must
raise (SQLite triggers RAISE(ABORT)). INSERT still works, and the signed receipt
chain still verifies on a fresh chain.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.govern.verify import verify_receipt_chain
from axiom.schema.models import Entity, Receipt
from axiom.sign import ed25519_signer


@pytest.fixture(autouse=True)
def _isolated_signing_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AXIOM_VAULT_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.delenv("AXIOM_ENV", raising=False)
    monkeypatch.delenv(ed25519_signer.SEED_ENV_VAR, raising=False)
    monkeypatch.delenv(ed25519_signer.VAULT_NAME_ENV_VAR, raising=False)
    ed25519_signer.clear_keypair_cache()


@pytest.fixture()
def migrated_sf(tmp_path: Path) -> sessionmaker[Session]:
    """Build a DB by running alembic upgrade head (so the triggers exist)."""
    repo_root = Path(__file__).parent.parent
    db_path = tmp_path / "immutable.db"
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}", future=True)
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


def test_triggers_exist_after_migration(migrated_sf: sessionmaker[Session]) -> None:
    with migrated_sf() as session:
        names = (
            session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'receipts_%'"
                )
            )
            .scalars()
            .all()
        )
    assert set(names) == {"receipts_no_update", "receipts_no_delete"}


def test_insert_still_works(migrated_sf: sessionmaker[Session]) -> None:
    receipt, inserted = chain_insert_receipt(migrated_sf, _payload(1))
    assert inserted is True
    with migrated_sf() as session:
        rows = session.execute(select(Receipt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == receipt.id


def test_update_raises(migrated_sf: sessionmaker[Session]) -> None:
    chain_insert_receipt(migrated_sf, _payload(1))
    with migrated_sf() as session:
        with pytest.raises(IntegrityError, match="receipts are append-only"):
            session.execute(
                text("UPDATE receipts SET reason = :r WHERE id = :i"),
                {"r": "tampered", "i": "receipt_1"},
            )
            session.commit()


def test_delete_raises(migrated_sf: sessionmaker[Session]) -> None:
    chain_insert_receipt(migrated_sf, _payload(1))
    with migrated_sf() as session:
        with pytest.raises(IntegrityError, match="receipts are append-only"):
            session.execute(text("DELETE FROM receipts WHERE id = :i"), {"i": "receipt_1"})
            session.commit()


def test_row_unchanged_after_blocked_update(migrated_sf: sessionmaker[Session]) -> None:
    chain_insert_receipt(migrated_sf, _payload(1))
    with migrated_sf() as session:
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE receipts SET reason = 'tampered' WHERE id = 'receipt_1'"))
            session.commit()
        session.rollback()
    with migrated_sf() as session:
        row = session.get(Receipt, "receipt_1")
        assert row is not None
        assert row.reason == "allowed"


def test_chain_still_verifies_on_fresh_chain(migrated_sf: sessionmaker[Session]) -> None:
    chain_insert_receipt(migrated_sf, _payload(1))
    second, _ = chain_insert_receipt(migrated_sf, _payload(2))
    with migrated_sf() as session:
        result = verify_receipt_chain(session, second.id)
    assert result["chain_verified"] is True
    assert result["signature_verified"] is True
