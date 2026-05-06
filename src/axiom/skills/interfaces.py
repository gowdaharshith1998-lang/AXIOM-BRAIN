from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    skill_id: str
    version: int
    scope: str
    skill_hash: str
    emitted_at: datetime
    signed_metadata: dict[str, Any]


class SkillsEmitter(ABC):
    @abstractmethod
    def emit_all(self) -> list[SkillDescriptor]:
        raise NotImplementedError("SkillsEmitter.emit_all is stubbed; lands in Phase 8")

    @abstractmethod
    def emit_one(self, process_entity_id: str) -> SkillDescriptor:
        raise NotImplementedError("SkillsEmitter.emit_one is stubbed; lands in Phase 8")

