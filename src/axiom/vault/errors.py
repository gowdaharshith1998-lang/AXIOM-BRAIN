"""Vault-specific exceptions."""

from __future__ import annotations


class VaultError(Exception):
    """Base class for all vault errors."""


class VaultLocked(VaultError):  # noqa: N818
    """Raised when a plaintext op is attempted but the master key is unavailable.

    The master key lives in the ``AXIOM_VAULT_KEY`` environment variable. When
    it is missing or malformed, any operation that needs to encrypt or decrypt
    will raise this. Metadata-only operations (list_secrets, delete_secret,
    mark_tested) do NOT raise — they don't touch the key.
    """


class VaultCorrupt(VaultError):  # noqa: N818
    """Raised when stored ciphertext cannot be decrypted with the current key.

    Causes: master key was rotated, the row was tampered with, or the row was
    written by a different vault instance. The row is not auto-deleted; the
    operator must investigate and decide whether to ``delete_secret`` and re-store.
    """


class DuplicateSecret(VaultError):  # noqa: N818
    """Raised when ``store_secret`` is called for an already-existing
    ``(provider_id, key_name)`` pair.

    Use :func:`delete_secret` first if you want to overwrite. Explicit replace
    avoids silent drift between what the operator thinks is stored and what
    actually is.
    """


class SecretNotFound(VaultError):  # noqa: N818
    """Raised when ``get_secret`` or ``mark_tested`` targets a missing row."""

    def __init__(self, provider_id: str, key_name: str) -> None:
        self.provider_id = provider_id
        self.key_name = key_name
        super().__init__(f"no secret for provider_id={provider_id!r} key_name={key_name!r}")
