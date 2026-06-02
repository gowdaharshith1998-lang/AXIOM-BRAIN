from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# Env var holding a base64-encoded 32-byte Ed25519 seed (highest precedence).
SEED_ENV_VAR = "AXIOM_SIGNING_KEY_B64"
# Env var naming the vault secret that holds a base64-encoded 32-byte seed.
VAULT_NAME_ENV_VAR = "AXIOM_SIGNING_KEY_VAULT_NAME"
# Fixed vault provider_id under which the signing seed is stored; the configured
# AXIOM_SIGNING_KEY_VAULT_NAME value is used as the key_name within it.
VAULT_PROVIDER_ID = "signing"

# Production environment names. Treat both "production" and "prod" as production
# so a near-miss value ("prod") does not silently fall through to the permissive
# dev path (GOV-KEY-003 review near-miss).
_PRODUCTION_ENV_NAMES = frozenset({"production", "prod"})


class SigningKeyError(RuntimeError):
    """Raised when no signing key can be loaded and auto-generation is refused."""


def _is_production() -> bool:
    """Return True if AXIOM_ENV indicates production.

    Accepts both ``production`` and ``prod`` (case-insensitive, whitespace
    trimmed). In production the signing key MUST be provisioned out of band:
    auto-generation of a fresh keypair is refused.
    """
    return os.environ.get("AXIOM_ENV", "").strip().lower() in _PRODUCTION_ENV_NAMES


@dataclass(frozen=True, slots=True)
class KeyPair:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey
    public_key_bytes: bytes
    private_key_path: Path
    public_key_path: Path


_KEYPAIR_CACHE: KeyPair | None = None


def _private_key_path() -> Path:
    return Path.home() / ".axiom" / "signing_key.pem"


def _public_key_path() -> Path:
    return Path.home() / ".axiom" / "signing_key.pem.pub"


def _payload_bytes(payload: bytes | str | dict[str, Any]) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _keypair_from_private(private_key: Ed25519PrivateKey) -> KeyPair:
    public_key = private_key.public_key()
    return KeyPair(
        private_key=private_key,
        public_key=public_key,
        public_key_bytes=public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
        private_key_path=_private_key_path(),
        public_key_path=_public_key_path(),
    )


def clear_keypair_cache() -> None:
    global _KEYPAIR_CACHE
    _KEYPAIR_CACHE = None


def _private_key_from_seed_b64(seed_b64: str, *, source: str) -> Ed25519PrivateKey:
    """Decode a base64-encoded 32-byte Ed25519 seed into a private key.

    ``source`` is a short human label (e.g. the env var name) used only for
    error messages — never the seed value itself.
    """
    try:
        seed = base64.b64decode(seed_b64.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SigningKeyError(f"signing key from {source} is not valid base64") from exc
    if len(seed) != 32:
        raise SigningKeyError(
            f"signing key from {source} must decode to exactly 32 bytes (got {len(seed)})"
        )
    return Ed25519PrivateKey.from_private_bytes(seed)


def _keypair_from_env_seed() -> KeyPair | None:
    """Load the keypair from ``AXIOM_SIGNING_KEY_B64`` if set, else None."""
    seed_b64 = os.environ.get(SEED_ENV_VAR)
    if not seed_b64:
        return None
    return _keypair_from_private(_private_key_from_seed_b64(seed_b64, source=SEED_ENV_VAR))


def _keypair_from_vault() -> KeyPair | None:
    """Load the keypair from the Fernet vault if ``AXIOM_SIGNING_KEY_VAULT_NAME`` is set.

    Returns None when the env var is unset. Uses the EXISTING vault read API
    (``get_secret``); requires the vault to be unlocked (``AXIOM_VAULT_KEY``
    present). A configured-but-missing or locked vault is a hard, fail-closed
    error rather than a silent fall-through to on-disk generation.
    """
    vault_name = os.environ.get(VAULT_NAME_ENV_VAR)
    if not vault_name:
        return None

    # Imported lazily so the sign module has no import-time dependency on the
    # vault package (and so tests can patch it).
    from axiom.vault.errors import SecretNotFound, VaultError
    from axiom.vault.store import get_secret

    try:
        seed_b64 = get_secret(VAULT_PROVIDER_ID, vault_name)
    except SecretNotFound as exc:
        raise SigningKeyError(
            f"{VAULT_NAME_ENV_VAR}={vault_name!r} is set but no signing seed is "
            f"stored in the vault under provider_id={VAULT_PROVIDER_ID!r}"
        ) from exc
    except VaultError as exc:
        # VaultLocked / VaultCorrupt — vault is configured but unusable. Fail
        # closed; never silently fall back to auto-generation.
        raise SigningKeyError(
            f"{VAULT_NAME_ENV_VAR}={vault_name!r} is set but the vault could not "
            f"be read: {type(exc).__name__}"
        ) from exc
    return _keypair_from_private(_private_key_from_seed_b64(seed_b64, source="vault"))


def generate_keypair() -> KeyPair:
    global _KEYPAIR_CACHE

    private_key = Ed25519PrivateKey.generate()
    keypair = _keypair_from_private(private_key)
    keypair.private_key_path.parent.mkdir(parents=True, exist_ok=True)
    keypair.private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    keypair.private_key_path.chmod(0o600)
    keypair.public_key_path.write_bytes(
        keypair.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    keypair.public_key_path.chmod(0o644)
    _KEYPAIR_CACHE = keypair
    return keypair


def load_or_create_keypair() -> KeyPair:
    """Resolve the Ed25519 signing keypair, fail-closed in production.

    Load order (GOV-KEY-003):
      1. ``AXIOM_SIGNING_KEY_B64`` env var — base64-encoded 32-byte seed.
      2. The Fernet vault, when ``AXIOM_SIGNING_KEY_VAULT_NAME`` is set and the
         vault is unlocked (existing vault read API).
      3. The on-disk PEM at ``~/.axiom/signing_key.pem``.
      4. Auto-generate a fresh keypair — DEV ONLY. In production this is refused
         (a missing key is a hard, fail-closed configuration error); operators
         must provision the key out of band.

    The keypair is cached after the first successful resolution.
    """
    global _KEYPAIR_CACHE

    private_path = _private_key_path()
    if _KEYPAIR_CACHE is not None and _KEYPAIR_CACHE.private_key_path == private_path:
        return _KEYPAIR_CACHE

    # 1. Environment-provided seed (highest precedence).
    env_keypair = _keypair_from_env_seed()
    if env_keypair is not None:
        _KEYPAIR_CACHE = env_keypair
        return _KEYPAIR_CACHE

    # 2. Fernet vault.
    vault_keypair = _keypair_from_vault()
    if vault_keypair is not None:
        _KEYPAIR_CACHE = vault_keypair
        return _KEYPAIR_CACHE

    # 3. On-disk PEM.
    if private_path.exists():
        private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError(f"signing key at {private_path} is not an Ed25519 private key")
        _KEYPAIR_CACHE = _keypair_from_private(private_key)
        return _KEYPAIR_CACHE

    # 4. Auto-generate (dev only). Never silently auto-generate an unencrypted
    # signing key in production — a missing key there is a hard, fail-closed
    # configuration error.
    if _is_production():
        raise SigningKeyError(
            f"no Ed25519 signing key found (checked {SEED_ENV_VAR}, the vault via "
            f"{VAULT_NAME_ENV_VAR}, and {private_path}) and auto-generation is refused "
            "in production (AXIOM_ENV in {'production','prod'}); provision the signing "
            "key out of band before starting"
        )
    return generate_keypair()


def sign(canonical_payload: bytes | str | dict[str, Any]) -> bytes:
    return load_or_create_keypair().private_key.sign(_payload_bytes(canonical_payload))


def _public_key_from_bytes(pubkey: bytes | str) -> Ed25519PublicKey:
    raw = pubkey.encode("utf-8") if isinstance(pubkey, str) else pubkey
    if raw.startswith(b"-----BEGIN"):
        loaded = serialization.load_pem_public_key(raw)
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("public key is not Ed25519")
        return loaded
    return Ed25519PublicKey.from_public_bytes(raw)


def verify(payload: bytes | str | dict[str, Any], sig: bytes, pubkey: bytes | str) -> bool:
    try:
        _public_key_from_bytes(pubkey).verify(sig, _payload_bytes(payload))
        return True
    except (InvalidSignature, ValueError):
        return False
