from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.studio.health import readiness_failures, refresh_task_liveness


def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine("sqlite://"))


def test_readiness_failures_reports_locked_vault() -> None:
    app = SimpleNamespace(state=SimpleNamespace(vault_unlocked=False))

    failures = readiness_failures(app, _session_factory(), task_attrs=())

    assert failures == ["vault: locked"]


def test_readiness_failures_reports_failed_background_task() -> None:
    app = SimpleNamespace(state=SimpleNamespace(vault_unlocked=True))
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(_raise_runtime_error())
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        app.state.connector_sync_task = task

        failures = readiness_failures(app, _session_factory(), task_attrs=("connector_sync_task",))
    finally:
        loop.close()

    assert failures == ["task connector_sync_task: RuntimeError('sync stopped')"]


def test_readiness_failures_reports_missing_configured_spa() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            vault_unlocked=True,
            spa_explicitly_configured=True,
            spa_serve_enabled=True,
            spa_mounted=False,
        )
    )

    failures = readiness_failures(app, _session_factory(), task_attrs=())

    assert failures == ["spa: configured but not mounted (check AXIOM_FRONTEND_DIST)"]


def test_refresh_task_liveness_sets_alive_and_stopped_values() -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    loop = asyncio.new_event_loop()
    try:
        done_task = loop.create_task(_return_none())
        loop.run_until_complete(done_task)
        pending_task = loop.create_task(_sleep_forever())
        app.state.done_task = done_task
        app.state.pending_task = pending_task
        gauge = _FakeGauge()

        refresh_task_liveness(app, ("done_task", "pending_task", "missing_task"), gauge)
    finally:
        pending_task.cancel()
        loop.run_until_complete(asyncio.gather(pending_task, return_exceptions=True))
        loop.close()

    assert gauge.values == {
        "done_task": 0.0,
        "pending_task": 1.0,
        "missing_task": 0.0,
    }


async def _raise_runtime_error() -> None:
    raise RuntimeError("sync stopped")


async def _return_none() -> None:
    return None


async def _sleep_forever() -> None:
    await asyncio.Event().wait()


class _FakeGauge:
    def __init__(self) -> None:
        self.values: dict[str, float] = {}

    def labels(self, *, task: str) -> _FakeGaugeLabel:
        return _FakeGaugeLabel(self.values, task)


class _FakeGaugeLabel:
    def __init__(self, values: dict[str, float], task: str) -> None:
        self._values = values
        self._task = task

    def set(self, value: Any) -> None:
        self._values[self._task] = float(value)
