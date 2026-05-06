from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any


class EventBroadcaster:
    """In-process pub/sub for ingest events with sequence numbering + replay.

    Contract (founder ruling Q2): last 1000 events in-memory. Clients reconnect
    with ?since=<seq> and receive replay from that sequence number forward.
    """

    BUFFER_CAPACITY = 1000

    def __init__(self) -> None:
        self._seq = 0
        self._buffer: deque[tuple[int, dict[str, Any]]] = deque(maxlen=self.BUFFER_CAPACITY)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, envelope: dict[str, Any]) -> int:
        async with self._lock:
            self._seq += 1
            seq = self._seq
            env = dict(envelope)
            env["seq"] = seq

            self._buffer.append((seq, env))

            for q in list(self._subscribers):
                try:
                    q.put_nowait(env)
                except asyncio.QueueFull:
                    self._subscribers.discard(q)

            return seq

    async def subscribe(self, *, since: int = 0) -> AsyncIterator[dict[str, Any]]:
        for seq, env in list(self._buffer):
            if seq > since:
                yield env

        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2000)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    @property
    def current_seq(self) -> int:
        return self._seq

