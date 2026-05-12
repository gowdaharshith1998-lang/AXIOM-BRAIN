"""Tests for vault HTTP API endpoints — Phase 5.13.2.

Covers:
  * Provider listing and lookup.
  * Secret CRUD (POST, GET listing, DELETE) — happy + error paths.
  * Plaintext discipline: no GET response ever contains plaintext.
  * Validation: bad key_name, empty plaintext, unknown provider.
  * Duplication: POST same (provider_id, key_name) → 409.
  * Verify (POST /test) with mocked verify_key.
  * Vault locked → 503.
  * Rotate (PUT) happy + error paths.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from axiom.providers.models import VerifyResult
from axiom.schema.models import Base
from axiom.storage.db import init_engine, reset_engine
from axiom.vault.crypto import ENV_VAR

TEST_KEY: str = Fernet.generate_key().decode("utf-8")


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Spin up a TestClient with a temp DB and unlocked vault."""
    monkeypatch.setenv(ENV_VAR, TEST_KEY)
    db_path = tmp_path / "test_api.db"
    db_url = f"sqlite:///{db_path}"

    engine = init_engine(db_url)
    Base.metadata.create_all(engine)

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, live=False, enable_organizer=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    engine.dispose()
    reset_engine()


@pytest.fixture()
def locked_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with vault LOCKED (no AXIOM_VAULT_KEY)."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    db_path = tmp_path / "test_locked.db"
    db_url = f"sqlite:///{db_path}"

    engine = init_engine(db_url)
    Base.metadata.create_all(engine)

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, live=False, enable_organizer=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    engine.dispose()
    reset_engine()


# ─── provider routes ────────────────────────────────────────────────────────


def test_list_providers_returns_all_ten(api_client: TestClient) -> None:
    resp = api_client.get("/api/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["providers"]) == 10
    ids = [p["id"] for p in data["providers"]]
    assert "anthropic" in ids
    assert "openai" in ids


def test_get_provider_anthropic(api_client: TestClient) -> None:
    resp = api_client.get("/api/providers/anthropic")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"]["id"] == "anthropic"
    assert data["provider"]["kind"] == "llm"


def test_get_provider_unknown_returns_404(api_client: TestClient) -> None:
    resp = api_client.get("/api/providers/nonsense")
    assert resp.status_code == 404


# ─── secret CRUD happy path ────────────────────────────────────────────────


def test_post_get_delete_lifecycle(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "default",
            "plaintext": "sk-ant-test-1234",
        },
    )
    assert resp.status_code == 201
    meta = resp.json()["secret"]
    assert meta["provider_id"] == "anthropic"
    assert meta["key_name"] == "default"
    assert meta["status"] == "untested"

    resp = api_client.get("/api/secrets")
    assert resp.status_code == 200
    secrets = resp.json()["secrets"]
    assert len(secrets) == 1
    assert secrets[0]["key_name"] == "default"

    resp = api_client.delete("/api/secrets/anthropic/default")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = api_client.get("/api/secrets")
    assert resp.json()["secrets"] == []


# ─── validation errors ──────────────────────────────────────────────────────


def test_post_unknown_provider_returns_400(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "bogus-provider",
            "key_name": "key1",
            "plaintext": "value",
        },
    )
    assert resp.status_code == 400
    assert "bogus-provider" in resp.json()["detail"]


def test_post_invalid_key_name_whitespace_returns_422(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "bad key name",
            "plaintext": "value",
        },
    )
    assert resp.status_code == 422


def test_post_invalid_key_name_slashes_returns_422(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "bad/key",
            "plaintext": "value",
        },
    )
    assert resp.status_code == 422


def test_post_empty_plaintext_returns_422(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "k",
            "plaintext": "",
        },
    )
    assert resp.status_code == 422


# ─── duplication ────────────────────────────────────────────────────────────


def test_post_duplicate_returns_409(api_client: TestClient) -> None:
    api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "dup",
            "plaintext": "first",
        },
    )
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "dup",
            "plaintext": "second",
        },
    )
    assert resp.status_code == 409


# ─── delete nonexistent ────────────────────────────────────────────────────


def test_delete_nonexistent_returns_404(api_client: TestClient) -> None:
    resp = api_client.delete("/api/secrets/anthropic/nonexistent")
    assert resp.status_code == 404


# ─── verify / test ──────────────────────────────────────────────────────────


def test_post_test_secret_returns_verify_result(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "testkey",
            "plaintext": "sk-ant-fake",
        },
    )

    mock_verify = MagicMock(return_value=VerifyResult(status="ok", detail=None))
    monkeypatch.setattr("axiom.studio.vault_api.verify_secret", mock_verify)

    from axiom.vault import mark_tested

    mark_tested("anthropic", "testkey", "valid")

    resp = api_client.post("/api/secrets/anthropic/testkey/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["status"] == "ok"
    assert data["secret"]["provider_id"] == "anthropic"
    assert data["secret"]["status"] == "valid"


# ─── vault locked ──────────────────────────────────────────────────────────


def test_post_secret_vault_locked_returns_503(locked_client: TestClient) -> None:
    resp = locked_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "k",
            "plaintext": "value",
        },
    )
    assert resp.status_code == 503
    assert "Vault locked" in resp.json()["detail"]


# ─── plaintext discipline ──────────────────────────────────────────────────


def test_plaintext_never_in_any_get_response(api_client: TestClient) -> None:
    plaintext = "sk-ant-SUPER-SECRET-NEVER-LEAK-12345"
    api_client.post(
        "/api/secrets",
        json={
            "provider_id": "openai",
            "key_name": "leak-test",
            "plaintext": plaintext,
        },
    )

    resp_list = api_client.get("/api/secrets")
    assert plaintext not in resp_list.text

    resp_providers = api_client.get("/api/providers")
    assert plaintext not in resp_providers.text

    resp_provider = api_client.get("/api/providers/openai")
    assert plaintext not in resp_provider.text


def test_post_response_does_not_contain_plaintext(api_client: TestClient) -> None:
    plaintext = "sk-ant-ANOTHER-SECRET-67890"
    resp = api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "no-leak",
            "plaintext": plaintext,
        },
    )
    assert resp.status_code == 201
    assert plaintext not in resp.text


# ─── rotate (PUT) ──────────────────────────────────────────────────────────


def test_rotate_secret_replaces_value(api_client: TestClient) -> None:
    api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "rot",
            "plaintext": "old-value",
        },
    )
    resp = api_client.put(
        "/api/secrets/anthropic/rot",
        json={
            "provider_id": "anthropic",
            "key_name": "rot",
            "plaintext": "new-value",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["secret"]["key_name"] == "rot"

    secrets = api_client.get("/api/secrets").json()["secrets"]
    assert len(secrets) == 1


def test_rotate_nonexistent_returns_404(api_client: TestClient) -> None:
    resp = api_client.put(
        "/api/secrets/anthropic/nope",
        json={
            "provider_id": "anthropic",
            "key_name": "nope",
            "plaintext": "value",
        },
    )
    assert resp.status_code == 404


def test_rotate_mismatched_path_body_returns_400(api_client: TestClient) -> None:
    api_client.post(
        "/api/secrets",
        json={
            "provider_id": "anthropic",
            "key_name": "mm",
            "plaintext": "v",
        },
    )
    resp = api_client.put(
        "/api/secrets/anthropic/mm",
        json={
            "provider_id": "openai",
            "key_name": "mm",
            "plaintext": "v",
        },
    )
    assert resp.status_code == 400
