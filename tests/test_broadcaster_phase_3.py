from __future__ import annotations

import asyncio

import pytest

from axiom.ingest.broadcaster import EventBroadcaster


@pytest.mark.asyncio
async def test_publish_seq_monotonic() -> None:
    b = EventBroadcaster()
    s1 = await b.publish({"type": "x"})
    s2 = await b.publish({"type": "y"})
    assert s2 == s1 + 1
    assert b.current_seq == s2


@pytest.mark.asyncio
async def test_subscribe_replays_since() -> None:
    b = EventBroadcaster()
    for i in range(10):
        await b.publish({"type": "t", "i": i})

    got = []
    async for env in b.subscribe(since=5):
        got.append(env["seq"])
        if len(got) == 4:
            break

    assert got == [6, 7, 8, 9]


@pytest.mark.asyncio
async def test_buffer_caps_at_1000() -> None:
    b = EventBroadcaster()
    for i in range(1500):
        await b.publish({"i": i})

    got = []
    async for env in b.subscribe(since=0):
        got.append(env["seq"])
        if len(got) == 5:
            break

    assert got[0] == 501
    assert b.current_seq == 1500


@pytest.mark.asyncio
async def test_slow_subscriber_dropped() -> None:
    b = EventBroadcaster()
    # Publish at least one event, then create a subscriber and barely consume.
    await b.publish({"boot": True})
    it = b.subscribe(since=0)
    agen = it.__aiter__()
    first = await agen.__anext__()
    assert first["seq"] == 1

    # Flood publishes; subscriber queue should fill and be dropped.
    for _ in range(5000):
        await b.publish({"spam": True})

    # New subscriber should still work.
    got = []
    async for env in b.subscribe(since=b.current_seq - 3):
        got.append(env["seq"])
        if len(got) == 3:
            break
    assert len(got) == 3


@pytest.mark.asyncio
async def test_concurrent_publishers_and_subscriber() -> None:
    b = EventBroadcaster()

    async def pub(n: int) -> None:
        for i in range(n):
            await b.publish({"i": i})

    async def sub() -> int:
        seen = 0
        async for _ in b.subscribe(since=0):
            seen += 1
            if seen >= 200:
                return seen
        return seen

    seen = await asyncio.gather(pub(200), sub())
    assert seen[1] == 200


@pytest.mark.asyncio
async def test_subscribe_live_events_after_replay() -> None:
    b = EventBroadcaster()
    await b.publish({"kind": "replay"})

    it = b.subscribe(since=0)
    agen = it.__aiter__()
    first = await agen.__anext__()
    assert first["seq"] == 1

    # Ensure the subscription has transitioned to live mode before publishing.
    import asyncio

    pending_next = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0)
    await b.publish({"kind": "live"})
    second = await pending_next
    assert second["seq"] == 2
