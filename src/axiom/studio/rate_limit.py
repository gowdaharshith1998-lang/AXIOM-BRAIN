"""In-process rate limiting and daily token budget for paid LLM endpoints.

Dependency-free (no slowapi/Redis): a single-process limiter suitable for the
single-worker studio deployment. Enforces two independent limits per key:

* a fixed-window request count (default ``AXIOM_ASK_RATE_PER_MIN`` per minute), and
* a per-day token budget (default ``AXIOM_ASK_DAILY_TOKEN_CAP`` tokens) that is
  *pre-charged* by each request's requested ``max_tokens``.

Both limits are checked atomically under a single lock. If either limit would be
exceeded the call raises :class:`RateLimitExceededError` and charges nothing.
"""

from __future__ import annotations

import os
import threading
import time

DEFAULT_RATE_PER_MIN = 10
DEFAULT_DAILY_TOKEN_CAP = 1_000_000

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
