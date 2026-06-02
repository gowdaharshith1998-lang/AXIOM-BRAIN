"""Tests for the Ask the Brain RAG pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.api.brain_ask import ask_brain
from axiom.govern.llm_keys import set_provider_key_with_session
from axiom.providers.llm_chat import ChatCompletion, ChatCompletionError, ChatMessage
from axiom.schema.models import Base
from axiom.storage import crud
from axiom.vault.crypto import ENV_VAR


def _seed_session_factory(
    tmp_path: Path,
    db_name: str = "ask.db",
) -> tuple[sessionmaker[Session], str]:
    db_url = f"sqlite:///{tmp_path / db_name}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        refund = crud.create_entity(
            session,
            "decision",
            {
                "title": "Refund Policy 2026 (v3)",
                "summary": "Refunds beyond 30 days require VP approval.",
            },
            source_id=None,
        )
        playbook = crud.create_entity(
            session,
            "document",
            {
                "title": "Refund Operations Playbook",
                "body": "Detailed steps for processing customer refunds end-to-end.",
            },
            source_id=None,
        )
        ticket = crud.create_entity(
            session,
            "ticket",
            {"title": "Support SLA Audit", "subject": "Audit refund response times"},
            source_id=None,
        )
        crud.add_edge(session, refund.id, playbook.id, "DECISION_REFERENCES_DOCUMENT")
        crud.add_edge(session, ticket.id, refund.id, "TICKET_REFERENCES_DECISION")
    engine.dispose()
    engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True), db_url


@pytest.fixture()
def vault_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    yield


def _stub_completer(*, content: str = "Refund window is 30 days [1].") -> Any:
    def fake(
        session: Session,
        *,
        provider: str,
        messages: list[ChatMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> ChatCompletion:
        del session, messages, max_tokens
        return ChatCompletion(
            provider=provider,
            model=model or "stub-model",
            content=content,
            usage={"input_tokens": 12, "output_tokens": 8},
        )

    return fake


def test_ask_brain_returns_grounded_answer_and_citations(tmp_path: Path, vault_env: None) -> None:
    del vault_env
    sf, _ = _seed_session_factory(tmp_path)
    with sf() as session:
        set_provider_key_with_session(session, "anthropic", "sk-ant-stub")
    with sf() as session:
        result = ask_brain(
            session,
            question="What is the refund policy?",
            completer=_stub_completer(content="Refunds beyond 30 days require VP approval [1]."),
        )
    payload = result.to_dict()
    assert payload["provider"] == "anthropic"
    assert payload["question"] == "What is the refund policy?"
    assert "[1]" in payload["answer"]
    assert payload["citations"], "expected at least one citation"
    citation_titles = [c["title"] for c in payload["citations"]]
    assert any("Refund" in title for title in citation_titles)
    assert payload["receipt"]["type"] == "brain.ask"
    assert payload["retrieval_mode"] == "hybrid"


def test_ask_brain_picks_default_provider_when_unspecified(tmp_path: Path, vault_env: None) -> None:
    del vault_env
    sf, _ = _seed_session_factory(tmp_path, db_name="ask-default.db")
    with sf() as session:
        set_provider_key_with_session(session, "openai", "sk-openai-stub")
    with sf() as session:
        result = ask_brain(
            session,
            question="Where do refund procedures live?",
            completer=_stub_completer(content="See the Refund Operations Playbook [2]."),
        )
    assert result.provider == "openai"


def test_ask_brain_raises_when_no_provider_key(tmp_path: Path, vault_env: None) -> None:
    del vault_env
    sf, _ = _seed_session_factory(tmp_path, db_name="ask-no-key.db")
    with pytest.raises(Exception) as excinfo:
        with sf() as session:
            ask_brain(session, question="Anything?", completer=_stub_completer())
    assert "no llm provider key" in str(excinfo.value).lower()


def test_ask_brain_rejects_short_question(tmp_path: Path, vault_env: None) -> None:
    del vault_env
    sf, _ = _seed_session_factory(tmp_path, db_name="ask-short.db")
    with pytest.raises(ValueError):
        with sf() as session:
            ask_brain(session, question="a", completer=_stub_completer())


def test_ask_brain_propagates_chat_completion_error(tmp_path: Path, vault_env: None) -> None:
    del vault_env
    sf, _ = _seed_session_factory(tmp_path, db_name="ask-upstream.db")
    with sf() as session:
        set_provider_key_with_session(session, "anthropic", "sk-ant-stub")

    def failing(*args: Any, **kwargs: Any) -> ChatCompletion:
        del args, kwargs
        raise ChatCompletionError("rate_limited", "upstream rate limited")

    with pytest.raises(ChatCompletionError):
        with sf() as session:
            ask_brain(session, question="What is the refund policy?", completer=failing)


def test_post_brain_ask_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    sf, db_url = _seed_session_factory(tmp_path, db_name="ask-route.db")
    with sf() as session:
        set_provider_key_with_session(session, "anthropic", "sk-ant-stub")
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)

    def stub_ask(*, completer: Any = None, **kwargs: Any) -> Any:
        del completer
        from axiom.api.brain_ask import ask_brain as real_ask

        return real_ask(**kwargs, completer=_stub_completer())

    monkeypatch.setattr(
        "axiom.studio.brain_ask_api.ask_brain",
        lambda session, **kwargs: stub_ask(session=session, **kwargs),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/brain/ask",
            json={"question": "What is the refund policy?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "answer" in body
    assert isinstance(body["citations"], list)


def test_post_brain_ask_returns_409_when_no_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    _, db_url = _seed_session_factory(tmp_path, db_name="ask-route-nokey.db")
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/brain/ask",
            json={"question": "What is the refund policy?"},
        )
    assert response.status_code == 409
    assert "key" in response.json()["detail"].lower()


def test_post_brain_ask_validation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    _, db_url = _seed_session_factory(tmp_path, db_name="ask-route-short.db")
    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.post("/api/brain/ask", json={"question": "a"})
    assert response.status_code == 422
