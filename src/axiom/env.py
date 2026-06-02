from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from axiom.vault.crypto import ENV_VAR

log = logging.getLogger("axiom.env")
_ENV_LOADED = False


def load_axiom_env() -> None:
    """Load ``.env`` from the current working directory (idempotent)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    dotenv_path = Path.cwd() / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)
    else:
        load_dotenv()
    _ENV_LOADED = True


def vault_status() -> tuple[bool, str | None]:
    """Return ``(key_present, error_message)`` for the vault master key."""
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return False, None
    try:
        from cryptography.fernet import Fernet

        Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        return True, str(exc)
    return True, None


def log_vault_startup_status() -> bool:
    """Log vault state on startup. Returns ``True`` when the vault can be used."""
    present, error = vault_status()
    if not present:
        log.warning("WARNING: AXIOM_VAULT_KEY not set — vault is locked, connectors will not sync.")
        return False
    if error:
        log.warning(
            "WARNING: AXIOM_VAULT_KEY is malformed — vault is locked, connectors will not sync. %s",
            error,
        )
        return False
    log.info("Vault unlocked (AXIOM_VAULT_KEY present)")
    return True
