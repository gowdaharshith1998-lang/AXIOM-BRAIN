"""OAuth provider stubs — real verification ships in Phase 5.13.5+."""

from __future__ import annotations

from typing import Any

from axiom.providers.models import VerifyResult

_OAUTH_DETAIL = "OAuth verification lands in Phase 5.13.5"
PlaintextCredential = str | dict[str, Any]


def verify_google_key(plaintext: PlaintextCredential) -> VerifyResult:
    return VerifyResult(status="not_implemented", detail=_OAUTH_DETAIL)


def verify_microsoft_key(plaintext: PlaintextCredential) -> VerifyResult:
    return VerifyResult(status="not_implemented", detail=_OAUTH_DETAIL)
