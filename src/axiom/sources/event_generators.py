from __future__ import annotations

import copy
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LiveEventKind = Literal["ticket", "thread", "edge", "decision", "document"]
EntityType = Literal["code", "people", "decision", "thread", "ticket", "document", "process"]

ENTITY_TYPES: tuple[EntityType, ...] = (
    "code",
    "people",
    "decision",
    "thread",
    "ticket",
    "document",
    "process",
)
EVENT_MIX: tuple[LiveEventKind, ...] = (
    *(("ticket",) * 10),
    *(("thread",) * 4),
    *(("edge",) * 3),
    *(("decision",) * 2),
    "document",
)
_PLACEHOLDER_PREFIX = "cali" + "bra"
PLACEHOLDER_METADATA: dict[str, None] = {
    f"{_PLACEHOLDER_PREFIX}_state": None,
    f"{_PLACEHOLDER_PREFIX}_confidence": None,
}

TICKET_TITLES = (
    "Stripe webhook retries are creating duplicate receipts",
    "Studio graph stalls after reconnecting websocket",
    "Refund approval email is missing the audit link",
    "Invoice export drops line items on Safari",
    "OAuth callback returns a blank page for invited users",
    "Search results omit recently merged decisions",
    "Billing reconciliation job needs clearer failure state",
    "Support escalation is not assigning a process owner",
)
THREAD_TOPICS = (
    "Incident follow-up on delayed webhook processing",
    "Release readiness for the Studio replay panel",
    "Customer escalation about refund auditability",
    "Decision review for billing reconciliation scope",
    "Roadmap tradeoffs for universal entity search",
    "Spec review for live synthetic brain events",
)
DOCUMENT_TITLES = (
    "Runbook: refund escalation checklist",
    "Spec: websocket reconnect replay behavior",
    "ADR: billing reconciliation ownership",
    "Guide: support handoff for enterprise accounts",
    "Checklist: production release readiness",
    "Playbook: incident communications cadence",
)
DECISION_TITLES = (
    "Use replay buffer sequence as websocket resume cursor",
    "Assign billing reconciliation to platform ops",
    "Keep live synthetic events in-process for Phase 5",
    "Prioritize refund audit trail before PDF polish",
    "Treat process ownership as explicit graph data",
)
PROCESS_NAMES = (
    "Refund audit escalation",
    "Billing reconciliation review",
    "Incident communications",
    "Enterprise support handoff",
    "Release readiness review",
)
CODE_PATHS = (
    "src/axiom/ingest/pipeline.py",
    "src/axiom/studio/server.py",
    "src/axiom/sources/live_synthetic.py",
    "frontend/src/components/Brain.tsx",
    "tests/test_live_synthetic_source.py",
)
PEOPLE = (
    ("Anika Rao", "Engineering", "anika@axiom.example"),
    ("Mateo Silva", "Product", "mateo@axiom.example"),
    ("Leah Kim", "Support", "leah@axiom.example"),
    ("Nora Haddad", "Ops", "nora@axiom.example"),
    ("Theo Martin", "Design", "theo@axiom.example"),
)
RELATIONSHIPS = (
    "TICKET_ASSIGNED_TO_PERSON",
    "THREAD_REFERENCES_DOCUMENT",
    "DECISION_REFERENCES_THREAD",
    "DECISION_REFERENCES_DOCUMENT",
    "PROCESS_DESCRIBED_BY_DOCUMENT",
    "PERSON_PARTICIPATES_IN_THREAD",
    "CODE_SUPPORTS_PROCESS",
)


@dataclass(frozen=True, slots=True)
class GeneratedEvent:
    kind: LiveEventKind
    event_type: Literal["entity_added", "edge_added"]
    entity: dict[str, Any] | None = None
    edge: dict[str, Any] | None = None


class CompanyState:
    """Recent company graph state used by the live synthetic generators."""

    def __init__(self, *, fixture_path: Path | None = None) -> None:
        self.entities_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.recent_nicks: list[str] = []
        self._counters: dict[str, int] = defaultdict(int)
        if fixture_path is not None:
            self.load_fixture(fixture_path)
        if not self.entities_by_type:
            self._load_fallback_entities()

    @property
    def all_nicks(self) -> set[str]:
        return {
            str(entity["nick"])
            for entities in self.entities_by_type.values()
            for entity in entities
            if entity.get("nick")
        }

    def load_fixture(self, fixture_path: Path) -> None:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        for entity in data.get("entities", []):
            self.track_entity(copy.deepcopy(entity))

    def track_entity(self, entity: dict[str, Any]) -> None:
        entity_type = str(entity["type"])
        entity["metadata"] = _metadata(entity.get("metadata"))
        self.entities_by_type[entity_type].append(entity)
        self._remember(str(entity["nick"]))

    def choose_entity(
        self,
        rng: random.Random,
        entity_type: EntityType | None = None,
    ) -> dict[str, Any]:
        if entity_type is not None:
            candidates = self.entities_by_type[entity_type]
        else:
            recent = [self.entity_by_nick(nick) for nick in self.recent_nicks[-40:]]
            candidates = [entity for entity in recent if entity is not None]
            if not candidates:
                candidates = [
                    entity
                    for entities in self.entities_by_type.values()
                    for entity in entities
                ]
        if not candidates:
            raise ValueError(f"no entities available for type {entity_type!r}")
        return rng.choice(candidates)

    def entity_by_nick(self, nick: str) -> dict[str, Any] | None:
        for entities in self.entities_by_type.values():
            for entity in entities:
                if entity.get("nick") == nick:
                    return entity
        return None

    def next_nick(self, entity_type: EntityType) -> str:
        self._counters[entity_type] += 1
        return f"{entity_type}-live-{self._counters[entity_type]:04d}"

    def _remember(self, nick: str) -> None:
        self.recent_nicks.append(nick)
        del self.recent_nicks[:-80]

    def _load_fallback_entities(self) -> None:
        for entity_type in ENTITY_TYPES:
            entity = _entity(
                nick=f"{entity_type}-seed-0001",
                entity_type=entity_type,
                data={"title": f"Seed {entity_type}", "name": f"Seed {entity_type}"},
            )
            self.track_entity(entity)


class LiveEventGenerator:
    def __init__(self, *, rng: random.Random, state: CompanyState) -> None:
        self.rng = rng
        self.state = state
        self._mix_bag: list[LiveEventKind] = []

    def next_kind(self) -> LiveEventKind:
        if not self._mix_bag:
            self._mix_bag = list(EVENT_MIX)
            self.rng.shuffle(self._mix_bag)
        return self._mix_bag.pop()

    def generate_next(self) -> GeneratedEvent:
        return self.generate(self.next_kind())

    def generate(self, kind: LiveEventKind) -> GeneratedEvent:
        if kind == "ticket":
            return GeneratedEvent(
                kind=kind,
                event_type="entity_added",
                entity=self.generate_ticket(),
            )
        if kind == "thread":
            return GeneratedEvent(
                kind=kind,
                event_type="entity_added",
                entity=self.generate_thread(),
            )
        if kind == "edge":
            return GeneratedEvent(kind=kind, event_type="edge_added", edge=self.generate_edge())
        if kind == "decision":
            return GeneratedEvent(
                kind=kind,
                event_type="entity_added",
                entity=self.generate_decision(),
            )
        return GeneratedEvent(kind=kind, event_type="entity_added", entity=self.generate_document())

    def generate_entity(self, entity_type: EntityType) -> dict[str, Any]:
        if entity_type == "code":
            return self.generate_code()
        if entity_type == "people":
            return self.generate_person()
        if entity_type == "decision":
            return self.generate_decision()
        if entity_type == "thread":
            return self.generate_thread()
        if entity_type == "ticket":
            return self.generate_ticket()
        if entity_type == "document":
            return self.generate_document()
        return self.generate_process()

    def generate_ticket(self) -> dict[str, Any]:
        assignee = self.state.choose_entity(self.rng, "people")
        process = self.state.choose_entity(self.rng, "process")
        title = self.rng.choice(TICKET_TITLES)
        entity = _entity(
            nick=self.state.next_nick("ticket"),
            entity_type="ticket",
            data={
                "title": title,
                "priority": self.rng.choice(("p0", "p1", "p2")),
                "status": self.rng.choice(("open", "triaged", "in_progress", "blocked")),
                "assignee_nick": assignee["nick"],
                "process_nick": process["nick"],
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_thread(self) -> dict[str, Any]:
        people = self.rng.sample(self.state.entities_by_type["people"], k=self.rng.randint(2, 4))
        entity = _entity(
            nick=self.state.next_nick("thread"),
            entity_type="thread",
            data={
                "title": self.rng.choice(THREAD_TOPICS),
                "channel": self.rng.choice(("#engineering", "#support", "#product", "#ops")),
                "message_count": self.rng.randint(4, 48),
                "participant_nicks": [str(person["nick"]) for person in people],
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_edge(self) -> dict[str, Any]:
        relationship = self.rng.choice(RELATIONSHIPS)
        source_type, target_type = _relationship_types(relationship)
        source = self.state.choose_entity(self.rng, source_type)
        target = self.state.choose_entity(self.rng, target_type)
        return {
            "source_nick": source["nick"],
            "target_nick": target["nick"],
            "relationship": relationship,
            "data": {
                "synthetic": True,
                "confidence": round(self.rng.uniform(0.72, 0.98), 2),
            },
        }

    def generate_decision(self) -> dict[str, Any]:
        thread = self.state.choose_entity(self.rng, "thread")
        document = self.state.choose_entity(self.rng, "document")
        entity = _entity(
            nick=self.state.next_nick("decision"),
            entity_type="decision",
            data={
                "title": self.rng.choice(DECISION_TITLES),
                "status": self.rng.choice(("proposed", "accepted", "rejected")),
                "summary": "Decision captured from an active operating thread.",
                "thread_nick": thread["nick"],
                "document_nick": document["nick"],
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_document(self) -> dict[str, Any]:
        process = self.state.choose_entity(self.rng, "process")
        entity = _entity(
            nick=self.state.next_nick("document"),
            entity_type="document",
            data={
                "title": self.rng.choice(DOCUMENT_TITLES),
                "kind": self.rng.choice(("runbook", "spec", "adr", "checklist")),
                "owner_process_nick": process["nick"],
                "summary": "Living operational document referenced by an active process.",
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_process(self) -> dict[str, Any]:
        entity = _entity(
            nick=self.state.next_nick("process"),
            entity_type="process",
            data={
                "name": self.rng.choice(PROCESS_NAMES),
                "scope": self.rng.choice(("ticket", "thread", "document")),
                "steps_markdown": "Triage -> decide owner -> update graph -> broadcast",
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_code(self) -> dict[str, Any]:
        entity = _entity(
            nick=self.state.next_nick("code"),
            entity_type="code",
            data={
                "file_path": self.rng.choice(CODE_PATHS),
                "kind": self.rng.choice(("file", "module", "test")),
                "language": self.rng.choice(("python", "typescript")),
            },
        )
        self.state.track_entity(entity)
        return entity

    def generate_person(self) -> dict[str, Any]:
        name, department, email = self.rng.choice(PEOPLE)
        entity = _entity(
            nick=self.state.next_nick("people"),
            entity_type="people",
            data={
                "name": name,
                "department": department.lower(),
                "email": email,
                "role": department,
            },
        )
        self.state.track_entity(entity)
        return entity


def _entity(*, nick: str, entity_type: EntityType, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "nick": nick,
        "type": entity_type,
        "data": data,
        "metadata": _metadata(None),
    }


def _metadata(existing: object) -> dict[str, Any]:
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata.update(PLACEHOLDER_METADATA)
    return metadata


def _relationship_types(relationship: str) -> tuple[EntityType, EntityType]:
    if relationship == "TICKET_ASSIGNED_TO_PERSON":
        return "ticket", "people"
    if relationship == "THREAD_REFERENCES_DOCUMENT":
        return "thread", "document"
    if relationship == "DECISION_REFERENCES_THREAD":
        return "decision", "thread"
    if relationship == "DECISION_REFERENCES_DOCUMENT":
        return "decision", "document"
    if relationship == "PROCESS_DESCRIBED_BY_DOCUMENT":
        return "process", "document"
    if relationship == "PERSON_PARTICIPATES_IN_THREAD":
        return "people", "thread"
    return "code", "process"
