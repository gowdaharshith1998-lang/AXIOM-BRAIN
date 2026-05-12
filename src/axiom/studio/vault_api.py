"""Vault HTTP API endpoints — Phase 5.13.2.

Exposes the vault + provider registry through FastAPI so the settings UI
(Phase 5.13.3) can manage secrets without direct Python/CLI access.

Plaintext discipline:
  * POST /api/secrets accepts plaintext — the ONLY inbound plaintext path.
  * No GET endpoint ever returns plaintext.
  * Plaintext is never logged.

# Protected by app-level API auth when AXIOM_API_TOKEN / AXIOM_AUTH_REQUIRED is set.
# Single-user dev remains unauthenticated by default.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from axiom.providers import (
    UnknownProvider,
    VerifyResult,
    get_provider,
    list_providers,
    verify_secret,
)
from axiom.vault import (
    DuplicateSecret,
    SecretMetadataDTO,
    SecretNotFound,
    VaultCorrupt,
    VaultLocked,
    delete_secret,
    list_secrets,
    store_secret,
)

router = APIRouter()

_KEY_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_KEY_NAME_MAX = 64
_PLAINTEXT_MAX = 8000


# ─── request / response schemas ─────────────────────────────────────────────


class StoreSecretRequest(BaseModel):
    provider_id: str
    key_name: str = Field(max_length=_KEY_NAME_MAX)
    plaintext: str = Field(min_length=1, max_length=_PLAINTEXT_MAX)

    @field_validator("key_name")
    @classmethod
    def _validate_key_name(cls, v: str) -> str:
        if not _KEY_NAME_RE.match(v):
            raise ValueError("key_name must be ASCII alphanumeric, dash, or underscore only")
        return v


class StoreSecretResponse(BaseModel):
    secret: SecretMetadataDTO


class ListSecretsResponse(BaseModel):
    secrets: list[SecretMetadataDTO]


class ListProvidersResponse(BaseModel):
    providers: list[dict[str, Any]]


class ProviderResponse(BaseModel):
    provider: dict[str, Any]


class TestSecretResponse(BaseModel):
    result: VerifyResult
    secret: SecretMetadataDTO


class DeleteSecretResponse(BaseModel):
    deleted: bool


# ─── error mapping ──────────────────────────────────────────────────────────


def _raise_vault_error(exc: Exception) -> None:
    """Map vault/provider exceptions to HTTPException."""
    if isinstance(exc, VaultLocked):
        raise HTTPException(
            503, detail="Vault locked. Run `python -m axiom.cli vault init`."
        ) from exc
    if isinstance(exc, VaultCorrupt):
        raise HTTPException(500, detail="Vault decryption failed.") from exc
    if isinstance(exc, SecretNotFound):
        raise HTTPException(404, detail=str(exc)) from exc
    if isinstance(exc, DuplicateSecret):
        raise HTTPException(409, detail=str(exc)) from exc
    if isinstance(exc, UnknownProvider):
        raise HTTPException(404, detail=str(exc)) from exc
    raise HTTPException(500, detail=str(exc)) from exc


# ─── provider routes ────────────────────────────────────────────────────────


@router.get("/api/providers")
def api_list_providers() -> ListProvidersResponse:
    providers = list_providers()
    return ListProvidersResponse(providers=[p.model_dump(mode="json") for p in providers])


@router.get("/api/providers/{provider_id}")
def api_get_provider(provider_id: str) -> ProviderResponse:
    try:
        meta = get_provider(provider_id)
    except UnknownProvider as exc:
        _raise_vault_error(exc)
    return ProviderResponse(provider=meta.model_dump(mode="json"))


# ─── secret routes ──────────────────────────────────────────────────────────


@router.get("/api/secrets")
def api_list_secrets() -> ListSecretsResponse:
    metas = list_secrets()
    return ListSecretsResponse(secrets=metas)


@router.post("/api/secrets", status_code=201)
def api_store_secret(body: StoreSecretRequest) -> StoreSecretResponse:
    try:
        get_provider(body.provider_id)
    except UnknownProvider:
        raise HTTPException(400, detail=f"unknown provider_id={body.provider_id!r}") from None

    try:
        meta = store_secret(body.provider_id, body.key_name, body.plaintext)
    except (VaultLocked, VaultCorrupt, DuplicateSecret) as exc:
        _raise_vault_error(exc)
    return StoreSecretResponse(secret=meta)


@router.delete("/api/secrets/{provider_id}/{key_name}")
def api_delete_secret(provider_id: str, key_name: str) -> DeleteSecretResponse:
    deleted = delete_secret(provider_id, key_name)
    if not deleted:
        raise HTTPException(
            404, detail=f"no secret for provider_id={provider_id!r} key_name={key_name!r}"
        )
    return DeleteSecretResponse(deleted=True)


@router.post("/api/secrets/{provider_id}/{key_name}/test")
def api_test_secret(provider_id: str, key_name: str) -> TestSecretResponse:
    try:
        result = verify_secret(provider_id, key_name)
    except (VaultLocked, VaultCorrupt, SecretNotFound, UnknownProvider) as exc:
        _raise_vault_error(exc)

    metas = list_secrets()
    meta = next(
        (m for m in metas if m.provider_id == provider_id and m.key_name == key_name),
        None,
    )
    if meta is None:
        raise HTTPException(
            404, detail=f"no secret for provider_id={provider_id!r} key_name={key_name!r}"
        )
    return TestSecretResponse(result=result, secret=meta)


@router.put("/api/secrets/{provider_id}/{key_name}", status_code=200)
def api_rotate_secret(
    provider_id: str, key_name: str, body: StoreSecretRequest
) -> StoreSecretResponse:
    """Replace an existing secret's plaintext value (delete + re-store)."""
    if body.provider_id != provider_id or body.key_name != key_name:
        raise HTTPException(400, detail="body provider_id/key_name must match URL path")

    deleted = delete_secret(provider_id, key_name)
    if not deleted:
        raise HTTPException(
            404, detail=f"no secret for provider_id={provider_id!r} key_name={key_name!r}"
        )

    try:
        meta = store_secret(provider_id, key_name, body.plaintext)
    except (VaultLocked, VaultCorrupt, DuplicateSecret) as exc:
        _raise_vault_error(exc)
    return StoreSecretResponse(secret=meta)
