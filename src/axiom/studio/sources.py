from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.schema.models import Entity


@dataclass(frozen=True)
class SourceSnapshot:
    name: str
    count: int
    last_event_at: str
    live: bool


SOURCE_BASELINES: tuple[tuple[str, int, str], ...] = (
    ("Slack", 1247, "live"),
    ("Linear", 312, "2m ago"),
    ("GitHub", 89, "5m ago"),
    ("Notion", 156, "1h ago"),
    ("Email", 2890, "live"),
    ("Meetings", 47, "3h ago"),
)


def synthetic_sources_snapshot(session: Session) -> list[dict[str, object]]:
    entity_count = session.execute(select(Entity.id)).all()
    increment = len(entity_count)
    now = datetime.utcnow()
    rows: list[dict[str, object]] = []
    for index, (name, baseline, freshness) in enumerate(SOURCE_BASELINES):
        live = freshness == "live"
        last_event = now if live else now - timedelta(minutes=(index + 1) * 2)
        rows.append(
            {
                "name": name,
                "count": baseline + increment * (index + 1),
                "last_event_at": last_event.isoformat(),
                "freshness": freshness,
                "live": live,
            }
        )
    return rows
