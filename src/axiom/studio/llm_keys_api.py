from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from axiom.govern.llm_keys import (
    LLMProviderKeyNotFound,
    UnknownLLMProvider,
    delete_provider_key_with_session,
    get_provider_key_metadata_with_session,
    list_provider_key_metadata_with_session,
    set_provider_key_with_session,
    test_provider_connection_with_session,
)
from axiom.vault.errors import VaultCorrupt, VaultLocked

router = APIRouter()


class LLMKeyIn(BaseModel):
    provider: str
    key: str = Field(min_length=1, max_length=8000)


def _session_factory(request: Request) -> Any:
    return request.app.state.SessionLocal


def _raise_error(exc: Exception) -> None:
    if isinstance(exc, UnknownLLMProvider):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, LLMProviderKeyNotFound):
        raise HTTPException(status_code=404, detail="provider key not found") from exc
    if isinstance(exc, VaultLocked):
        raise HTTPException(status_code=503, detail="vault key unavailable") from exc
    if isinstance(exc, VaultCorrupt):
        raise HTTPException(status_code=500, detail="stored provider key cannot be decrypted") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/internal/llm-keys")
def api_set_llm_key(body: LLMKeyIn, request: Request) -> dict[str, Any]:
    try:
        with _session_factory(request)() as session:
            meta = set_provider_key_with_session(session, body.provider, body.key)
    except Exception as exc:  # noqa: BLE001
        _raise_error(exc)
    return meta.to_dict()


@router.get("/api/internal/llm-keys")
def api_list_llm_keys(request: Request) -> dict[str, Any]:
    with _session_factory(request)() as session:
        rows = list_provider_key_metadata_with_session(session)
    return {"keys": [row.to_dict() for row in rows]}


@router.delete("/api/internal/llm-keys/{provider}")
def api_delete_llm_key(provider: str, request: Request) -> dict[str, bool]:
    try:
        with _session_factory(request)() as session:
            deleted = delete_provider_key_with_session(session, provider)
    except Exception as exc:  # noqa: BLE001
        _raise_error(exc)
    if not deleted:
        raise HTTPException(status_code=404, detail="provider key not found")
    return {"deleted": True}


@router.post("/api/internal/llm-keys/{provider}/test")
def api_test_llm_key(provider: str, request: Request) -> dict[str, Any]:
    try:
        with _session_factory(request)() as session:
            meta = test_provider_connection_with_session(session, provider)
    except Exception as exc:  # noqa: BLE001
        _raise_error(exc)
    return meta.to_dict()


@router.get("/api/internal/llm-keys/{provider}")
def api_get_llm_key(provider: str, request: Request) -> dict[str, Any]:
    try:
        with _session_factory(request)() as session:
            meta = get_provider_key_metadata_with_session(session, provider)
    except Exception as exc:  # noqa: BLE001
        _raise_error(exc)
    return meta.to_dict()
