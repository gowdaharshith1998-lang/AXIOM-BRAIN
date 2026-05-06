from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def _load_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "synthetic_company.json"
    assert path.exists()
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_parses_and_counts() -> None:
    d = _load_fixture()
    assert "entities" in d
    assert "edges" in d

    entities = d["entities"]
    edges = d["edges"]

    assert len(entities) == 100
    assert len(edges) >= 150

    types = Counter(e["type"] for e in entities)
    assert types == Counter(
        {
            "people": 8,
            "thread": 36,
            "ticket": 18,
            "document": 14,
            "decision": 10,
            "process": 8,
            "code": 6,
        }
    )


def test_fixture_entity_shape_and_nick_uniqueness() -> None:
    d = _load_fixture()
    entities = d["entities"]
    nicks: set[str] = set()

    for e in entities:
        assert set(e.keys()) == {"data", "metadata", "nick", "type"}
        assert isinstance(e["nick"], str) and e["nick"]
        assert e["nick"] not in nicks
        nicks.add(e["nick"])

        assert isinstance(e["data"], dict)
        assert isinstance(e["metadata"], dict)
        assert e["metadata"].get("calibra_state") is None
        assert e["metadata"].get("calibra_confidence") is None


def test_fixture_edges_resolve_and_minimum_invariants() -> None:
    d = _load_fixture()
    entities = d["entities"]
    edges = d["edges"]

    nick_to_type = {e["nick"]: e["type"] for e in entities}

    for ed in edges:
        assert set(ed.keys()) == {"data", "relationship", "source_nick", "target_nick"}
        assert ed["source_nick"] in nick_to_type
        assert ed["target_nick"] in nick_to_type
        assert isinstance(ed["relationship"], str) and ed["relationship"]

    # Required minimums (checked structurally by relationship labels).
    by_rel: dict[str, list[dict]] = defaultdict(list)
    for ed in edges:
        by_rel[ed["relationship"]].append(ed)

    # Every person participates in >= 2 threads.
    person_to_threads: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["PERSON_PARTICIPATES_IN_THREAD"]:
        person_to_threads[ed["source_nick"]].add(ed["target_nick"])

    people = [e["nick"] for e in entities if e["type"] == "people"]
    assert all(len(person_to_threads[p]) >= 2 for p in people)

    # Every ticket has >= 1 assignee person.
    ticket_to_assignees: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["TICKET_ASSIGNED_TO_PERSON"]:
        ticket_to_assignees[ed["source_nick"]].add(ed["target_nick"])
    tickets = [e["nick"] for e in entities if e["type"] == "ticket"]
    assert all(len(ticket_to_assignees[t]) >= 1 for t in tickets)

    # Every ticket belongs to >= 1 process.
    ticket_to_processes: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["TICKET_BELONGS_TO_PROCESS"]:
        ticket_to_processes[ed["source_nick"]].add(ed["target_nick"])
    assert all(len(ticket_to_processes[t]) >= 1 for t in tickets)

    # Every decision references >= 1 thread and >= 1 document.
    decision_to_threads: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["DECISION_REFERENCES_THREAD"]:
        decision_to_threads[ed["source_nick"]].add(ed["target_nick"])
    decision_to_docs: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["DECISION_REFERENCES_DOCUMENT"]:
        decision_to_docs[ed["source_nick"]].add(ed["target_nick"])

    decisions = [e["nick"] for e in entities if e["type"] == "decision"]
    assert all(len(decision_to_threads[d]) >= 1 for d in decisions)
    assert all(len(decision_to_docs[d]) >= 1 for d in decisions)

    # Every process described by >= 2 documents.
    process_to_docs: dict[str, set[str]] = defaultdict(set)
    for ed in by_rel["PROCESS_DESCRIBED_BY_DOCUMENT"]:
        process_to_docs[ed["source_nick"]].add(ed["target_nick"])
    processes = [e["nick"] for e in entities if e["type"] == "process"]
    assert all(len(process_to_docs[p]) >= 2 for p in processes)

    # Every code associated with >= 1 process or ticket.
    code_to_any: dict[str, int] = defaultdict(int)
    for rel in ("CODE_IMPLEMENTS_PROCESS", "CODE_RESOLVES_TICKET"):
        for ed in by_rel[rel]:
            code_to_any[ed["source_nick"]] += 1
    codes = [e["nick"] for e in entities if e["type"] == "code"]
    assert all(code_to_any[c] >= 1 for c in codes)


def test_fixture_contains_at_least_five_long_chains() -> None:
    d = _load_fixture()
    entities = d["entities"]
    edges = d["edges"]

    by_rel: dict[str, list[dict]] = defaultdict(list)
    for ed in edges:
        by_rel[ed["relationship"]].append(ed)

    # Build adjacency for chain search on nicks.
    def links(rel: str) -> dict[str, set[str]]:
        m: dict[str, set[str]] = defaultdict(set)
        for ed in by_rel.get(rel, []):
            m[ed["source_nick"]].add(ed["target_nick"])
        return m

    dec_to_thread = links("DECISION_REFERENCES_THREAD")
    person_to_thread = links("PERSON_PARTICIPATES_IN_THREAD")
    ticket_to_person = links("TICKET_ASSIGNED_TO_PERSON")
    ticket_to_process = links("TICKET_BELONGS_TO_PROCESS")
    process_to_doc = links("PROCESS_DESCRIBED_BY_DOCUMENT")

    # reverse helpers for walking the chain decision->thread->person->ticket->process->document
    def reverse(m: dict[str, set[str]]) -> dict[str, set[str]]:
        r: dict[str, set[str]] = defaultdict(set)
        for a, bs in m.items():
            for b in bs:
                r[b].add(a)
        return r

    thread_to_person = reverse(person_to_thread)
    person_to_ticket = reverse(ticket_to_person)

    decisions = [e["nick"] for e in entities if e["type"] == "decision"]
    found = 0
    for dec in decisions:
        for th in dec_to_thread.get(dec, set()):
            for p in thread_to_person.get(th, set()):
                for t in person_to_ticket.get(p, set()):
                    for pr in ticket_to_process.get(t, set()):
                        if process_to_doc.get(pr):
                            found += 1
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if found >= 5:
            break

    assert found >= 5

