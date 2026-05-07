from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "fixtures" / "synthetic_company.json"
SEED = 42


ENTITY_COUNTS: dict[str, int] = {
    "people": 8,
    "thread": 36,
    "ticket": 18,
    "document": 14,
    "decision": 10,
    "process": 8,
    "code": 6,
}


@dataclass(frozen=True)
class EntitySpec:
    nick: str
    type: str
    data: dict[str, Any]


def _meta() -> dict[str, Any]:
    # Phase 7 populates; fixture keeps inert null placeholders.
    return {"calibra_state": None, "calibra_confidence": None}


def _mk_people(rng: random.Random, n: int) -> list[EntitySpec]:
    names = [
        ("Asha", "Patel"),
        ("Kwame", "Mensah"),
        ("Yuki", "Tanaka"),
        ("Pratiksha", "Iyer"),
        ("Diego", "Santos"),
        ("Mina", "Hassan"),
        ("Oksana", "Kovalenko"),
        ("Samir", "Khan"),
    ]
    roles = [
        "Founder",
        "Engineering",
        "Product",
        "Design",
        "Customer Support",
        "Sales",
        "Marketing",
        "Ops",
    ]
    people: list[EntitySpec] = []
    for i in range(n):
        first, last = names[i % len(names)]
        role = roles[i % len(roles)]
        nick = f"person-{first.lower()}-{last.lower()}"
        people.append(
            EntitySpec(
                nick=nick,
                type="people",
                data={
                    "name": f"{first} {last}",
                    "role": role,
                    "email": f"{first.lower()}@axiom.example",
                    "department": role.split()[0].lower(),
                },
            )
        )
    rng.shuffle(people)
    return people


def _mk_threads(rng: random.Random, n: int) -> list[EntitySpec]:
    channels = ["#support-escalations", "#product", "#engineering", "#ops", "#growth"]
    titles = [
        "Support escalation: billing mismatch",
        "Release plan: onboarding v3",
        "Incident follow-up: webhook latency",
        "Decision review: refunds threshold",
        "Spec discussion: studio websocket replay",
        "Customer feedback: export format",
        "Bug triage: OAuth callback",
        "Roadmap: Q2 priorities",
    ]
    threads: list[EntitySpec] = []
    for i in range(n):
        nick = f"thread-{i:02d}"
        threads.append(
            EntitySpec(
                nick=nick,
                type="thread",
                data={
                    "title": f"{titles[i % len(titles)]} ({i+1})",
                    "channel": channels[i % len(channels)],
                    "message_count": rng.randint(3, 42),
                },
            )
        )
    return threads


def _mk_tickets(rng: random.Random, n: int) -> list[EntitySpec]:
    titles = [
        "OAuth callback fails on Safari",
        "Stripe webhook timeout > 30s",
        "Invoice PDF export truncates long names",
        "Refund flow missing audit trail",
        "Emails not threading correctly",
        "Edge traversal returns duplicates",
        "Studio HUD flickers on reconnect",
        "DB migration fails on fresh clone",
    ]
    statuses = ["open", "in_progress", "blocked", "done", "triaged"]
    tickets: list[EntitySpec] = []
    for i in range(n):
        nick = f"ticket-{i:02d}"
        tickets.append(
            EntitySpec(
                nick=nick,
                type="ticket",
                data={
                    "title": f"{titles[i % len(titles)]} [{i+1}]",
                    "status": statuses[i % len(statuses)],
                    "priority": ["p0", "p1", "p2"][i % 3],
                },
            )
        )
    return tickets


def _mk_documents(rng: random.Random, n: int) -> list[EntitySpec]:
    doc_types = ["policy", "spec", "memo", "runbook", "onboarding"]
    titles = [
        "Refund Policy 2026",
        "Engineering Onboarding v3",
        "Incident Response Runbook",
        "Studio Protocol: WebSocket Replay",
        "Support Escalation Guidelines",
        "Billing Reconciliation Notes",
        "Data Model Conventions",
        "Customer Comms Templates",
    ]
    docs: list[EntitySpec] = []
    for i in range(n):
        nick = f"doc-{i:02d}"
        docs.append(
            EntitySpec(
                nick=nick,
                type="document",
                data={
                    "title": f"{titles[i % len(titles)]} (v{1 + (i % 3)})",
                    "doc_type": doc_types[i % len(doc_types)],
                    "excerpt": "…",
                },
            )
        )
    rng.shuffle(docs)
    return docs


def _mk_decisions(rng: random.Random, n: int) -> list[EntitySpec]:
    titles = [
        "Standardize on Postgres for billing",
        "Default policy stance is permissive with CORRECT steering",
        "Adopt UUIDv7 for all primary keys",
        "Ship Studio WebGPU-first with WebGL fallback",
        "Define universal entity types as free-text strings",
    ]
    statuses = ["proposed", "accepted", "rejected"]
    decisions: list[EntitySpec] = []
    for i in range(n):
        nick = f"decision-{i:02d}"
        decisions.append(
            EntitySpec(
                nick=nick,
                type="decision",
                data={
                    "title": f"{titles[i % len(titles)]} ({i+1})",
                    "status": statuses[(i + 1) % len(statuses)],
                    "summary": "A concrete call made with a clear rationale and follow-ups.",
                },
            )
        )
    return decisions


def _mk_processes(rng: random.Random, n: int) -> list[EntitySpec]:
    names = [
        "Customer refund processing",
        "Incident response",
        "Support escalation",
        "Release checklist",
        "Billing reconciliation",
        "Onboarding new engineer",
        "Quarterly planning",
        "Security review",
    ]
    processes: list[EntitySpec] = []
    for i in range(n):
        nick = f"process-{i:02d}"
        processes.append(
            EntitySpec(
                nick=nick,
                type="process",
                data={
                    "name": names[i % len(names)],
                    "scope": ["ticket", "thread", "document"][i % 3],
                    "steps_markdown": "Validate → decide → update → record",
                },
            )
        )
    rng.shuffle(processes)
    return processes


def _mk_code(rng: random.Random, n: int) -> list[EntitySpec]:
    paths = [
        "src/axiom/ingest/pipeline.py",
        "src/axiom/studio/server.py",
        "src/axiom/storage/crud.py",
        "frontend/src/components/Brain.tsx",
        "scripts/generate_fixture.py",
        "src/axiom/sources/synthetic.py",
    ]
    kinds = ["file", "module"]
    langs = ["python", "typescript"]
    code: list[EntitySpec] = []
    for i in range(n):
        nick = f"code-{i:02d}"
        code.append(
            EntitySpec(
                nick=nick,
                type="code",
                data={
                    "file_path": paths[i % len(paths)],
                    "language": langs[i % len(langs)],
                    "kind": kinds[i % len(kinds)],
                },
            )
        )
    rng.shuffle(code)
    return code


def _entity_dict(spec: EntitySpec) -> dict[str, Any]:
    return {"nick": spec.nick, "type": spec.type, "data": spec.data, "metadata": _meta()}


def main() -> None:
    rng = random.Random(SEED)

    people = _mk_people(rng, ENTITY_COUNTS["people"])
    threads = _mk_threads(rng, ENTITY_COUNTS["thread"])
    tickets = _mk_tickets(rng, ENTITY_COUNTS["ticket"])
    docs = _mk_documents(rng, ENTITY_COUNTS["document"])
    decisions = _mk_decisions(rng, ENTITY_COUNTS["decision"])
    processes = _mk_processes(rng, ENTITY_COUNTS["process"])
    code = _mk_code(rng, ENTITY_COUNTS["code"])

    entities_specs = [*people, *threads, *tickets, *docs, *decisions, *processes, *code]

    # Stable output order (deterministic across runs).
    entities_specs.sort(key=lambda e: (e.type, e.nick))

    nicks_by_type: dict[str, list[str]] = {}
    for e in entities_specs:
        nicks_by_type.setdefault(e.type, []).append(e.nick)

    def pick(type_: str) -> str:
        return rng.choice(nicks_by_type[type_])

    edges: list[dict[str, Any]] = []

    def edge(src: str, tgt: str, rel: str, data: dict[str, Any] | None = None) -> None:
        edges.append(
            {"source_nick": src, "target_nick": tgt, "relationship": rel, "data": data or {}}
        )

    # 5 long chains: Decision → Thread → Person → Ticket → Process → Document
    chain_threads = nicks_by_type["thread"][:5]
    chain_people = nicks_by_type["people"][:5]
    chain_tickets = nicks_by_type["ticket"][:5]
    chain_processes = nicks_by_type["process"][:5]
    chain_docs = nicks_by_type["document"][:5]
    chain_decisions = nicks_by_type["decision"][:5]
    for i in range(5):
        edge(chain_decisions[i], chain_threads[i], "DECISION_REFERENCES_THREAD")
        edge(chain_decisions[i], chain_docs[i], "DECISION_REFERENCES_DOCUMENT")
        edge(chain_people[i], chain_threads[i], "PERSON_PARTICIPATES_IN_THREAD")
        edge(chain_tickets[i], chain_people[i], "TICKET_ASSIGNED_TO_PERSON")
        edge(chain_tickets[i], chain_processes[i], "TICKET_BELONGS_TO_PROCESS")
        edge(chain_processes[i], chain_docs[i], "PROCESS_DESCRIBED_BY_DOCUMENT")

    # Every person participates in >= 2 threads.
    for p in nicks_by_type["people"]:
        for _ in range(2):
            edge(p, pick("thread"), "PERSON_PARTICIPATES_IN_THREAD")

    # Every ticket assigned + belongs to a process.
    for t in nicks_by_type["ticket"]:
        edge(t, pick("people"), "TICKET_ASSIGNED_TO_PERSON")
        edge(t, pick("process"), "TICKET_BELONGS_TO_PROCESS")

    # Every decision references >= 1 thread + >= 1 document.
    for d in nicks_by_type["decision"]:
        edge(d, pick("thread"), "DECISION_REFERENCES_THREAD")
        edge(d, pick("document"), "DECISION_REFERENCES_DOCUMENT")

    # Every process described by >= 2 documents.
    for p in nicks_by_type["process"]:
        for _ in range(2):
            edge(p, pick("document"), "PROCESS_DESCRIBED_BY_DOCUMENT")

    # Every document referenced by >= 1 decision OR process (already mostly satisfied).
    for doc in nicks_by_type["document"]:
        edge(pick("decision"), doc, "DECISION_REFERENCES_DOCUMENT")

    # Every code associated with >= 1 process or ticket.
    for c in nicks_by_type["code"]:
        edge(c, pick("process"), "CODE_IMPLEMENTS_PROCESS")
        edge(c, pick("ticket"), "CODE_RESOLVES_TICKET")

    # Density / cross-category edges (no entity-type branching downstream).
    # Add extra edges until >=170 (gives margin over 150).
    relationships = [
        ("people", "ticket", "PERSON_WATCHES_TICKET"),
        ("people", "document", "PERSON_AUTHORED_DOCUMENT"),
        ("thread", "ticket", "THREAD_DISCUSSES_TICKET"),
        ("document", "decision", "DOCUMENT_REFERENCED_BY_DECISION"),
        ("process", "thread", "PROCESS_REFERENCES_THREAD"),
        ("ticket", "document", "TICKET_REFERENCES_DOCUMENT"),
        ("thread", "document", "THREAD_REFERENCES_DOCUMENT"),
        ("ticket", "decision", "TICKET_IMPACTS_DECISION"),
    ]

    while len(edges) < 170:
        a, b, rel = rng.choice(relationships)
        edge(pick(a), pick(b), rel)

    payload = {
        "seed": SEED,
        "entities": [_entity_dict(e) for e in entities_specs],
        "edges": edges,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

