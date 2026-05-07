from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

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


class IngestPipeline(ABC):
    @abstractmethod
    async def run(self, *, since: datetime | None = None) -> AsyncIterator[IngestEvent]:
        raise NotImplementedError("IngestPipeline.run is stubbed; lands in Phase 3")

