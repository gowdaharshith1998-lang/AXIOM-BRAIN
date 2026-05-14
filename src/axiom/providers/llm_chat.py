"""Synchronous chat-completion clients for AXIOM Ask the Brain.

Wraps a small subset of provider chat APIs behind a single dataclass-based
interface. Keys come from the stored LLM vault via
``axiom.govern.llm_keys.get_provider_key_plaintext_with_session`` — never from
environment variables — so all credential reads go through the same audit path
as the rest of the system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

import httpx

from axiom.govern.llm_keys import (
    LLMProviderKeyNotFound,
    UnknownLLMProvider,
    get_provider_key_plaintext_with_session,
)
from axiom.providers.models import VerifyResult
from axiom.vault.errors import VaultCorrupt, VaultLocked

log = logging.getLogger("axiom.providers.llm_chat")

ChatRole = Literal["system", "user", "assistant"]
SUPPORTED_PROVIDERS: Final[frozenset[str]] = frozenset({"anthropic", "openai"})
DEFAULT_MODELS: Final[dict[str, str]] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}
_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0
_DEFAULT_MAX_TOKENS: Final[int] = 1024


class ChatCompletionError(RuntimeError):
    """Raised when an upstream chat completion call fails."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    provider: str
    model: str
    content: str
    usage: dict[str, int]


def _http_post_json(
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any],
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = client.post(url, headers=headers, json=json_body)
    except httpx.TimeoutException as exc:
        raise ChatCompletionError("network_error", "upstream timeout") from exc
    except httpx.RequestError as exc:
        raise ChatCompletionError(
            "network_error",
            f"network error: {type(exc).__name__}",
        ) from exc

    if response.status_code == 429:
        raise ChatCompletionError("rate_limited", "upstream rate limited")
    if response.status_code in {401, 403}:
        raise ChatCompletionError("auth_error", "provider rejected credentials")
    if not 200 <= response.status_code < 300:
        raise ChatCompletionError(
            "network_error",
            f"unexpected HTTP {response.status_code}: {response.text[:200]}",
        )
    return cast(dict[str, Any], response.json())


def _split_system(messages: list[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    system_chunks = [msg.content for msg in messages if msg.role == "system"]
    rest = [msg for msg in messages if msg.role != "system"]
    return ("\n\n".join(chunk for chunk in system_chunks if chunk.strip()), rest)


def _call_anthropic(
    key: str,
    *,
    model: str,
    messages: list[ChatMessage],
    max_tokens: int,
) -> ChatCompletion:
    system_text, rest = _split_system(messages)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": m.role, "content": m.content} for m in rest],
    }
    if system_text:
        body["system"] = system_text
    payload = _http_post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json_body=body,
    )
    blocks = payload.get("content") or []
    text_parts = [
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    usage = payload.get("usage") or {}
    return ChatCompletion(
        provider="anthropic",
        model=str(payload.get("model") or model),
        content="".join(text_parts).strip(),
        usage={
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
        },
    )


def _call_openai(
    key: str,
    *,
    model: str,
    messages: list[ChatMessage],
    max_tokens: int,
) -> ChatCompletion:
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    payload = _http_post_json(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json_body=body,
    )
    choices = payload.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "").strip()
    usage = payload.get("usage") or {}
    return ChatCompletion(
        provider="openai",
        model=str(payload.get("model") or model),
        content=content,
        usage={
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
    )


def chat_complete(
    session: Any,
    *,
    provider: str,
    messages: list[ChatMessage],
    model: str | None = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> ChatCompletion:
    """Send a chat completion using a vault-stored provider key.

    Raises ChatCompletionError for upstream issues, VaultLocked / VaultCorrupt
    when the key store is unavailable, LLMProviderKeyNotFound when no key has
    been registered for the requested provider, and UnknownLLMProvider for an
    unsupported provider string.
    """

    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise UnknownLLMProvider(
            f"unsupported chat provider: {provider!r}; supported: "
            f"{sorted(SUPPORTED_PROVIDERS)}"
        )
    plaintext_key = get_provider_key_plaintext_with_session(session, normalized)
    resolved_model = (model or DEFAULT_MODELS[normalized]).strip()
    if not resolved_model:
        raise ValueError("model must not be empty")
    if normalized == "anthropic":
        return _call_anthropic(
            plaintext_key,
            model=resolved_model,
            messages=messages,
            max_tokens=max_tokens,
        )
    return _call_openai(
        plaintext_key,
        model=resolved_model,
        messages=messages,
        max_tokens=max_tokens,
    )


__all__ = [
    "ChatCompletion",
    "ChatCompletionError",
    "ChatMessage",
    "ChatRole",
    "DEFAULT_MODELS",
    "SUPPORTED_PROVIDERS",
    "chat_complete",
    # re-export so callers don't need to import from two places
    "LLMProviderKeyNotFound",
    "UnknownLLMProvider",
    "VaultCorrupt",
    "VaultLocked",
    "VerifyResult",
]
