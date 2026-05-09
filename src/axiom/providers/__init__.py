"""Credential provider registry and key verification — Phase 5.13.1."""

from __future__ import annotations

from axiom.providers.errors import UnknownProvider
from axiom.providers.models import CredentialField, ProviderMetadata, VerifyResult
from axiom.providers.registry import get_provider, list_providers
from axiom.providers.verify import verify_secret
from axiom.vault import SecretNotFound, VaultLocked

__all__ = [
    "CredentialField",
    "SecretNotFound",
    "UnknownProvider",
    "ProviderMetadata",
    "VaultLocked",
    "VerifyResult",
    "get_provider",
    "list_providers",
    "verify_secret",
]
