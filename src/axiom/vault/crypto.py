"""Fernet helpers for the vault.

Single source of plaintext ↔ ciphertext conversion. Everything else in the
vault module goes through here.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

from axiom.vault.errors import VaultCorrupt, VaultLocked

ENV_VAR: str = "AXIOM_VAULT_KEY"


def generate_master_key() -> str:
    """Generate a fresh Fernet master key as a UTF-8 base64 string.

    Suitable for direct paste into ``.env`` as ``AXIOM_VAULT_KEY=...``.
    """
    return Fernet.generate_key().decode("utf-8")


def _load_master_key() -> Fernet:
    """Load the Fernet from the ``AXIOM_VAULT_KEY`` env var.

    Raises:
        VaultLocked: if the env var is missing, empty, or malformed.
    """
    raw = os.environ.get(ENV_VAR)
    if not raw:
        raise VaultLocked(
            f"{ENV_VAR} is not set. Generate a master key with "
            "`python -m axiom.cli vault init` and add it to your .env."
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise VaultLocked(
            f"{ENV_VAR} is malformed (must be a 32-byte url-safe base64 "
            f"Fernet key). Regenerate with `python -m axiom.cli vault init`. "
            f"Underlying error: {exc}"
        ) from exc


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a UTF-8 base64 ciphertext string.

    Raises:
        VaultLocked: if the master key is unavailable.
    """
    f = _load_master_key()
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64 ciphertext string. Returns the original plaintext.

    Raises:
        VaultLocked: if the master key is unavailable.
        VaultCorrupt: if the ciphertext cannot be decrypted with the current key
            (rotated key, tampered row, or wrong vault instance).
    """
    f = _load_master_key()
    try:
        plaintext = f.decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise VaultCorrupt(
            "Stored ciphertext could not be decrypted with the current master "
            "key. The master key may have been rotated, or the row may have "
            "been tampered with."
        ) from exc
    return plaintext.decode("utf-8")
