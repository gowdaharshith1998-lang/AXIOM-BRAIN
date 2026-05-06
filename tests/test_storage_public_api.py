from __future__ import annotations

from pathlib import Path

import pytest

from axiom.schema.models import Base
from axiom.storage import (
    add_edge,
    create_entity,
    delete_entity,
    get_entity,
    init_engine,
    list_neighbors,
    query_entities,
    remove_edge,
    update_entity,
)


@pytest.fixture()
def storage_db(tmp_path: Path) -> None:
    db_path = tmp_path / "public_api.db"
    engine = init_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


def test_public_api_crud_roundtrip(storage_db: None) -> None:
    e = create_entity("people", {"name": "A"}, source_id=None)
    assert get_entity(e.id) is not None

    updated = update_entity(e.id, {"name": "A2"})
    assert updated.data["name"] == "A2"

    assert delete_entity(e.id) is True
    assert get_entity(e.id) is None


def test_public_api_edges_and_neighbors(storage_db: None) -> None:
    a = create_entity("people", {"name": "A"}, source_id=None)
    b = create_entity("ticket", {"name": "B"}, source_id=None)
    c = create_entity("thread", {"name": "C"}, source_id=None)

    e1 = add_edge(a.id, b.id, "ASSIGNED_TO", data={"at": 1})
    _ = add_edge(b.id, c.id, "LINKS_TO", data={})

    neigh_1 = list_neighbors(a.id, depth=1, direction="outgoing")
    assert {n.id for n in neigh_1} == {b.id}

    neigh_2 = list_neighbors(a.id, depth=2, direction="outgoing")
    assert {n.id for n in neigh_2} == {b.id, c.id}

    assert remove_edge(e1.id) is True


def test_public_api_query_entities(storage_db: None) -> None:
    for i in range(3):
        create_entity("document", {"i": i}, source_id=None)

    got = query_entities(type_="document", limit=10, offset=0)
    assert len(got) == 3

