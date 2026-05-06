from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from axiom.sources.base import IngestEvent, Source, SourceMetadata

DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_company.json"


class SyntheticSource(Source):
    source_type = "synthetic"

    def __init__(self, *, fixture_path: Path | None = None, source_id: str = "synthetic-default"):
        self.source_id = source_id
        self.fixture_path = fixture_path or DEFAULT_FIXTURE
        self._data: dict[str, Any] | None = None

    async def discover(self) -> SourceMetadata:
        return SourceMetadata(
            source_id=self.source_id,
            source_type=self.source_type,
            display_name="Synthetic Company (fixture)",
            connected=True,
            last_sync_at=None,
            capabilities={"supports_watch": True, "supports_backfill": False},
        )

    def ingest(self, since: datetime | None = None) -> AsyncIterator[IngestEvent]:
        del since  # snapshot fixture; not incremental

        async def _gen() -> AsyncIterator[IngestEvent]:
            if self._data is None:
                self._data = json.loads(self.fixture_path.read_text(encoding="utf-8"))

            occurred_at = datetime.utcnow()

            entities = self._data.get("entities", [])
            edges = self._data.get("edges", [])

            for i, entity in enumerate(entities):
                yield IngestEvent(
                    event_id=f"{self.source_id}:entity:{i}",
                    event_type="entity_added",
                    source_id=self.source_id,
                    occurred_at=occurred_at,
                    entity=entity,
                    raw=None,
                )

            for i, edge in enumerate(edges):
                yield IngestEvent(
                    event_id=f"{self.source_id}:edge:{i}",
                    event_type="edge_added",
                    source_id=self.source_id,
                    occurred_at=occurred_at,
                    edge=edge,
                    raw=None,
                )

        return _gen()

    def metadata(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "source_type": self.source_type}

    def watch(self, on_event: Callable[[IngestEvent], None]) -> AbstractAsyncContextManager[None]:
        del on_event  # no live changes in fixture

        @asynccontextmanager
        async def _cm() -> AsyncIterator[None]:
            yield None

        return _cm()

    async def disconnect(self) -> None:
        self._data = None

