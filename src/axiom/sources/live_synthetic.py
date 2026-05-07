from __future__ import annotations

import asyncio
import inspect
import json
import math
import random
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from axiom.sources.base import IngestEvent, Source, SourceMetadata
from axiom.sources.event_generators import CompanyState, LiveEventGenerator
from axiom.sources.synthetic import DEFAULT_FIXTURE


class LiveSyntheticSource(Source):
    source_type = "synthetic"

    def __init__(
        self,
        *,
        seed_fixture_path: Path | None = None,
        rate_per_second: float = 1 / 8,
        max_events: int | None = None,
        rng_seed: int = 42,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if max_events is not None and max_events < 0:
            raise ValueError("max_events must be non-negative")

        self.source_id = "live-synthetic"
        self.seed_fixture_path = seed_fixture_path or DEFAULT_FIXTURE
        self.rate_per_second = rate_per_second
        self.max_events = max_events
        self.rng_seed = rng_seed
        self.rng = random.Random(rng_seed)
        self._cancelled = asyncio.Event()
        self._events_emitted = 0
        self._sequence = 0
        self._task: asyncio.Task[None] | None = None
        self._base_time = datetime(2026, 1, 1, 0, 0, 0)
        self.state = CompanyState(fixture_path=self.seed_fixture_path)
        self.generator = LiveEventGenerator(rng=self.rng, state=self.state)

    @property
    def events_emitted(self) -> int:
        return self._events_emitted

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    async def discover(self) -> SourceMetadata:
        return SourceMetadata(
            source_id=self.source_id,
            source_type=self.source_type,
            display_name="Live Synthetic Company",
            connected=not self._cancelled.is_set(),
            last_sync_at=None,
            capabilities={
                "supports_watch": True,
                "supports_backfill": True,
                "rate_per_second": self.rate_per_second,
            },
        )

    def ingest(self, since: datetime | None = None) -> AsyncIterator[IngestEvent]:
        del since

        async def _gen() -> AsyncIterator[IngestEvent]:
            data = json.loads(self.seed_fixture_path.read_text(encoding="utf-8"))
            occurred_at = self._base_time

            for i, entity in enumerate(data.get("entities", [])):
                yield IngestEvent(
                    event_id=f"{self.source_id}:seed:entity:{i}",
                    event_type="entity_added",
                    source_id=self.source_id,
                    occurred_at=occurred_at,
                    entity=entity,
                    raw={"live_seed": True},
                )

            for i, edge in enumerate(data.get("edges", [])):
                yield IngestEvent(
                    event_id=f"{self.source_id}:seed:edge:{i}",
                    event_type="edge_added",
                    source_id=self.source_id,
                    occurred_at=occurred_at,
                    edge=edge,
                    raw={"live_seed": True},
                )

        return _gen()

    def metadata(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "rate_per_second": self.rate_per_second,
            "events_emitted": self.events_emitted,
        }

    def watch(self, on_event: Callable[[IngestEvent], None]) -> AbstractAsyncContextManager[None]:
        @asynccontextmanager
        async def _cm() -> AsyncIterator[None]:
            task = asyncio.create_task(self._watch_loop(on_event))
            self._task = task
            try:
                yield None
            finally:
                self.cancel()
                await task
                self._task = None

        return _cm()

    async def disconnect(self) -> None:
        self.cancel()

    def cancel(self) -> None:
        self._cancelled.set()

    def sample_interarrival(self) -> float:
        return -math.log(1 - self.rng.random()) / self.rate_per_second

    def next_event(self) -> IngestEvent:
        generated = self.generator.generate_next()
        self._sequence += 1
        occurred_at = self._base_time + timedelta(seconds=self._sequence)
        return IngestEvent(
            event_id=f"{self.source_id}:live:{self._sequence}",
            event_type=generated.event_type,
            source_id=self.source_id,
            occurred_at=occurred_at,
            entity=generated.entity,
            edge=generated.edge,
            raw={"live_kind": generated.kind, "rng_seed": self.rng_seed},
        )

    async def _watch_loop(self, on_event: Callable[[IngestEvent], None]) -> None:
        while not self._cancelled.is_set():
            if self.max_events is not None and self._events_emitted >= self.max_events:
                return
            if await self._wait_for_next_event():
                return

            event = self.next_event()
            result = cast(Any, on_event(event))
            if inspect.isawaitable(result):
                await result
            self._events_emitted += 1

    async def _wait_for_next_event(self) -> bool:
        delay = self.sample_interarrival()
        try:
            await asyncio.wait_for(self._cancelled.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True
