"""verify_key implementations for LLM API keys (sync httpx)."""

from __future__ import annotations

import logging

import httpx

from axiom.providers.models import VerifyResult

_LOG = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5.0

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_MODELS = "https://api.openai.com/v1/models"
_MISTRAL_MODELS = "https://api.mistral.ai/v1/models"
_GROQ_MODELS = "https://api.groq.com/openai/v1/models"


def _ensure_api_key_string(plaintext: str | dict) -> VerifyResult | str:
    if isinstance(plaintext, dict):
        return VerifyResult(status="auth_error", detail="expected string API key")
    key = plaintext.strip()
    if not key:
        return VerifyResult(status="auth_error", detail="empty API key")
    return key


def _map_http_code(status_code: int) -> VerifyResult | None:
    if status_code == 429:
        return VerifyResult(status="rate_limited", detail="rate limited")
    if status_code in (401, 403):
        return VerifyResult(status="auth_error", detail="unauthorized")
    return None


def verify_anthropic_key(plaintext: str | dict) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.post(
                _ANTHROPIC_URL,
                headers={
                    "x-api-key": got,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
    except httpx.TimeoutException:
        _LOG.debug("anthropic verify timeout")
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("anthropic verify network error: %s", type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code == 200:
        return VerifyResult(status="ok")
    special = _map_http_code(r.status_code)
    if special:
        return special
    return VerifyResult(
        status="network_error",
        detail=f"unexpected HTTP status {r.status_code}",
    )


def _verify_bearer_models(url: str, plaintext: str | dict, provider_id: str) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.get(
                url,
                headers={"Authorization": f"Bearer {got}"},
            )
    except httpx.TimeoutException:
        _LOG.debug("%s verify timeout", provider_id)
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("%s verify network error: %s", provider_id, type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code == 200:
        return VerifyResult(status="ok")
    special = _map_http_code(r.status_code)
    if special:
        return special
    return VerifyResult(
        status="network_error",
        detail=f"unexpected HTTP status {r.status_code}",
    )


def verify_openai_key(plaintext: str | dict) -> VerifyResult:
    return _verify_bearer_models(_OPENAI_MODELS, plaintext, "openai")


def verify_mistral_key(plaintext: str | dict) -> VerifyResult:
    return _verify_bearer_models(_MISTRAL_MODELS, plaintext, "mistral")


def verify_groq_key(plaintext: str | dict) -> VerifyResult:
    return _verify_bearer_models(_GROQ_MODELS, plaintext, "groq")
