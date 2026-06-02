"""P0-6 completion: rate limits / cost caps on ALL paid LLM endpoints.

Covers the coverage gaps beyond ``/api/brain/ask`` (which ``test_ask_rate_limit``
already exercises):

* ``POST /api/internal/skills/{skill_id}/run`` returns 429 when over the limit.
* the per-provider-key concurrency semaphore actually bounds parallel LLM calls.
* real token accounting records the *actual* input+output usage parsed from a
  provider response (not just the requested ``max_tokens``), reconciling the
  daily budget and feeding the metrics counters.
"""

from __future__ import annotations

import asyncio
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
    LLMConcurrencyLimiter,
    ask_limiter,
    begin_llm_call,
    current_call_attribution,
    end_llm_call,
    llm_concurrency,
    record_llm_tokens,
    register_token_observer,
)
from axiom.vault.crypto import ENV_VAR


@pytest.fixture(autouse=True)
def _reset_limiters() -> Iterator[None]:
    ask_limiter.reset()
    llm_concurrency.reset()
    yield
    ask_limiter.reset()
    llm_concurrency.reset()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'paid-limits.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as test_client:
        yield test_client


# --- A.1 skills/run endpoint is rate-limited -----------------------------


def test_skills_run_returns_429_when_over_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The limiter rejects before run_skill ever touches a paid LLM call."""
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "1")
    ask_limiter.reset()

    # The skill id need not exist: the rate-limit dependency runs first, so the
    # second call is a 429 regardless of whether run_skill would 404 afterwards.
    first = client.post("/api/internal/skills/skill-xyz/run", json={"input_payload": {}})
    assert first.status_code != 429, first.text  # admitted (will 404 inside)
    second = client.post("/api/internal/skills/skill-xyz/run", json={"input_payload": {}})
    assert second.status_code == 429, second.text
    assert "Retry-After" in second.headers
    assert int(second.headers["Retry-After"]) >= 1


def test_skills_run_daily_token_cap_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_ASK_RATE_PER_MIN", "1000")
    # Each skill run pre-charges 1024 tokens; a cap of 1500 admits one then 429s.
    monkeypatch.setenv("AXIOM_ASK_DAILY_TOKEN_CAP", "1500")
    ask_limiter.reset()

    first = client.post("/api/internal/skills/skill-xyz/run", json={"input_payload": {}})
    assert first.status_code != 429, first.text
    second = client.post("/api/internal/skills/skill-xyz/run", json={"input_payload": {}})
    assert second.status_code == 429, second.text


# --- A.4 concurrency semaphore bounds parallel LLM calls -----------------


def test_concurrency_limiter_bounds_parallel_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_LLM_MAX_CONCURRENCY", "2")
    limiter = LLMConcurrencyLimiter()

    async def _drive() -> int:
        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def one_call() -> None:
            nonlocal in_flight, peak
            async with limiter.semaphore_for("token:k"):
                async with lock:
                    in_flight += 1
                    peak = max(peak, in_flight)
                # Hold the slot long enough for siblings to pile up behind it.
                await asyncio.sleep(0.02)
                async with lock:
                    in_flight -= 1

        await asyncio.gather(*(one_call() for _ in range(8)))
        return peak

    peak = asyncio.run(_drive())
    assert peak <= 2, f"semaphore allowed {peak} concurrent calls, expected <= 2"


def test_concurrency_limiter_is_per_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_LLM_MAX_CONCURRENCY", "1")
    limiter = LLMConcurrencyLimiter()
    sem_a = limiter.semaphore_for("token:a")
    sem_b = limiter.semaphore_for("token:b")
    assert sem_a is not sem_b
    # Same key returns the same semaphore object (so the bound is shared).
    assert limiter.semaphore_for("token:a") is sem_a


# --- A.5 real token accounting records actual usage ----------------------


def test_record_llm_tokens_feeds_observer_with_actual_usage() -> None:
    seen: list[tuple[int, int]] = []

    def observer(inp: int, out: int) -> None:
        seen.append((inp, out))

    register_token_observer(observer)
    try:
        record_llm_tokens(37, 11)
    finally:
        # The observer list is module-level; leaving the closure registered is
        # harmless (it only appends to a local list now out of scope), but assert
        # what we recorded.
        pass
    assert (37, 11) in seen


def test_record_llm_tokens_reconciles_daily_budget() -> None:
    limiter = AskRateLimiter()
    key = "token:reconcile"
    # Pre-charge the requested estimate (max_tokens=1024).
    limiter.check(key, 1024, now=1000.0)
    # The real reply used only 12 + 8 = 20 tokens. Reconcile the estimate (same
    # logical "now" so the per-day window does not reset).
    limiter.reconcile(key, requested_tokens=1024, actual_tokens=20, now=1000.0)
    # The charged total dropped from the 1024 estimate to the real 20 tokens.
    _day_start, charged = limiter._tokens[key]
    assert charged == 20


def test_chat_complete_records_actual_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """providers.llm_chat parses usage and records it through the limiter hook."""
    from axiom.providers import llm_chat
    from axiom.providers.llm_chat import ChatMessage, chat_complete

    seen: list[tuple[int, int]] = []
    register_token_observer(lambda inp, out: seen.append((inp, out)))

    # Stub the vault key lookup and the outbound HTTP call.
    monkeypatch.setattr(
        llm_chat,
        "get_provider_key_plaintext_with_session",
        lambda session, provider: "sk-stub",
    )

    def fake_post(
        url: str, *, headers: dict[str, str], json_body: dict[str, Any]
    ) -> dict[str, Any]:
        del url, headers, json_body
        return {
            "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 21, "output_tokens": 5},
        }

    monkeypatch.setattr(llm_chat, "_http_post_json", fake_post)

    key = "token:chat"
    begin_llm_call(key, 1024)
    try:
        # Pre-charge with real wall-clock time so the reconcile inside
        # chat_complete (which also uses real time) lands in the same window.
        ask_limiter.check(key, 1024)
        # Attribution is set so chat_complete reconciles this key.
        assert current_call_attribution() == (key, 1024)
        completion = chat_complete(
            session=object(),
            provider="anthropic",
            messages=[ChatMessage(role="user", content="hello")],
        )
    finally:
        end_llm_call()

    assert completion.usage == {"input_tokens": 21, "output_tokens": 5}
    assert (21, 5) in seen
    # The pre-charged 1024 estimate was reconciled down to the real 26 tokens.
    _, charged = ask_limiter._tokens[key]
    assert charged == 26
