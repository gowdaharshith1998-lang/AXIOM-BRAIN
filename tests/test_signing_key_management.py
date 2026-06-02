"""Signing key management (P1-2 / GOV-KEY-003).

Covers the env/vault/on-disk load order, the production fail-closed refusal to
auto-generate, the relaxed AXIOM_ENV detection ("prod" as well as "production"),
and the 0600 permissions on a generated on-disk PEM.
"""

from __future__ import annotations

import base64
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from axiom.sign import ed25519_signer
from axiom.vault.crypto import ENV_VAR as VAULT_ENV_VAR
from axiom.vault.store import store_secret_with_session


@pytest.fixture(autouse=True)
def _isolated_signing_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AXIOM_ENV", raising=False)
    monkeypatch.delenv(ed25519_signer.SEED_ENV_VAR, raising=False)
    monkeypatch.delenv(ed25519_signer.VAULT_NAME_ENV_VAR, raising=False)
    ed25519_signer.clear_keypair_cache()


def _fresh_seed_b64() -> str:
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    return base64.b64encode(seed).decode("ascii")


# ── env-seed load round-trips sign/verify ───────────────────────────────────


def test_env_seed_load_roundtrips_sign_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_b64 = _fresh_seed_b64()
    monkeypatch.setenv(ed25519_signer.SEED_ENV_VAR, seed_b64)

    keypair = ed25519_signer.load_or_create_keypair()
    payload = b'{"action":"read"}'
    signature = ed25519_signer.sign(payload)

    assert len(signature) == 64
    assert ed25519_signer.verify(payload, signature, keypair.public_key_bytes)
    # The env seed must produce the same key the seed encodes.
    seed = base64.b64decode(seed_b64)
    expected = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    assert keypair.public_key_bytes == expected


def test_env_seed_takes_precedence_over_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    # Generate an on-disk key first.
    disk = ed25519_signer.generate_keypair()
    ed25519_signer.clear_keypair_cache()

    seed_b64 = _fresh_seed_b64()
    monkeypatch.setenv(ed25519_signer.SEED_ENV_VAR, seed_b64)
    env_keypair = ed25519_signer.load_or_create_keypair()

    assert env_keypair.public_key_bytes != disk.public_key_bytes


def test_env_seed_invalid_base64_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ed25519_signer.SEED_ENV_VAR, "not!valid!base64!")
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()


def test_env_seed_wrong_length_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ed25519_signer.SEED_ENV_VAR, base64.b64encode(b"too-short").decode("ascii"))
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()


# ── vault load ──────────────────────────────────────────────────────────────


def test_vault_seed_load_roundtrips_sign_verify(
    monkeypatch: pytest.MonkeyPatch, db_session: object
) -> None:
    seed_b64 = _fresh_seed_b64()
    # Store the seed in the vault under the fixed provider_id + a chosen name.
    from sqlalchemy.orm import Session

    assert isinstance(db_session, Session)
    store_secret_with_session(
        db_session,
        ed25519_signer.VAULT_PROVIDER_ID,
        "primary",
        seed_b64,
    )
    monkeypatch.setenv(ed25519_signer.VAULT_NAME_ENV_VAR, "primary")

    keypair = ed25519_signer.load_or_create_keypair()
    payload = b'{"action":"read"}'
    signature = ed25519_signer.sign(payload)

    assert ed25519_signer.verify(payload, signature, keypair.public_key_bytes)
    seed = base64.b64decode(seed_b64)
    expected = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    assert keypair.public_key_bytes == expected


def test_vault_configured_but_missing_secret_raises(
    monkeypatch: pytest.MonkeyPatch, db_session: object
) -> None:
    monkeypatch.setenv(ed25519_signer.VAULT_NAME_ENV_VAR, "does_not_exist")
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()


def test_vault_configured_but_locked_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ed25519_signer.VAULT_NAME_ENV_VAR, "primary")
    monkeypatch.delenv(VAULT_ENV_VAR, raising=False)
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()


# ── production fail-closed + relaxed env detection ──────────────────────────


@pytest.mark.parametrize("env_value", ["production", "prod", "PRODUCTION", "  Prod  "])
def test_production_missing_key_raises(monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
    monkeypatch.setenv("AXIOM_ENV", env_value)
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()


def test_production_with_env_seed_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # A provisioned env seed satisfies the production requirement.
    monkeypatch.setenv("AXIOM_ENV", "production")
    monkeypatch.setenv(ed25519_signer.SEED_ENV_VAR, _fresh_seed_b64())
    keypair = ed25519_signer.load_or_create_keypair()
    assert keypair.public_key_bytes


def test_production_does_not_generate_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_ENV", "prod")
    with pytest.raises(ed25519_signer.SigningKeyError):
        ed25519_signer.load_or_create_keypair()
    assert not (Path.home() / ".axiom" / "signing_key.pem").exists()


@pytest.mark.parametrize("env_value", ["", "development", "staging", "test"])
def test_non_production_auto_generates(monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
    monkeypatch.setenv("AXIOM_ENV", env_value)
    keypair = ed25519_signer.load_or_create_keypair()
    assert keypair.public_key_bytes
    assert (Path.home() / ".axiom" / "signing_key.pem").exists()


# ── generated PEM has 0600 perms ────────────────────────────────────────────


def test_generated_pem_has_0600_perms() -> None:
    ed25519_signer.load_or_create_keypair()
    private_path = Path.home() / ".axiom" / "signing_key.pem"
    assert private_path.exists()
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600


def test_on_disk_load_after_generation_roundtrips() -> None:
    created = ed25519_signer.load_or_create_keypair()
    ed25519_signer.clear_keypair_cache()
    loaded = ed25519_signer.load_or_create_keypair()
    assert loaded.public_key_bytes == created.public_key_bytes


def test_vault_key_fixture_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # The conftest autouse fixture sets AXIOM_VAULT_KEY; without a vault-name env
    # var, the signer never touches the vault and falls through to on-disk gen.
    monkeypatch.setenv(VAULT_ENV_VAR, Fernet.generate_key().decode("utf-8"))
    keypair = ed25519_signer.load_or_create_keypair()
    assert keypair.public_key_bytes
