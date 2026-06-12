from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


class AppWithState(Protocol):
    state: Any


class GaugeChild(Protocol):
    def set(self, value: float) -> None: ...


class Gauge(Protocol):
    def labels(self, *, task: str) -> GaugeChild: ...


def readiness_failures(
    app: AppWithState,
    session_local: sessionmaker[Session],
    task_attrs: Iterable[str],
) -> list[str]:
    failed: list[str] = []

    try:
        with session_local() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        failed.append(f"db: {exc}")

    if not getattr(app.state, "vault_unlocked", False):
        failed.append("vault: locked")

    for attr in task_attrs:
        task = getattr(app.state, attr, None)
        if task is None:
            continue
        done = getattr(task, "done", None)
        if callable(done) and done():
            if getattr(task, "cancelled", lambda: False)():
                continue
            try:
                task_exc = task.exception()
            except Exception:  # noqa: BLE001
                continue
            if task_exc is not None:
                failed.append(f"task {attr}: {task_exc!r}")

    if (
        getattr(app.state, "spa_explicitly_configured", False)
        and getattr(app.state, "spa_serve_enabled", False)
        and not getattr(app.state, "spa_mounted", False)
    ):
        failed.append("spa: configured but not mounted (check AXIOM_FRONTEND_DIST)")

    return failed


def refresh_task_liveness(
    app: AppWithState,
    task_attrs: Iterable[str],
    gauge: Gauge | None,
) -> None:
    if gauge is None:
        return

    for attr in task_attrs:
        task = getattr(app.state, attr, None)
        alive = 0.0
        if task is not None:
            done = getattr(task, "done", None)
            alive = 0.0 if (callable(done) and done()) else 1.0
        gauge.labels(task=attr).set(alive)
