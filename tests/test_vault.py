"""Tests for the encrypted secrets vault — Phase 5.13.0.

Covers:
  * Fernet master-key load + key generation.
  * Round-trip: store → get returns the same plaintext.
  * list_secrets returns metadata only and never plaintext.
  * Locked vault: read/write raises VaultLocked; list/delete/mark_tested do not.
  * Wrong key (rotated master): raises VaultCorrupt on read; list still works.
  * Unique constraint (provider_id, key_name) raises DuplicateSecret.
  * delete_secret removes the row, not just clears the value.
  * mark_tested updates status + timestamp; rejects unknown statuses.
  * CLI: `vault init` generates a key and refuses to overwrite when env is set.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from axiom.vault import (
    DuplicateSecret,
    SecretMetadataDTO,
    VaultCorrupt,
    VaultLocked,
    generate_master_key,
)
from axiom.vault import store as vault_store
from axiom.vault.crypto import ENV_VAR
from axiom.vault.models import Secret

# Module-scoped, generated once per test run. Two distinct keys: the primary
# vault key (TEST_KEY) and a rotated key (ALT_KEY) used to exercise the
# wrong-key / VaultCorrupt path.
TEST_KEY: str = Fernet.generate_key().decode("utf-8")
ALT_KEY: str = Fernet.generate_key().decode("utf-8")


@pytest.fixture()
def unlocked_vault(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Set AXIOM_VAULT_KEY for the test, restore on teardown."""
    monkeypatch.setenv(ENV_VAR, TEST_KEY)
    yield TEST_KEY


@pytest.fixture()
def locked_vault(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure AXIOM_VAULT_KEY is unset for the test."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    yield


# ─── crypto-level tests ─────────────────────────────────────────────────────


def test_generate_master_key_returns_valid_fernet_key() -> None:
    key = generate_master_key()
    # Fernet accepts the key only if it is 32-byte url-safe base64.
    Fernet(key.encode("utf-8"))
    # Two consecutive generations must differ (otherwise PRNG is broken).
    assert key != generate_master_key()


# ─── round-trip tests ───────────────────────────────────────────────────────


def test_store_then_get_round_trip_returns_same_plaintext(
    db_session: Session, unlocked_vault: str
) -> None:
    plaintext = "sk-ant-test-1234567890"
    meta = vault_store.store_secret_with_session(
        db_session, "anthropic", "default", plaintext
    )
    assert isinstance(meta, SecretMetadataDTO)
    assert meta.provider_id == "anthropic"
    assert meta.key_name == "default"
    assert meta.status == "untested"
    assert meta.last_tested_at is None
    assert len(meta.id) == 32

    got = vault_store.get_secret_with_session(db_session, "anthropic", "default")
    assert got == plaintext


def test_store_persists_only_ciphertext_not_plaintext(
    db_session: Session, unlocked_vault: str
) -> None:
    plaintext = "super-secret-token-shhh"
    vault_store.store_secret_with_session(db_session, "openai", "work", plaintext)

    row = db_session.query(Secret).filter_by(provider_id="openai", key_name="work").one()
    assert row.encrypted_value != plaintext
    assert plaintext not in row.encrypted_value
    # Fernet tokens start with "gAAAAA..." (version byte 0x80 base64-encoded).
    assert row.encrypted_value.startswith("gAAAAA")


# ─── list_secrets tests ─────────────────────────────────────────────────────


def test_list_secrets_returns_metadata_only_never_plaintext(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN-1")
    vault_store.store_secret_with_session(db_session, "openai", "work", "PLAIN-2")

    metas = vault_store.list_secrets_with_session(db_session)
    assert len(metas) == 2

    serialized = [m.model_dump() for m in metas]
    flat = repr(serialized)
    # Plaintext must not appear in the metadata payload.
    assert "PLAIN-1" not in flat
    assert "PLAIN-2" not in flat
    # The DTO schema must not even have a field for ciphertext or plaintext.
    field_names = set(SecretMetadataDTO.model_fields.keys())
    assert "encrypted_value" not in field_names
    assert "value" not in field_names
    assert "plaintext" not in field_names


def test_list_secrets_works_when_vault_is_locked(
    db_session: Session, unlocked_vault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Store while unlocked.
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    # Now lock and verify list still works.
    monkeypatch.delenv(ENV_VAR, raising=False)
    metas = vault_store.list_secrets_with_session(db_session)
    assert len(metas) == 1
    assert metas[0].provider_id == "anthropic"


def test_list_secrets_filters_by_provider(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "a1")
    vault_store.store_secret_with_session(db_session, "anthropic", "work", "a2")
    vault_store.store_secret_with_session(db_session, "openai", "default", "o1")

    only_anthropic = vault_store.list_secrets_with_session(db_session, provider_id="anthropic")
    assert {m.key_name for m in only_anthropic} == {"default", "work"}
    assert all(m.provider_id == "anthropic" for m in only_anthropic)


# ─── locked-vault behavior ──────────────────────────────────────────────────


def test_store_secret_when_locked_raises_vault_locked(
    db_session: Session, locked_vault: None
) -> None:
    with pytest.raises(VaultLocked) as excinfo:
        vault_store.store_secret_with_session(db_session, "anthropic", "default", "x")
    assert "vault init" in str(excinfo.value)
    # And nothing was persisted.
    assert vault_store.list_secrets_with_session(db_session) == []


def test_get_secret_when_locked_raises_vault_locked(
    db_session: Session, unlocked_vault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(VaultLocked):
        vault_store.get_secret_with_session(db_session, "anthropic", "default")


# ─── corruption / wrong-key behavior ────────────────────────────────────────


def test_get_secret_with_rotated_master_key_raises_vault_corrupt(
    db_session: Session, unlocked_vault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    # Rotate the master key in the env. Existing ciphertext is now unreadable.
    monkeypatch.setenv(ENV_VAR, ALT_KEY)
    with pytest.raises(VaultCorrupt):
        vault_store.get_secret_with_session(db_session, "anthropic", "default")
    # list still works — it doesn't decrypt.
    metas = vault_store.list_secrets_with_session(db_session)
    assert len(metas) == 1


# ─── uniqueness / duplication ───────────────────────────────────────────────


def test_duplicate_provider_keyname_raises_duplicate_secret(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "first")
    with pytest.raises(DuplicateSecret) as excinfo:
        vault_store.store_secret_with_session(db_session, "anthropic", "default", "second")
    assert "anthropic" in str(excinfo.value)
    # The original row must still be intact and decryptable.
    assert vault_store.get_secret_with_session(db_session, "anthropic", "default") == "first"


def test_same_key_name_under_different_provider_is_allowed(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "a")
    vault_store.store_secret_with_session(db_session, "openai", "default", "o")
    metas = vault_store.list_secrets_with_session(db_session)
    assert len(metas) == 2


# ─── delete_secret ──────────────────────────────────────────────────────────


def test_delete_secret_removes_row_not_just_clears_value(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    assert len(vault_store.list_secrets_with_session(db_session)) == 1

    deleted = vault_store.delete_secret_with_session(db_session, "anthropic", "default")
    assert deleted is True

    # The row is gone (not present with empty value).
    assert vault_store.list_secrets_with_session(db_session) == []
    raw_count = db_session.query(Secret).count()
    assert raw_count == 0

    # Deleting again returns False instead of raising.
    assert vault_store.delete_secret_with_session(db_session, "anthropic", "default") is False


# ─── mark_tested ────────────────────────────────────────────────────────────


def test_mark_tested_updates_status_and_timestamp(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    meta = vault_store.mark_tested_with_session(db_session, "anthropic", "default", "valid")
    assert meta.status == "valid"
    assert meta.last_tested_at is not None


def test_mark_tested_rejects_unknown_status(
    db_session: Session, unlocked_vault: str
) -> None:
    vault_store.store_secret_with_session(db_session, "anthropic", "default", "PLAIN")
    with pytest.raises(ValueError):
        vault_store.mark_tested_with_session(
            db_session, "anthropic", "default", "bogus"  # type: ignore[arg-type]
        )


def test_mark_tested_for_missing_secret_raises_key_error(
    db_session: Session, unlocked_vault: str
) -> None:
    with pytest.raises(KeyError):
        vault_store.mark_tested_with_session(db_session, "nope", "nope", "valid")


# ─── CLI: vault init ────────────────────────────────────────────────────────


def test_cli_vault_init_prints_key_and_env_var(
    locked_vault: None, capsys: pytest.CaptureFixture[str]
) -> None:
    from axiom.cli import cmd_vault_init

    cmd_vault_init(argparse_namespace())
    captured = capsys.readouterr()
    assert ENV_VAR in captured.out
    # Extract the key after the ENV_VAR=... line and verify Fernet accepts it.
    line = next(line for line in captured.out.splitlines() if line.startswith(f"{ENV_VAR}="))
    key = line.split("=", 1)[1]
    Fernet(key.encode("utf-8"))


def test_cli_vault_init_refuses_to_overwrite_existing_key(
    unlocked_vault: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from axiom.cli import cmd_vault_init

    with pytest.raises(SystemExit) as excinfo:
        cmd_vault_init(argparse_namespace())
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "already set" in err


def argparse_namespace() -> object:
    """Tiny stand-in for argparse.Namespace — the cmd_vault_init handler ignores its arg."""
    import argparse

    return argparse.Namespace()
