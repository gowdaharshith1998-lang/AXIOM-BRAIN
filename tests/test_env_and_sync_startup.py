from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet


def test_load_axiom_env_reads_project_dotenv(tmp_path: Path, monkeypatch: Any) -> None:
    from axiom import env as env_module

    env_module._ENV_LOADED = False
    env_file = tmp_path / ".env"
    env_file.write_text("AXIOM_CONNECTOR_SYNC_INTERVAL_SECONDS=120\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    env_module.load_axiom_env()

    import os

    assert os.environ["AXIOM_CONNECTOR_SYNC_INTERVAL_SECONDS"] == "120"


def test_log_vault_startup_status_warns_when_missing(monkeypatch: Any, caplog: pytest.LogCaptureFixture) -> None:
    from axiom.env import log_vault_startup_status

    monkeypatch.delenv("AXIOM_VAULT_KEY", raising=False)
    with caplog.at_level("WARNING"):
        assert log_vault_startup_status() is False
    assert "WARNING: AXIOM_VAULT_KEY not set" in caplog.text


def test_log_vault_startup_status_ok_with_valid_key(monkeypatch: Any, caplog: pytest.LogCaptureFixture) -> None:
    from axiom.env import log_vault_startup_status

    monkeypatch.setenv("AXIOM_VAULT_KEY", Fernet.generate_key().decode("utf-8"))
    with caplog.at_level("INFO"):
        assert log_vault_startup_status() is True
    assert "Vault unlocked" in caplog.text


def test_sync_all_lists_connected_vendor_strings(monkeypatch: Any) -> None:
    """Regression: select(ConnectorStateRow.vendor).scalars() yields str rows."""
    from axiom.connectors import sync_runner
    from axiom.ingest.broadcaster import EventBroadcaster
    from axiom.schema.models import ConnectorStateRow

    class _FakeSession:
        def __enter__(self) -> _FakeSession:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _stmt: object) -> object:
            class _Result:
                def scalars(self) -> _Result:
                    return self

                def all(self) -> list[str]:
                    return ["github", "notion"]

            return _Result()

    calls: list[str] = []

    async def _fake_sync_vendor(
        _session: object,
        vendor: str,
        _broadcaster: EventBroadcaster,
    ) -> dict[str, str]:
        calls.append(vendor)
        return {"vendor": vendor, "status": "ok", "ingested": 0}

    monkeypatch.setattr(sync_runner, "vault_is_unlocked", lambda: True)
    monkeypatch.setattr(sync_runner, "sync_vendor", _fake_sync_vendor)
    monkeypatch.setattr(sync_runner, "bootstrap_embeddings", lambda _session: 0)

    session_factory = lambda: _FakeSession()
    summary = __import__("asyncio").run(
        sync_runner.sync_all_connected_connectors(session_factory, EventBroadcaster())
    )
    assert calls == ["github", "notion"]
    assert len(summary["results"]) == 2


def test_sync_all_skips_when_vault_locked(monkeypatch: Any) -> None:
    from axiom.connectors import sync_runner
    from axiom.ingest.broadcaster import EventBroadcaster

    monkeypatch.setattr(sync_runner, "vault_is_unlocked", lambda: False)
    summary = __import__("asyncio").run(
        sync_runner.sync_all_connected_connectors(
            lambda: None,
            EventBroadcaster(),
        )
    )
    assert summary["skipped"] == "vault_locked"
