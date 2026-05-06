from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from axiom.schema.dto import EntityDTO
from axiom.storage import crud

ENTITY_TYPES = ["code", "people", "decision", "thread", "ticket", "document", "process"]


@pytest.mark.parametrize("type_", ENTITY_TYPES)
def test_entity_crud_roundtrip_all_types(db_session: Session, type_: str) -> None:
    payload: dict[str, Any] = {
        "required": {"type": type_},
        "metadata": {
            "calibra_state": "UNKNOWN",
            "calibra_confidence": 0.0,
            "nested": {"unicode": "Δελτα", "list": [1, "two", {"three": 3}]},
        },
    }

    created = crud.create_entity(db_session, type_, payload, source_id=None)
    assert isinstance(created, EntityDTO)
    assert created.id
    assert len(created.id) == 32
    assert created.type == type_
    assert created.data == payload

    fetched = crud.get_entity(db_session, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.type == created.type
    assert fetched.data == created.data

    updated_payload = {"v": 2, "metadata": {"calibra_state": "KNOW", "calibra_confidence": 1.0}}
    updated = crud.update_entity(db_session, created.id, updated_payload)
    assert updated.id == created.id
    assert updated.data == updated_payload
    assert updated.updated_at >= updated.created_at

    assert crud.delete_entity(db_session, created.id) is True
    assert crud.get_entity(db_session, created.id) is None


def test_query_entities_limit_offset_and_where(db_session: Session) -> None:
    for i in range(5):
        crud.create_entity(db_session, "ticket", {"i": i}, source_id=None)

    first_two = crud.query_entities(db_session, type_="ticket", limit=2, offset=0)
    next_two = crud.query_entities(db_session, type_="ticket", limit=2, offset=2)
    assert len(first_two) == 2
    assert len(next_two) == 2
    assert {e.id for e in first_two}.isdisjoint({e.id for e in next_two})

    one = crud.query_entities(db_session, where={"type": "ticket"}, limit=1, offset=0)
    assert len(one) == 1
    assert one[0].type == "ticket"

    with pytest.raises(ValueError):
        crud.query_entities(db_session, where={"unsupported": "x"})

