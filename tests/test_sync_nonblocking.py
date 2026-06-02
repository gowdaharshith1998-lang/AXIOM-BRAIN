from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors import sync_runner
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Base, ConnectorStateRow


def _session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'nonblocking.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            ConnectorStateRow(
                id="slack_state_1",
                connector_id="slack",
                vendor="slack",
                access_token="xoxb-token",
                account_label="Slack Workspace",
                status="connected",
            )
        )
        session.commit()
    return sf


def test_slow_fetcher_does_not_block_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocking fetcher must run off the loop so other coroutines keep ticking.

    The fetcher sleeps 0.5s on a worker thread (via asyncio.to_thread). While it
    runs, a ticker coroutine should advance many times — proving the event loop
    is not wedged.
    """

    def _slow_fetch_users(_state: Any) -> list[dict[str, Any]]:
        time.sleep(0.5)
        return []

    def _empty_fetch_channels(_state: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(sync_runner, "slack_fetch_users", _slow_fetch_users)
    monkeypatch.setattr(sync_runner, "slack_fetch_channels", _empty_fetch_channels)

    sf = _session_factory(tmp_path)

    async def _scenario() -> int:
        ticks = 0
        stop = asyncio.Event()

        async def _ticker() -> None:
            nonlocal ticks
            while not stop.is_set():
                ticks += 1
                await asyncio.sleep(0.01)

        async def _sync() -> None:
            with sf() as session:
                await sync_runner.sync_slack(session, EventBroadcaster())
            stop.set()

        ticker_task = asyncio.create_task(_ticker())
        await _sync()
        await ticker_task
        return ticks

    ticks = asyncio.run(_scenario())

    # 0.5s of blocking work / 0.01s tick interval => dozens of ticks if the loop
    # stayed responsive. If the fetch ran ON the loop, ticks would be ~0-1.
    assert ticks > 10


def test_semaphore_bounds_concurrent_vendor_syncs(monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_vendor must not run more vendors concurrently than the configured cap."""
    monkeypatch.setenv("AXIOM_CONNECTOR_SYNC_CONCURRENCY", "2")
    # Force the cached semaphore to be rebuilt at the new size on the next loop.
    monkeypatch.setattr(sync_runner, "_sync_semaphore", None)
    monkeypatch.setattr(sync_runner, "_sync_semaphore_loop", None)

    current = 0
    peak = 0

    async def _fake_syncer(_session: object, _broadcaster: EventBroadcaster) -> dict[str, Any]:
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.05)
        current -= 1
        return {"vendor": "x", "status": "ok", "ingested": 0}

    vendors = ["github", "linear", "slack", "notion", "gmail"]
    monkeypatch.setattr(sync_runner, "_VENDOR_SYNCERS", dict.fromkeys(vendors, _fake_syncer))

    async def _scenario() -> None:
        broadcaster = EventBroadcaster()
        await asyncio.gather(
            *(sync_runner.sync_vendor(object(), vendor, broadcaster) for vendor in vendors)  # type: ignore[arg-type]
        )

    asyncio.run(_scenario())

    assert peak == 2, f"expected concurrency capped at 2, saw peak={peak}"


def test_concurrency_default_is_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXIOM_CONNECTOR_SYNC_CONCURRENCY", raising=False)
    assert sync_runner.connector_sync_concurrency() == 3


def test_concurrency_invalid_falls_back_to_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_SYNC_CONCURRENCY", "not-a-number")
    assert sync_runner.connector_sync_concurrency() == 3


def test_concurrency_clamped_to_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_CONNECTOR_SYNC_CONCURRENCY", "0")
    assert sync_runner.connector_sync_concurrency() == 1
