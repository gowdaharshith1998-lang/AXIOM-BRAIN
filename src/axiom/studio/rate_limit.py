"""In-process rate limiting and daily token budget for paid LLM endpoints.

Dependency-free (no slowapi/Redis): a single-process limiter suitable for the
single-worker studio deployment. Enforces two independent limits per key:

* a fixed-window request count (default ``AXIOM_ASK_RATE_PER_MIN`` per minute), and
* a per-day token budget (default ``AXIOM_ASK_DAILY_TOKEN_CAP`` tokens) that is
  *pre-charged* by each request's requested ``max_tokens``.

Both limits are checked atomically under a single lock. If either limit would be
exceeded the call raises :class:`RateLimitExceededError` and charges nothing.

Two further coverage pieces live here so every paid-LLM caller (the Ask route,
the skills/run route, the embedding routes, and the MCP query path) can share a
single enforcement surface:

* :class:`LLMConcurrencyLimiter` — a per-provider-key :class:`asyncio.Semaphore`
  (bounded by ``AXIOM_LLM_MAX_CONCURRENCY``, default 4) wrapped around the
  actual outbound LLM call.
* :func:`record_llm_tokens` — real token accounting. ``providers/llm_chat`` calls
  it with the *actual* input+output token counts parsed from the provider
  response, so the daily budget reconciles against reality (not just the
  requested ``max_tokens``) and any registered metrics sink is fed.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable

DEFAULT_RATE_PER_MIN = 10
DEFAULT_DAILY_TOKEN_CAP = 1_000_000
DEFAULT_LLM_MAX_CONCURRENCY = 4

_RATE_WINDOW_SECONDS = 60.0
_DAY_SECONDS = 86_400.0


class RateLimitExceededError(Exception):
    """Raised when a request would exceed a configured limit.

    ``retry_after`` is the number of whole seconds the caller should wait before
    retrying (suitable for an HTTP ``Retry-After`` header). ``detail`` is a
    human-readable explanation suitable for an error body.
    """

    def __init__(self, retry_after: int, detail: str) -> None:
        super().__init__(detail)
        self.retry_after = retry_after
        self.detail = detail


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class AskRateLimiter:
    """Thread-safe per-key request-rate + per-day token-budget limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_start_epoch, request_count_in_window)
        self._windows: dict[str, tuple[float, int]] = {}
        # key -> (day_start_epoch, tokens_charged_today)
        self._tokens: dict[str, tuple[float, int]] = {}

    @property
    def rate_per_min(self) -> int:
        return _env_int("AXIOM_ASK_RATE_PER_MIN", DEFAULT_RATE_PER_MIN)

    @property
    def daily_token_cap(self) -> int:
        return _env_int("AXIOM_ASK_DAILY_TOKEN_CAP", DEFAULT_DAILY_TOKEN_CAP)

    def check(self, key: str, requested_tokens: int, *, now: float | None = None) -> None:
        """Admit one request for ``key`` charging ``requested_tokens``.

        Raises :class:`RateLimitExceededError` (charging nothing) when either the
        per-minute request limit or the per-day token budget would be exceeded.
        """
        if now is None:
            now = time.time()
        requested = max(0, int(requested_tokens))
        rate_limit = self.rate_per_min
        token_cap = self.daily_token_cap

        with self._lock:
            # --- Per-minute fixed-window request limit ---
            window_start, count = self._windows.get(key, (now, 0))
            if now - window_start >= _RATE_WINDOW_SECONDS:
                window_start, count = now, 0
            if count + 1 > rate_limit:
                retry_after = max(1, int(_RATE_WINDOW_SECONDS - (now - window_start)) + 1)
                raise RateLimitExceededError(
                    retry_after=retry_after,
                    detail=(
                        f"Rate limit exceeded: {rate_limit} requests per minute. "
                        f"Retry in {retry_after}s."
                    ),
                )

            # --- Per-day pre-charged token budget ---
            day_start, charged = self._tokens.get(key, (now, 0))
            if now - day_start >= _DAY_SECONDS:
                day_start, charged = now, 0
            if charged + requested > token_cap:
                retry_after = max(1, int(_DAY_SECONDS - (now - day_start)) + 1)
                raise RateLimitExceededError(
                    retry_after=retry_after,
                    detail=(
                        f"Daily token budget exceeded: {token_cap} tokens/day. "
                        f"Retry in {retry_after}s."
                    ),
                )

            # Both checks passed: charge the request.
            self._windows[key] = (window_start, count + 1)
            self._tokens[key] = (day_start, charged + requested)

    def reconcile(
        self,
        key: str,
        requested_tokens: int,
        actual_tokens: int,
        *,
        now: float | None = None,
    ) -> None:
        """Adjust today's charged total from the requested estimate to reality.

        ``check`` pre-charges ``requested_tokens`` (the requested ``max_tokens``)
        before the call. Once the provider returns the real usage, this swaps the
        estimate for the ``actual_tokens`` so the daily budget tracks reality. The
        delta may be negative (most replies are shorter than ``max_tokens``). The
        running total never drops below zero.
        """
        if now is None:
            now = time.time()
        delta = int(actual_tokens) - max(0, int(requested_tokens))
        if delta == 0:
            return
        with self._lock:
            day_start, charged = self._tokens.get(key, (now, 0))
            if now - day_start >= _DAY_SECONDS:
                day_start, charged = now, 0
            self._tokens[key] = (day_start, max(0, charged + delta))

    def reset(self) -> None:
        """Clear all per-key state (intended for tests)."""
        with self._lock:
            self._windows.clear()
            self._tokens.clear()


def rate_limit_key(bearer_token: str | None, client_host: str | None) -> str:
    """Derive a stable limiter key: bearer token if present, else client IP."""
    token = (bearer_token or "").strip()
    if token:
        return f"token:{token}"
    host = (client_host or "").strip()
    return f"ip:{host or 'unknown'}"


# Module-level singleton shared across requests.
ask_limiter = AskRateLimiter()


# --- Per-provider-key concurrency cap (P0-6.4) -------------------------------


class LLMConcurrencyLimiter:
    """Bounds concurrent outbound LLM calls per provider key.

    A buggy or hostile caller can otherwise open an unbounded number of paid LLM
    requests in parallel and both run up the bill and saturate the single
    SQLite-backed process. Each provider key gets its own
    :class:`asyncio.Semaphore` sized to ``AXIOM_LLM_MAX_CONCURRENCY`` (default
    ``4``). The bound is read once per key (the first time the key is seen) so it
    is stable for the life of that key's semaphore.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    @staticmethod
    def max_concurrency() -> int:
        return _env_int("AXIOM_LLM_MAX_CONCURRENCY", DEFAULT_LLM_MAX_CONCURRENCY)

    def semaphore_for(self, key: str) -> asyncio.Semaphore:
        with self._lock:
            sem = self._semaphores.get(key)
            if sem is None:
                sem = asyncio.Semaphore(self.max_concurrency())
                self._semaphores[key] = sem
            return sem

    def reset(self) -> None:
        """Drop all per-key semaphores (intended for tests)."""
        with self._lock:
            self._semaphores.clear()


# Module-level singleton shared across requests.
llm_concurrency = LLMConcurrencyLimiter()


# --- Real token accounting (P0-6.5) ------------------------------------------

# A registered observer is fed every recorded token count so the /metrics layer
# can increment its LLM counters without rate_limit importing the server module
# (which would be a layering inversion). server.create_app() registers a sink
# that forwards to the prometheus counters.
_token_observers: list[Callable[[int, int], None]] = []
_observers_lock = threading.Lock()


def register_token_observer(observer: Callable[[int, int], None]) -> None:
    """Register a sink for actual LLM usage as ``(input_tokens, output_tokens)``.

    Idempotent per observer identity; safe to call from ``create_app`` (which may
    run more than once per process in tests).
    """
    with _observers_lock:
        if observer not in _token_observers:
            _token_observers.append(observer)


def record_llm_tokens(
    input_tokens: int,
    output_tokens: int,
    *,
    key: str | None = None,
    requested_tokens: int | None = None,
) -> None:
    """Account *actual* LLM usage parsed from a provider response.

    * Feeds every registered metrics observer (LLM token counters).
    * When a limiter ``key`` is supplied, reconciles that key's pre-charged daily
      budget against the real total so the cap tracks reality rather than the
      requested ``max_tokens``.

    Safe to call from any thread and even when no observers are registered.
    """
    total = max(0, int(input_tokens)) + max(0, int(output_tokens))
    with _observers_lock:
        observers = list(_token_observers)
    for observer in observers:
        try:
            observer(max(0, int(input_tokens)), max(0, int(output_tokens)))
        except Exception:  # noqa: BLE001 - instrumentation must never break a call
            pass
    if key is not None and requested_tokens is not None:
        ask_limiter.reconcile(key, requested_tokens, total)


# Contextvar-free, thread-local stash so a synchronous chat_complete call deep in
# the stack can attribute its usage to the limiter key + requested budget set by
# the HTTP/MCP entrypoint, without threading those values through every signature.
_current_call = threading.local()


def begin_llm_call(key: str | None, requested_tokens: int | None) -> None:
    """Mark the active thread as servicing one limiter-attributed LLM call."""
    _current_call.key = key
    _current_call.requested_tokens = requested_tokens


def end_llm_call() -> None:
    """Clear the active thread's limiter attribution."""
    _current_call.key = None
    _current_call.requested_tokens = None


def current_call_attribution() -> tuple[str | None, int | None]:
    """Return the active thread's ``(key, requested_tokens)`` attribution."""
    return (
        getattr(_current_call, "key", None),
        getattr(_current_call, "requested_tokens", None),
    )
