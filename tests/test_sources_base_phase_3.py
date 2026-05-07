from __future__ import annotations

from datetime import datetime

from axiom.sources.base import IngestEvent, SourceMetadata


def test_source_metadata_fields() -> None:
    m = SourceMetadata(
        source_id="src_x",
        source_type="synthetic",
        display_name="x",
        connected=True,
        last_sync_at=None,
        capabilities={"supports_watch": True},
    )
    assert m.source_id == "src_x"
    assert m.source_type == "synthetic"


def test_ingest_event_allows_entity_or_edge() -> None:
    e = IngestEvent(
        event_id="e1",
        event_type="entity_added",
        source_id="src_x",
        occurred_at=datetime.utcnow(),
        entity={"nick": "n", "type": "thread", "data": {}, "metadata": {}},
    )
    assert e.entity is not None

