from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from axiom.schema.dto import EdgeDTO, EntityDTO
from axiom.storage import crud
from axiom.storage.db import build_engine, get_session, init_engine

Direction = Literal["outgoing", "incoming", "both"]


def create_entity(type_: str, data: dict[str, Any], *, source_id: str | None = None) -> EntityDTO:
    session = get_session()
    try:
        return crud.create_entity(session, type_, data, source_id=source_id)
    finally:
        session.close()


def get_entity(entity_id: str) -> EntityDTO | None:
    session = get_session()
    try:
        return crud.get_entity(session, entity_id)
    finally:
        session.close()


def update_entity(entity_id: str, data: dict[str, Any]) -> EntityDTO:
    session = get_session()
    try:
        return crud.update_entity(session, entity_id, data)
    finally:
        session.close()


def delete_entity(entity_id: str) -> bool:
    session = get_session()
    try:
        return crud.delete_entity(session, entity_id)
    finally:
        session.close()


def query_entities(
    *,
    type_: str | None = None,
    where: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[EntityDTO]:
    session = get_session()
    try:
        return crud.query_entities(session, type_=type_, where=where, limit=limit, offset=offset)
    finally:
        session.close()


def list_neighbors(
    entity_id: str,
    *,
    edge_type: str | None = None,
    depth: int = 1,
    direction: Direction = "both",
) -> list[EntityDTO]:
    session = get_session()
    try:
        return crud.list_neighbors(
            session,
            entity_id,
            edge_type=edge_type,
            depth=depth,
            direction=direction,
        )
    finally:
        session.close()


def add_edge(
    source_id: str,
    target_id: str,
    type_: str,
    data: dict[str, Any] | None = None,
) -> EdgeDTO:
    session = get_session()
    try:
        return crud.add_edge(session, source_id, target_id, type_, data)
    finally:
        session.close()


def remove_edge(edge_id: str) -> bool:
    session = get_session()
    try:
        return crud.remove_edge(session, edge_id)
    finally:
        session.close()


__all__ = [
    "Direction",
    "Session",
    "add_edge",
    "build_engine",
    "create_entity",
    "crud",
    "delete_entity",
    "get_entity",
    "init_engine",
    "list_neighbors",
    "query_entities",
    "remove_edge",
    "update_entity",
]
