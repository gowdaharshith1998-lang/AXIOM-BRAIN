from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import (
    get_provider_key_plaintext_with_session,
    set_provider_key_with_session,
)
from axiom.schema.models import Base, LLMProviderKey
from axiom.vault.crypto import ENV_VAR


@pytest.fixture()
def llm_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    engine = create_engine(f"sqlite:///{tmp_path / 'llm_keys.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        yield session
    engine.dispose()


@pytest.fixture()
def llm_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'llm_keys_api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        yield client


def test_llm_key_encrypt_roundtrip(llm_session: Session) -> None:
    set_provider_key_with_session(llm_session, "anthropic", "sk-ant-secret-1234")
    row = llm_session.get(LLMProviderKey, "anthropic")
    assert row is not None
    assert row.encrypted_key != "sk-ant-secret-1234"
    assert "sk-ant-secret-1234" not in row.encrypted_key
    assert get_provider_key_plaintext_with_session(llm_session, "anthropic") == "sk-ant-secret-1234"


def test_llm_key_fingerprint_correct(llm_session: Session) -> None:
    meta = set_provider_key_with_session(llm_session, "openai", "sk-test-abcdef")
    assert meta.key_fingerprint == "cdef"


def test_llm_missing_key_returns_404(llm_client: TestClient) -> None:
    resp = llm_client.post("/api/internal/llm-keys/anthropic/test")
    assert resp.status_code == 404


def test_llm_test_endpoint_hits_provider(
    llm_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})

        class Response:
            status_code = 200

        return Response()

    monkeypatch.setattr("axiom.govern.llm_keys.httpx.get", fake_get)
    llm_client.post("/api/internal/llm-keys", json={"provider": "openai", "key": "sk-openai-1234"})
    resp = llm_client.post("/api/internal/llm-keys/openai/test")
    assert resp.status_code == 200
    assert resp.json()["last_test_status"] == "valid"
    assert calls and calls[0]["url"] == "https://api.openai.com/v1/models"


def test_llm_delete_removes_row(llm_client: TestClient) -> None:
    llm_client.post("/api/internal/llm-keys", json={"provider": "groq", "key": "gsk-secret-1234"})
    resp = llm_client.delete("/api/internal/llm-keys/groq")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    resp = llm_client.post("/api/internal/llm-keys/groq/test")
    assert resp.status_code == 404


def test_llm_list_excludes_plaintext(llm_client: TestClient) -> None:
    plaintext = "sk-mistral-super-secret-9876"
    llm_client.post("/api/internal/llm-keys", json={"provider": "mistral", "key": plaintext})
    resp = llm_client.get("/api/internal/llm-keys")
    assert resp.status_code == 200
    assert plaintext not in resp.text
    assert "encrypted_key" not in resp.text
    assert resp.json()["keys"][0]["key_fingerprint"] == "9876"
