"""Tests for provider registry and verify_key / verify_secret — Phase 5.13.1."""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock

import httpx
import pytest

from axiom.providers import (
    SecretNotFound,
    UnknownProvider,
    VaultLocked,
    connectors,
    get_provider,
    list_providers,
    llm,
    oauth,
    verify_secret,
)
from axiom.providers import verify as verify_mod

_REAL_HTTPX_CLIENT = httpx.Client

# (provider_id, expected_kind, expected_shape_len)
_PROVIDER_EXPECTATIONS: tuple[tuple[str, str, int], ...] = (
    ("anthropic", "llm", 1),
    ("openai", "llm", 1),
    ("mistral", "llm", 1),
    ("groq", "llm", 1),
    ("github", "connector", 1),
    ("linear", "connector", 1),
    ("notion", "connector", 1),
    ("slack", "connector", 1),
    ("google", "oauth", 2),
    ("microsoft", "oauth", 2),
)

_VERIFY_TARGETS: tuple[tuple[str, ModuleType, str], ...] = (
    ("anthropic", llm, "verify_anthropic_key"),
    ("openai", llm, "verify_openai_key"),
    ("mistral", llm, "verify_mistral_key"),
    ("groq", llm, "verify_groq_key"),
    ("github", connectors, "verify_github_key"),
    ("linear", connectors, "verify_linear_key"),
    ("notion", connectors, "verify_notion_key"),
    ("slack", connectors, "verify_slack_key"),
)


def _client_factory(transport: httpx.MockTransport):
    def _factory(**kwargs: object) -> httpx.Client:
        kwargs = dict(kwargs)
        kwargs.setdefault("timeout", 5.0)
        kwargs["transport"] = transport
        return _REAL_HTTPX_CLIENT(**kwargs)

    return _factory


def _ok_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "slack.com" in url and "/api/auth.test" in url:
        return httpx.Response(200, json={"ok": True, "url": "https://example.slack.com"})
    return httpx.Response(200, json={})


@pytest.mark.parametrize("provider_id,expected_kind,shape_len", _PROVIDER_EXPECTATIONS)
def test_get_provider_metadata_kind_and_shape(
    provider_id: str, expected_kind: str, shape_len: int
) -> None:
    meta = get_provider(provider_id)
    assert meta.id == provider_id
    assert meta.kind == expected_kind
    assert len(meta.credential_shape) == shape_len
    assert meta.docs_url.startswith("http")
    assert meta.verify_endpoint


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(UnknownProvider) as exc:
        get_provider("nonsense-provider")
    assert exc.value.provider_id == "nonsense-provider"


def test_list_providers_returns_ten_sorted_ids() -> None:
    providers = list_providers()
    ids = [p.id for p in providers]
    assert len(ids) == 10
    assert ids == sorted(ids)
    assert set(ids) == {e[0] for e in _PROVIDER_EXPECTATIONS}


def test_llm_and_connector_verify_200_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(_ok_handler)
    factory = _client_factory(transport)
    for _pid, mod, fn_name in _VERIFY_TARGETS:
        monkeypatch.setattr(mod.httpx, "Client", factory)
        fn = getattr(mod, fn_name)
        assert fn("test-token").status == "ok"


@pytest.mark.parametrize("status_code", [401, 403])
def test_llm_and_connector_verify_http_auth_error(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(status_code, json={"error": "no"})
    )
    factory = _client_factory(transport)
    for _pid, mod, fn_name in _VERIFY_TARGETS:
        monkeypatch.setattr(mod.httpx, "Client", factory)
        fn = getattr(mod, fn_name)
        assert fn("bad-token").status == "auth_error"


def test_llm_and_connector_verify_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def __enter__(self) -> Boom:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def post(self, *_a: object, **_k: object) -> None:
            raise httpx.TimeoutException("timeout")

        def get(self, *_a: object, **_k: object) -> None:
            raise httpx.TimeoutException("timeout")

    def boom(**_kw: object) -> Boom:
        return Boom()

    for _pid, mod, fn_name in _VERIFY_TARGETS:
        monkeypatch.setattr(mod.httpx, "Client", boom)
        fn = getattr(mod, fn_name)
        assert fn("x").status == "network_error"


def test_slack_auth_test_http_200_with_ok_false_is_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
    )
    monkeypatch.setattr(connectors.httpx, "Client", _client_factory(transport))
    res = connectors.verify_slack_key("xoxb-fake")
    assert res.status == "auth_error"


@pytest.mark.parametrize(
    "fn",
    [oauth.verify_google_key, oauth.verify_microsoft_key],
)
def test_oauth_verify_returns_not_implemented(fn) -> None:
    assert fn("anything").status == "not_implemented"
    assert fn({"client_id": "a", "client_secret": "b"}).status == "not_implemented"


def test_verify_secret_happy_path_calls_mark_tested_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(_ok_handler)
    monkeypatch.setattr(llm.httpx, "Client", _client_factory(transport))
    mock_mark = MagicMock()
    monkeypatch.setattr(verify_mod, "mark_tested", mock_mark)
    monkeypatch.setattr(verify_mod, "get_secret", lambda _p, _k: "secret-value")

    result = verify_secret("anthropic", "default")
    assert result.status == "ok"
    mock_mark.assert_called_once_with("anthropic", "default", "valid")


def test_verify_secret_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_mod, "get_secret", MagicMock())
    with pytest.raises(UnknownProvider):
        verify_secret("not-a-provider", "k")


def test_verify_secret_propagates_vault_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    def locked(_p: str, _k: str) -> str:
        raise VaultLocked()

    monkeypatch.setattr(verify_mod, "get_secret", locked)
    with pytest.raises(VaultLocked):
        verify_secret("openai", "work")


def test_verify_secret_propagates_secret_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(p: str, k: str) -> str:
        raise SecretNotFound(p, k)

    monkeypatch.setattr(verify_mod, "get_secret", boom)
    with pytest.raises(SecretNotFound) as exc:
        verify_secret("anthropic", "missing")
    assert exc.value.provider_id == "anthropic"
    assert exc.value.key_name == "missing"


def test_llm_rejects_non_string_plaintext() -> None:
    assert llm.verify_anthropic_key({"api_key": "x"}).status == "auth_error"
