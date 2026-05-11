from __future__ import annotations

from sqlalchemy.orm import Session

from axiom.schema.models import Entity, Source

SYNTHETIC_SOURCE_ID = "synthetic-default"


def is_demo_target(session: Session, entity_id: str | None) -> bool:
    if not entity_id:
        return True

    entity = session.get(Entity, entity_id)
    if entity is None or entity.source_id is None:
        return True
    if entity.source_id == SYNTHETIC_SOURCE_ID:
        return True

    source = session.get(Source, entity.source_id)
    if source is None:
        return True
    return source.source_type == "synthetic"
