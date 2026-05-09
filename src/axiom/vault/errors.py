"""Vault-specific exceptions."""

from __future__ import annotations


class VaultError(Exception):
    """Base class for all vault errors."""


class VaultLocked(VaultError):
    """Raised when a plaintext op is attempted but the master key is unavailable.

    The master key lives in the ``AXIOM_VAULT_KEY`` environment variable. When
    it is missing or malformed, any operation that needs to encrypt or decrypt
    will raise this. Metadata-only operations (list_secrets, delete_secret,
    mark_tested) do NOT raise — they don't touch the key.
    """


class VaultCorrupt(VaultError):
    """Raised when stored ciphertext cannot be decrypted with the current key.

    Causes: master key was rotated, the row was tampered with, or the row was
    written by a different vault instance. The row is not auto-deleted; the
    operator must investigate and decide whether to ``delete_secret`` and re-store.
    """


class DuplicateSecret(VaultError):
    """Raised when ``store_secret`` is called for an already-existing
    ``(provider_id, key_name)`` pair.

    Use :func:`delete_secret` first if you want to overwrite. Explicit replace
    avoids silent drift between what the operator thinks is stored and what
    actually is.
    """
