from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.schema.dto import EdgeDTO, EntityDTO
from axiom.schema.models import Edge, Entity


def create_entity(
    session: Session,
    type_: str,
    data: dict[str, Any],
    *,
    source_id: str | None = None,
    cluster_id: str | None = None,
) -> EntityDTO:
    entity = Entity(type=type_, data=data, source_id=source_id, cluster_id=cluster_id)
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return EntityDTO.model_validate(entity)


def get_entity(session: Session, entity_id: str) -> EntityDTO | None:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return None
    return EntityDTO.model_validate(entity)


def update_entity(session: Session, entity_id: str, data: dict[str, Any]) -> EntityDTO:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise KeyError(f"entity not found: {entity_id}")
    entity.data = data
    entity.updated_at = datetime.utcnow()
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return EntityDTO.model_validate(entity)


def delete_entity(session: Session, entity_id: str) -> bool:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return False
    session.delete(entity)
    session.commit()
    return True


def query_entities(
    session: Session,
    *,
    type_: str | None = None,
    where: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[EntityDTO]:
    stmt = select(Entity)
    if type_ is not None:
        stmt = stmt.where(Entity.type == type_)

    if where:
        for key, value in where.items():
            if key == "id":
                stmt = stmt.where(Entity.id == value)
            elif key == "type":
                stmt = stmt.where(Entity.type == value)
            elif key == "source_id":
                stmt = stmt.where(Entity.source_id == value)
            else:
                raise ValueError(f"unsupported where key (Phase 2): {key}")

    stmt = stmt.offset(offset).limit(limit)
    rows = session.execute(stmt).scalars().all()
    return [EntityDTO.model_validate(r) for r in rows]


Direction = Literal["outgoing", "incoming", "both"]


def list_neighbors(
    session: Session,
    entity_id: str,
    *,
    edge_type: str | None = None,
    depth: int = 1,
    direction: Direction = "both",
) -> list[EntityDTO]:
    if depth not in (1, 2):
        raise ValueError("depth must be 1 or 2 in Phase 2")

    visited: set[str] = {entity_id}
    results: list[EntityDTO] = []

    q: deque[tuple[str, int]] = deque([(entity_id, 0)])
    while q:
        current_id, current_depth = q.popleft()
        if current_depth == depth:
            continue

        edges_stmt = select(Edge)
        if edge_type is not None:
            edges_stmt = edges_stmt.where(Edge.relationship == edge_type)

        if direction in ("outgoing", "both"):
            out_stmt = edges_stmt.where(Edge.source_id == current_id)
            for e in session.execute(out_stmt).scalars().all():
                if e.target_id not in visited:
                    visited.add(e.target_id)
                    ent = session.get(Entity, e.target_id)
                    if ent is not None:
                        dto = EntityDTO.model_validate(ent)
                        results.append(dto)
                        q.append((e.target_id, current_depth + 1))

        if direction in ("incoming", "both"):
            in_stmt = edges_stmt.where(Edge.target_id == current_id)
            for e in session.execute(in_stmt).scalars().all():
                if e.source_id not in visited:
                    visited.add(e.source_id)
                    ent = session.get(Entity, e.source_id)
                    if ent is not None:
                        dto = EntityDTO.model_validate(ent)
                        results.append(dto)
                        q.append((e.source_id, current_depth + 1))

    return results


def add_edge(
    session: Session,
    source_id: str,
    target_id: str,
    type_: str,
    data: dict[str, Any] | None = None,
) -> EdgeDTO:
    edge = Edge(source_id=source_id, target_id=target_id, relationship=type_, data=data or {})
    session.add(edge)
    session.commit()
    session.refresh(edge)
    return EdgeDTO.model_validate(edge)


def remove_edge(session: Session, edge_id: str) -> bool:
    edge = session.get(Edge, edge_id)
    if edge is None:
        return False
    session.delete(edge)
    session.commit()
    return True
