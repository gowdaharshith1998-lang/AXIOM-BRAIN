from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from axiom.storage import crud


def test_neighbors_depth_1_directional(db_session: Session) -> None:
    a = crud.create_entity(db_session, "people", {"name": "A"}, source_id=None)
    b = crud.create_entity(db_session, "ticket", {"name": "B"}, source_id=None)
    c = crud.create_entity(db_session, "thread", {"name": "C"}, source_id=None)

    crud.add_edge(db_session, a.id, b.id, "ASSIGNED_TO", data=None)
    crud.add_edge(db_session, c.id, a.id, "MENTIONS", data=None)

    out = crud.list_neighbors(db_session, a.id, depth=1, direction="outgoing")
    inc = crud.list_neighbors(db_session, a.id, depth=1, direction="incoming")
    both = crud.list_neighbors(db_session, a.id, depth=1, direction="both")

    assert {e.id for e in out} == {b.id}
    assert {e.id for e in inc} == {c.id}
    assert {e.id for e in both} == {b.id, c.id}


def test_neighbors_depth_2_cycle_protection(db_session: Session) -> None:
    a = crud.create_entity(db_session, "decision", {"name": "A"}, source_id=None)
    b = crud.create_entity(db_session, "document", {"name": "B"}, source_id=None)
    c = crud.create_entity(db_session, "process", {"name": "C"}, source_id=None)

    crud.add_edge(db_session, a.id, b.id, "REL", data=None)
    crud.add_edge(db_session, b.id, a.id, "REL", data=None)  # cycle back
    crud.add_edge(db_session, b.id, c.id, "REL", data=None)

    neighbors = crud.list_neighbors(db_session, a.id, depth=2, direction="outgoing")
    ids = {e.id for e in neighbors}
    assert a.id not in ids
    assert b.id in ids
    assert c.id in ids


def test_neighbors_edge_type_filter(db_session: Session) -> None:
    a = crud.create_entity(db_session, "people", {"name": "A"}, source_id=None)
    b = crud.create_entity(db_session, "people", {"name": "B"}, source_id=None)
    c = crud.create_entity(db_session, "people", {"name": "C"}, source_id=None)

    crud.add_edge(db_session, a.id, b.id, "TYPE_1", data=None)
    crud.add_edge(db_session, a.id, c.id, "TYPE_2", data=None)

    only_1 = crud.list_neighbors(
        db_session,
        a.id,
        depth=1,
        direction="outgoing",
        edge_type="TYPE_1",
    )
    assert {e.id for e in only_1} == {b.id}


def test_neighbors_depth_validation(db_session: Session) -> None:
    a = crud.create_entity(db_session, "people", {"name": "A"}, source_id=None)
    with pytest.raises(ValueError):
        crud.list_neighbors(db_session, a.id, depth=3)

