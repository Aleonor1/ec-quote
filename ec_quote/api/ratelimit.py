"""Limite de ritm in memorie (fereastra glisanta) si lacat pe conversatie.

Starea traieste in proces: serviciul ruleaza cu un singur worker.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Hashable
from contextlib import asynccontextmanager


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[Hashable, deque[float]] = {}
        self._calls = 0

    def hit(self, key: Hashable) -> float | None:
        """None daca cererea trece; altfel secundele pana la urmatoarea incercare."""
        now = self._clock()
        self._calls += 1
        if self._calls % 500 == 0:
            self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(hits[0] + self.window - now, 0.0)
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]
        for key in stale:
            del self._hits[key]


class KeyedLocks:
    """Un asyncio.Lock pe cheie; cererile aceleiasi conversatii trec pe rand, in ordinea sosirii."""

    def __init__(self) -> None:
        self._locks: dict[Hashable, list] = {}

    @asynccontextmanager
    async def hold(self, key: Hashable):
        entry = self._locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._locks.pop(key, None)
