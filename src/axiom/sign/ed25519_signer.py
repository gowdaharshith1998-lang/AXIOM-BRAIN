from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class SigningKeyError(RuntimeError):
    """Raised when no signing key can be loaded and auto-generation is refused."""


def _is_production() -> bool:
    return os.environ.get("AXIOM_ENV", "").strip().lower() == "production"


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
    global _KEYPAIR_CACHE

    private_path = _private_key_path()
    if _KEYPAIR_CACHE is not None and _KEYPAIR_CACHE.private_key_path == private_path:
        return _KEYPAIR_CACHE
    if not private_path.exists():
        # GOV-KEY-003: never silently auto-generate an unencrypted signing key in
        # production. A missing key there is a hard, fail-closed configuration
        # error — operators must provision the key out of band (see deferred
        # vault-load below). Outside production (incl. the test suite) we keep the
        # developer-friendly auto-generation behavior.
        if _is_production():
            raise SigningKeyError(
                f"no Ed25519 signing key found at {private_path} and auto-generation is "
                "refused in production (AXIOM_ENV=production); provision the signing key "
                "out of band before starting"
            )
        return generate_keypair()
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError(f"signing key at {private_path} is not an Ed25519 private key")
    _KEYPAIR_CACHE = _keypair_from_private(private_key)
    return _KEYPAIR_CACHE


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
