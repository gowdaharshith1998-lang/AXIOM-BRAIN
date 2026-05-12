from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool: str
    params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class MCPServer(ABC):
    @abstractmethod
    def register_tools(self) -> None:
        raise NotImplementedError("MCPServer.register_tools is stubbed; lands in Phase 6")

    @abstractmethod
    async def handle(self, call: ToolCall) -> ToolResult:
        raise NotImplementedError("MCPServer.handle is stubbed; lands in Phase 6")
