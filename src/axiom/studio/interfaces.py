from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

WebSocketEventType = Literal[
    "bootstrap_complete",
    "entity_added",
    "entity_modified",
    "entity_removed",
    "edge_added",
    "edge_removed",
    "receipt_emitted",
    "agent_action_signed",
    "correct_signal_emitted",
    "deny_signal_emitted",
    "skill_emitted",
    "source_connected",
    "source_disconnected",
    "source_sync_started",
    "source_sync_completed",
    "policy_decision_made",
    "approval_queue_updated",
    "stats",
]


@dataclass(frozen=True, slots=True)
class WebSocketEvent:
    type: WebSocketEventType
    timestamp_ms: int
    payload: dict[str, Any]


class StudioEventStream(ABC):
    @abstractmethod
    async def subscribe(self, *, since_seq: int | None = None) -> AsyncIterator[WebSocketEvent]:
        raise NotImplementedError("StudioEventStream.subscribe is stubbed; lands in Phase 4")

    @abstractmethod
    def publish(self, event: WebSocketEvent) -> None:
        raise NotImplementedError("StudioEventStream.publish is stubbed; lands in Phase 4")
