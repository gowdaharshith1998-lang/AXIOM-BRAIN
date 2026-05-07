from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from axiom.sources.event_generators import ENTITY_TYPES, LiveEventGenerator
from axiom.sources.live_synthetic import LiveSyntheticSource


def test_poisson_interarrival_mean_within_five_percent() -> None:
    rate = 0.25
    source = LiveSyntheticSource(rate_per_second=rate)

    samples = [source.sample_interarrival() for _ in range(500)]
    mean = sum(samples) / len(samples)

    assert abs(mean - (1 / rate)) / (1 / rate) <= 0.05


def test_event_mix_ratios_match_targets_over_500_events() -> None:
    source = LiveSyntheticSource()

    counts = Counter(source.next_event().raw["live_kind"] for _ in range(500))

    assert counts["ticket"] == 250
    assert counts["thread"] == 100
    assert counts["edge"] == 75
    assert counts["decision"] == 50
    assert counts["document"] == 25


def test_determinism_with_seed_42() -> None:
    left = LiveSyntheticSource(rng_seed=42)
    right = LiveSyntheticSource(rng_seed=42)

    left_events = [left.next_event() for _ in range(40)]
    right_events = [right.next_event() for _ in range(40)]

    assert left_events == right_events


@pytest.mark.asyncio
async def test_cancellation_stops_watch_promptly(monkeypatch: pytest.MonkeyPatch) -> None:
    source = LiveSyntheticSource(rate_per_second=1.0)
    monkeypatch.setattr(source, "sample_interarrival", lambda: 60.0)
    called = False

    def on_event(_event: object) -> None:
        nonlocal called
        called = True

    async with source.watch(on_event):
        source.cancel()
        await asyncio.sleep(0)

    assert called is False
    assert source.events_emitted == 0


@pytest.mark.asyncio
async def test_max_events_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    source = LiveSyntheticSource(rate_per_second=1000.0, max_events=5)
    monkeypatch.setattr(source, "sample_interarrival", lambda: 0.0)
    events = []

    async def on_event(event: object) -> None:
        events.append(event)

    async with source.watch(on_event):  # type: ignore[arg-type]
        while source.task is not None and not source.task.done():
            await asyncio.sleep(0)

    assert len(events) == 5
    assert source.events_emitted == 5


def test_all_emitted_entities_have_calibra_placeholders() -> None:
    source = LiveSyntheticSource()
    entities = [
        event.entity
        for event in (source.next_event() for _ in range(100))
        if event.entity is not None
    ]

    assert entities
    assert all(entity["metadata"]["calibra_state"] is None for entity in entities)
    assert all(entity["metadata"]["calibra_confidence"] is None for entity in entities)


def test_all_emitted_entities_have_non_empty_nicks() -> None:
    source = LiveSyntheticSource()
    entities = [
        event.entity
        for event in (source.next_event() for _ in range(100))
        if event.entity is not None
    ]

    assert all(isinstance(entity["nick"], str) and entity["nick"] for entity in entities)


def test_edge_events_reference_existing_nicks() -> None:
    source = LiveSyntheticSource()
    edge_events = [event for event in (source.next_event() for _ in range(100)) if event.edge]

    assert edge_events
    for event in edge_events:
        assert event.edge is not None
        assert event.edge["source_nick"] in source.state.all_nicks
        assert event.edge["target_nick"] in source.state.all_nicks


def test_ticket_titles_are_plausible_and_short() -> None:
    source = LiveSyntheticSource()
    titles = [
        event.entity["data"]["title"]
        for event in (source.next_event() for _ in range(100))
        if event.entity is not None and event.entity["type"] == "ticket"
    ]

    assert titles
    assert all(0 < len(title) <= 120 for title in titles)
    assert any("webhook" in title.lower() or "refund" in title.lower() for title in titles)


def test_all_seven_entity_types_are_emittable() -> None:
    source = LiveSyntheticSource()
    generator = LiveEventGenerator(rng=source.rng, state=source.state)

    emitted = {generator.generate_entity(entity_type)["type"] for entity_type in ENTITY_TYPES}

    assert emitted == set(ENTITY_TYPES)


def test_live_source_discover_and_metadata() -> None:
    source = LiveSyntheticSource(rate_per_second=0.5, max_events=2)

    assert source.metadata()["rate_per_second"] == 0.5
    assert source.metadata()["events_emitted"] == 0
