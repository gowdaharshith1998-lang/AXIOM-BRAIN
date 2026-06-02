from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from axiom.sources.base import IngestEvent, Source, SourceMetadata


def _default_fixture() -> Path:
    """Locate ``fixtures/synthetic_company.json`` across install layouts.

    Resolution order: ``AXIOM_FIXTURE_PATH`` env var → ``<cwd>/fixtures/`` (repo
    checkout or container WORKDIR) → source-relative (editable installs). The
    source-relative path does not exist when the package is pip-installed into
    site-packages, which is why it is the last resort.
    """
    env_path = os.environ.get("AXIOM_FIXTURE_PATH", "").strip()
    if env_path:
        return Path(env_path)
    candidates = [
        Path.cwd() / "fixtures" / "synthetic_company.json",
        Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_company.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Preserve the historical default for error messages when nothing exists.
    return candidates[-1]


# Kept as a module-level name for backwards compatibility with existing imports.
DEFAULT_FIXTURE = _default_fixture()


class SyntheticSource(Source):
    source_type = "synthetic"

    def __init__(self, *, fixture_path: Path | None = None, source_id: str = "synthetic-default"):
        self.source_id = source_id
        self.fixture_path = fixture_path or _default_fixture()
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
