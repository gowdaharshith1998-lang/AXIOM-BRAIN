from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

SourceType = Literal["linear", "slack", "gmail", "drive", "github", "synthetic"]


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_id: str
    source_type: SourceType
    display_name: str
    connected: bool
    last_sync_at: datetime | None
    capabilities: dict[str, Any]


IngestEventType = Literal[
    "entity_added",
    "entity_modified",
    "entity_removed",
    "edge_added",
    "edge_removed",
]


@dataclass(frozen=True, slots=True)
class IngestEvent:
    event_id: str
    event_type: IngestEventType
    source_id: str
    occurred_at: datetime
    entity: dict[str, Any] | None = None
    edge: dict[str, Any] | None = None
    external_ref: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


class Source(ABC):
    source_id: str
    source_type: SourceType

    @abstractmethod
    async def discover(self) -> SourceMetadata:
        raise NotImplementedError("Source.discover is stubbed; lands in Phase 12+")

    @abstractmethod
    async def ingest(self, since: datetime | None = None) -> AsyncIterator[IngestEvent]:
        raise NotImplementedError("Source.ingest is stubbed; lands in Phase 12+")

    @abstractmethod
    async def watch(
        self, on_event: Callable[[IngestEvent], None]
    ) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError("Source.watch is stubbed; lands in Phase 12+")

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError("Source.disconnect is stubbed; lands in Phase 12+")

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        raise NotImplementedError("Source.metadata is stubbed; lands in Phase 12+")

