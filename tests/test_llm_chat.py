"""HTTP-level tests for the real LLM chat client (Phase 3).

These exercise providers.llm_chat.chat_complete end-to-end against a stubbed
httpx.Client — request shape, response parsing, usage mapping, and error
mapping — so the real client is no longer dead-code from a test perspective.
Fully network-free; no live API key and no extra test dependency required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import (
    LLMProviderKeyNotFound,
    set_provider_key_with_session,
)
from axiom.providers import llm_chat
from axiom.providers.llm_chat import (
    ChatCompletionError,
    ChatMessage,
    UnknownLLMProvider,
    chat_complete,
)
from axiom.schema.models import Base


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "stub error body"

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Stub of httpx.Client used as a context manager by _http_post_json."""

    captured: dict[str, Any] = {}
    response: _FakeResponse = _FakeResponse(200, {})

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        type(self).captured = {"url": url, "headers": headers, "json": json}
        return type(self).response


def _install(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> type[_FakeClient]:
    _FakeClient.captured = {}
    _FakeClient.response = response
    monkeypatch.setattr(llm_chat.httpx, "Client", _FakeClient)
    return _FakeClient


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'llm.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return sf()


def _seed(session: Session, provider: str, key: str = "sk-test-key") -> None:
    set_provider_key_with_session(session, provider, key)
    session.commit()


def test_chat_complete_anthropic_request_and_response(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(session, "anthropic")
    client = _install(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "model": "claude-haiku-4-5-20251001",
                "content": [{"type": "text", "text": "Refund window is 30 days [1]."}],
                "usage": {"input_tokens": 42, "output_tokens": 9},
            },
        ),
    )

    result = chat_complete(
        session,
        provider="anthropic",
        messages=[
            ChatMessage(role="system", content="You are AXIOM."),
            ChatMessage(role="user", content="What is the refund window?"),
        ],
        max_tokens=128,
    )

    assert result.provider == "anthropic"
    assert result.content == "Refund window is 30 days [1]."
    assert result.usage == {"input_tokens": 42, "output_tokens": 9}

    cap = client.captured
    assert cap["url"] == "https://api.anthropic.com/v1/messages"
    assert cap["headers"]["x-api-key"] == "sk-test-key"
    assert cap["headers"]["anthropic-version"] == "2023-06-01"
    assert cap["json"]["max_tokens"] == 128
    # system message hoisted into body["system"]; only user/assistant remain
    assert cap["json"]["system"] == "You are AXIOM."
    assert [m["role"] for m in cap["json"]["messages"]] == ["user"]


def test_chat_complete_openai_request_and_response(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(session, "openai")
    client = _install(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "Hello from OpenAI."}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
        ),
    )

    result = chat_complete(
        session,
        provider="openai",
        messages=[ChatMessage(role="user", content="hi")],
    )

    assert result.provider == "openai"
    assert result.content == "Hello from OpenAI."
    assert result.usage == {"input_tokens": 11, "output_tokens": 4}
    assert client.captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert client.captured["headers"]["Authorization"] == "Bearer sk-test-key"


def test_chat_complete_maps_429_to_rate_limited(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(session, "anthropic")
    _install(monkeypatch, _FakeResponse(429))

    with pytest.raises(ChatCompletionError) as exc:
        chat_complete(
            session,
            provider="anthropic",
            messages=[ChatMessage(role="user", content="hi")],
        )
    assert exc.value.status == "rate_limited"


def test_chat_complete_maps_401_to_auth_error(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(session, "openai")
    _install(monkeypatch, _FakeResponse(401))

    with pytest.raises(ChatCompletionError) as exc:
        chat_complete(
            session,
            provider="openai",
            messages=[ChatMessage(role="user", content="hi")],
        )
    assert exc.value.status == "auth_error"


def test_chat_complete_unknown_provider(session: Session) -> None:
    with pytest.raises(UnknownLLMProvider):
        chat_complete(
            session,
            provider="not-a-provider",
            messages=[ChatMessage(role="user", content="hi")],
        )


def test_chat_complete_missing_key_raises(session: Session) -> None:
    # No key seeded for anthropic => the vault lookup raises before any HTTP call.
    with pytest.raises(LLMProviderKeyNotFound):
        chat_complete(
            session,
            provider="anthropic",
            messages=[ChatMessage(role="user", content="hi")],
        )
