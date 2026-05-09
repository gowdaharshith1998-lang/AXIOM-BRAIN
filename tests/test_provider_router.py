"""Tests for vault-first LLM API key routing — Phase 5.13.4."""

from __future__ import annotations

from datetime import datetime

import pytest

import axiom.providers.router as router_mod
from axiom.providers.router import KeyResolution, get_active_llm_key, get_active_llm_key_anthropic
from axiom.vault import SecretNotFound, VaultCorrupt, VaultLocked
from axiom.vault.models import SecretMetadataDTO


def _meta(
    *,
    pid: str = "anthropic",
    key_name: str = "default",
    status: str = "valid",
) -> SecretMetadataDTO:
    now = datetime(2026, 1, 1, 0, 0, 0)
    return SecretMetadataDTO(
        id="mid" + "x" * 29,
        provider_id=pid,
        key_name=key_name,
        status=status,
        last_tested_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _reset_fallback_log_flag() -> None:
    router_mod._vault_locked_env_fallback_logged = False


def test_active_key_from_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router_mod, "get_secret", lambda _p, _k: "plain-from-vault")
    monkeypatch.setattr(
        router_mod,
        "list_secrets",
        lambda pid: [_meta(pid=pid)],
    )

    res = get_active_llm_key("anthropic")
    assert res.source == "vault"
    assert res.key == "plain-from-vault"
    assert res.vault_status == "valid"


def test_secret_not_found_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-secret")

    def boom(p: str, k: str) -> str:
        raise SecretNotFound(p, k)

    monkeypatch.setattr(router_mod, "get_secret", boom)

    res = get_active_llm_key("anthropic")
    assert res.source == "env"
    assert res.key == "env-key-secret"
    assert res.vault_status is None


def test_vault_locked_falls_back_to_env_and_logs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info_messages: list[str] = []

    def capture_info(msg: object, *args: object, **_kwargs: object) -> None:
        text = msg % args if args else msg
        info_messages.append(str(text))

    monkeypatch.setattr(router_mod.logger, "info", capture_info)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env-only")

    def locked(_p: str, _k: str) -> str:
        raise VaultLocked()

    monkeypatch.setattr(router_mod, "get_secret", locked)

    r1 = get_active_llm_key("anthropic")
    assert r1.source == "env"
    assert r1.key == "from-env-only"
    assert info_messages.count("vault locked, using env fallback") == 1

    before = len(info_messages)
    r2 = get_active_llm_key("anthropic")
    assert r2.key == "from-env-only"
    assert len(info_messages) == before  # fallback line stays once per process guard


def test_vault_wins_when_env_also_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-should-not-win")
    monkeypatch.setattr(router_mod, "get_secret", lambda _p, _k: "vault-wins")
    monkeypatch.setattr(
        router_mod,
        "list_secrets",
        lambda pid: [_meta(pid=pid)],
    )

    res = get_active_llm_key("anthropic")
    assert res.source == "vault"
    assert res.key == "vault-wins"


def test_none_when_vault_miss_and_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def missing(p: str, k: str) -> str:
        raise SecretNotFound(p, k)

    monkeypatch.setattr(router_mod, "get_secret", missing)

    res = get_active_llm_key("anthropic")
    assert res.source == "none"
    assert res.key is None


def test_vault_corrupt_logs_warning_falls_through_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []

    def capture_warning(msg: object, *args: object, **_kwargs: object) -> None:
        text = msg % args if args else msg
        warnings.append(str(text))

    monkeypatch.setattr(router_mod.logger, "warning", capture_warning)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-fallback")

    def corrupt(_p: str, _k: str) -> str:
        raise VaultCorrupt()

    monkeypatch.setattr(router_mod, "get_secret", corrupt)

    res = get_active_llm_key("openai")
    assert res.source == "env"
    assert res.key == "openai-env-fallback"
    assert any("vault ciphertext corrupt" in w for w in warnings)


@pytest.mark.parametrize(
    ("provider_id", "env_var", "suffix"),
    [
        ("openai", "OPENAI_API_KEY", "open"),
        ("mistral", "MISTRAL_API_KEY", "mis"),
        ("groq", "GROQ_API_KEY", "grq"),
    ],
)
def test_llm_providers_use_registry_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    provider_id: str,
    env_var: str,
    suffix: str,
) -> None:
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv(env_var, f"v-{suffix}")

    def missing(p: str, k: str) -> str:
        raise SecretNotFound(p, k)

    monkeypatch.setattr(router_mod, "get_secret", missing)

    res = get_active_llm_key(provider_id)
    assert res.source == "env"
    assert res.key == f"v-{suffix}"


def test_connector_has_no_env_var_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(p: str, k: str) -> str:
        raise SecretNotFound(p, k)

    monkeypatch.setattr(router_mod, "get_secret", missing)

    res = get_active_llm_key("github")
    assert res.source == "none"
    assert res.key is None


def test_get_active_llm_key_anthropic_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def spy(pid: str) -> KeyResolution:
        called.append(pid)
        assert pid == "anthropic"
        return KeyResolution(key="k", source="vault", vault_status=None)

    monkeypatch.setattr(router_mod, "get_active_llm_key", spy)

    r = get_active_llm_key_anthropic()
    assert r.source == "vault"
    assert r.key == "k"
    assert called == ["anthropic"]