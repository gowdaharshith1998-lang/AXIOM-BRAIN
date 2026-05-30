"""Tests for the brain ask rate limit + daily token budget (P0-6 / OBS-01)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from axiom.schema.models import Base
from axiom.studio.rate_limit import (
    AskRateLimiter,
    RateLimitExceeded,
    ask_limiter,
    rate_limit_key,
)
from axiom.vault.crypto import ENV_VAR


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    """Isolate every test in this module from shared limiter state."""
    ask_limiter.reset()
    yield
    ask_limiter.reset()


class _StubResult:
    def to_dict(self) -> dict[str, Any]:
        return {"answer": "stubbed", "citations": []}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'ask-rl.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)

    def _stub_ask(session: Any, **kwargs: Any) -> _StubResult:
        del session, kwargs
        return _StubResult()

    monkeypatch.setattr("axiom.studio.brain_ask_api.ask_brain", _stub_ask)
    # The TestClient context manager runs the app lifespan, which sets
    # app.state.SessionLocal (the handler needs it before reaching the stub).
    with TestClient(app) as test_client:
        yield test_client


# --- Unit-level tests of the limiter itself ------------------------------


def test_rate_limit_key_prefers_bearer_token() -> None:
    assert rate_limit_key("abc", "1.2.3.4") == "token:abc"
    assert rate_limit_key("", "1.2.3.4") == "ip:1.2.3.4"
    assert rate_limit_key(None, None) == "ip:unknown"


def test_check_allows_up_to_limit_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "3")
    limiter = AskRateLimiter()
    for _ in range(3):
        limiter.check("k", 1, now=1000.0)
    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.check("k", 1, now=1000.0)
    assert excinfo.value.retry_after >= 1


def test_check_window_resets_after_a_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "2")
    limiter = AskRateLimiter()
    limiter.check("k", 1, now=1000.0)
    limiter.check("k", 1, now=1000.0)
    with pytest.raises(RateLimitExceeded):
        limiter.check("k", 1, now=1000.0)
    # New window -> allowed again.
    limiter.check("k", 1, now=1061.0)


def test_check_token_cap_charges_requested_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "1000")
    monkeypatch.setenv("AXIOM_ASK_DAILY_TOKEN_CAP", "100")
    limiter = AskRateLimiter()
    limiter.check("k", 60, now=0.0)
    # 60 + 60 = 120 > 100 -> raises, and charges nothing on raise.
    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.check("k", 60, now=0.0)
    assert "token" in excinfo.value.detail.lower()
    # The failed request charged nothing, so a smaller one still fits (60+40).
    limiter.check("k", 40, now=0.0)


# --- Route-level tests ----------------------------------------------------


def test_11th_request_in_window_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "10")
    ask_limiter.reset()
    for _ in range(10):
        resp = client.post("/api/brain/ask", json={"question": "hello there?"})
        assert resp.status_code == 200, resp.text
    resp = client.post("/api/brain/ask", json={"question": "hello there?"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


def test_daily_token_cap_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "1000")
    # Cap of 1500 with max_tokens=1024 -> first ok (1024), second over (2048).
    monkeypatch.setenv("AXIOM_ASK_DAILY_TOKEN_CAP", "1500")
    ask_limiter.reset()
    resp = client.post(
        "/api/brain/ask", json={"question": "hello there?", "max_tokens": 1024}
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/brain/ask", json={"question": "hello there?", "max_tokens": 1024}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
