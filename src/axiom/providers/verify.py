"""Orchestration: load secret from vault, verify, persist status."""

from __future__ import annotations

from axiom.providers.models import VerifyResult, VerifyStatus
from axiom.providers.registry import _get_record
from axiom.vault import get_secret, mark_tested
from axiom.vault.models import SecretStatus

_STATUS_TO_SECRET: dict[VerifyStatus, SecretStatus] = {
    "ok": "valid",
    "auth_error": "invalid",
    "network_error": "untested",
    "rate_limited": "untested",
    "not_implemented": "untested",
}


def verify_secret(provider_id: str, key_name: str) -> VerifyResult:
    record = _get_record(provider_id)
    plaintext = get_secret(provider_id, key_name)
    result = record.verify_key(plaintext)
    secret_status = _STATUS_TO_SECRET[result.status]
    mark_tested(provider_id, key_name, secret_status)
    return result
