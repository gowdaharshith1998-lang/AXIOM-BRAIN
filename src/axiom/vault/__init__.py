"""Encrypted secrets vault — Phase 5.13.0 foundation.

The vault stores third-party credentials (LLM API keys, OAuth tokens,
connector secrets) encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256).

Master key sourced from ``AXIOM_VAULT_KEY`` environment variable. Generate one
with::

    python -m axiom.cli vault init

Public API surface:

  * :func:`store_secret` — encrypt + persist a new secret. Plaintext entry point.
  * :func:`get_secret`   — decrypt + return plaintext. The ONLY plaintext exit point.
  * :func:`list_secrets` — metadata only. Never returns plaintext. Safe when locked.
  * :func:`delete_secret`— remove a row. Safe when locked.
  * :func:`mark_tested`  — update verification status / timestamp. Safe when locked.

Errors:

  * :class:`VaultLocked` — ``AXIOM_VAULT_KEY`` missing or malformed.
  * :class:`VaultCorrupt` — ciphertext cannot be decrypted with current master key.
  * :class:`DuplicateSecret` — ``(provider_id, key_name)`` already exists.
  * :class:`SecretNotFound` — no row for ``get_secret`` / ``mark_tested``.

Future phases (NOT in 5.13.0):
  * 5.13.1 — provider registry + verification.
  * 5.13.2 — HTTP API endpoints.
  * 5.13.3 — frontend UI.
  * 5.13.4 — organizer classifier resolves Anthropic keys vault-first via
    :mod:`axiom.providers.router`, with registry env-var fallback.
  * 5.13.5+ — OAuth flows.
"""

from __future__ import annotations

from axiom.vault.crypto import generate_master_key
from axiom.vault.errors import (
    DuplicateSecret,
    SecretNotFound,
    VaultCorrupt,
    VaultError,
    VaultLocked,
)
from axiom.vault.models import Secret, SecretMetadataDTO, SecretStatus
from axiom.vault.store import (
    delete_secret,
    get_secret,
    list_secrets,
    mark_tested,
    store_secret,
)

__all__ = [
    "DuplicateSecret",
    "SecretNotFound",
    "Secret",
    "SecretMetadataDTO",
    "SecretStatus",
    "VaultCorrupt",
    "VaultError",
    "VaultLocked",
    "delete_secret",
    "generate_master_key",
    "get_secret",
    "list_secrets",
    "mark_tested",
    "store_secret",
]
