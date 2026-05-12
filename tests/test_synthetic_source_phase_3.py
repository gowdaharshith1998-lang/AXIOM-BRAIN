from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from axiom.sources.synthetic import SyntheticSource


@pytest.mark.asyncio
async def test_synthetic_source_discover() -> None:
    s = SyntheticSource()
    meta = await s.discover()
    assert meta.source_id == "synthetic-default"
    assert meta.source_type == "synthetic"
    assert meta.connected is True
    assert "supports_watch" in meta.capabilities


@pytest.mark.asyncio
async def test_synthetic_source_ingest_yields_entities_then_edges() -> None:
    s = SyntheticSource()
    events = [e async for e in s.ingest()]
    assert len(events) >= 250
    assert all(e.source_id == "synthetic-default" for e in events)
    assert all(isinstance(e.occurred_at, datetime) for e in events)

    # all entity events before the first edge event
    first_edge_idx = next(i for i, e in enumerate(events) if e.event_type == "edge_added")
    assert all(e.event_type == "entity_added" for e in events[:first_edge_idx])
    assert all(e.event_type == "edge_added" for e in events[first_edge_idx:])

    assert all(e.entity is not None for e in events[:first_edge_idx])
    assert all(e.edge is not None for e in events[first_edge_idx:])


@pytest.mark.asyncio
async def test_synthetic_watch_is_noop() -> None:
    s = SyntheticSource()
    called = False

    def on_event(_e) -> None:  # type: ignore[no-untyped-def]
        nonlocal called
        called = True

    async with s.watch(on_event):
        await asyncio.sleep(0)

    assert called is False


@pytest.mark.asyncio
async def test_synthetic_disconnect_clears_cache() -> None:
    # ensure it loaded data
    s = SyntheticSource()
    _ = [e async for e in s.ingest()]
    assert s._data is not None  # noqa: SLF001 (test)

    await s.disconnect()
    assert s._data is None  # noqa: SLF001 (test)
