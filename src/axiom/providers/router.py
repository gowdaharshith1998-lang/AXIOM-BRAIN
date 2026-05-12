"""Resolve active LLM API keys — vault-first, registry env-var fallback."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy.exc import OperationalError

from axiom.providers.registry import get_provider
from axiom.vault import SecretNotFound, VaultCorrupt, VaultLocked, get_secret, list_secrets
from axiom.vault.models import VALID_STATUSES, SecretStatus

logger = logging.getLogger("axiom.providers.router")

_DEFAULT_KEY_NAME = "default"

_vault_locked_env_fallback_logged = False


@dataclass(frozen=True, slots=True)
class KeyResolution:
    key: str | None
    source: Literal["vault", "env", "none"]
    vault_status: SecretStatus | None = None


def _vault_status_for(provider_id: str, key_name: str) -> SecretStatus | None:
    """Metadata-only lookup (no decrypt); safe alongside a successful ``get_secret``."""
    try:
        for meta in list_secrets(provider_id):
            if meta.key_name == key_name:
                return cast(SecretStatus, meta.status) if meta.status in VALID_STATUSES else None
        return None
    except Exception:  # noqa: BLE001 — status is best-effort
        logger.debug("could not resolve vault status for %s/%s", provider_id, key_name)
        return None


def _is_missing_vault_table(exc: OperationalError) -> bool:
    return "no such table: secrets" in str(exc).lower()


def get_active_llm_key(provider_id: str) -> KeyResolution:
    """Return the active API key for ``provider_id`` (vault ``default``, then env)."""
    global _vault_locked_env_fallback_logged

    meta = get_provider(provider_id)
    env_var = meta.env_var_name
    vault_was_locked = False

    try:
        key = get_secret(provider_id, _DEFAULT_KEY_NAME)
        vstatus = _vault_status_for(provider_id, _DEFAULT_KEY_NAME)
        return KeyResolution(key=key, source="vault", vault_status=vstatus)
    except SecretNotFound:
        pass
    except OperationalError as exc:
        if not _is_missing_vault_table(exc):
            raise
        logger.debug("vault secrets table missing; falling back to env for %s", provider_id)
    except VaultLocked:
        vault_was_locked = True
    except VaultCorrupt:
        logger.warning(
            "vault ciphertext corrupt or undecryptable for provider_id=%s; falling back to env",
            provider_id,
        )

    if env_var is None:
        return KeyResolution(key=None, source="none", vault_status=None)

    env_key = os.environ.get(env_var)
    if env_key:
        if vault_was_locked and not _vault_locked_env_fallback_logged:
            logger.info("vault locked, using env fallback")
            _vault_locked_env_fallback_logged = True
        return KeyResolution(key=env_key, source="env", vault_status=None)
    return KeyResolution(key=None, source="none", vault_status=None)


def get_active_llm_key_anthropic() -> KeyResolution:
    return get_active_llm_key("anthropic")
