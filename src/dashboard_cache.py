"""Small process-local cache for immutable dashboard snapshot payloads."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any


class DashboardSnapshotCache:
    def __init__(self, ttl_sec: int = 60, max_entries: int = 64):
        self.ttl_sec = ttl_sec
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        key: tuple,
        factory: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        async with self._lock:
            cached = self._entries.get(key)
            now = time.monotonic()
            if cached is not None and cached[0] > now:
                self._entries.move_to_end(key)
                return cached[1]
            self._entries.pop(key, None)

            value = await factory()
            self._entries[key] = (now + self.ttl_sec, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return value

    async def invalidate(self) -> None:
        async with self._lock:
            self._entries.clear()


dashboard_snapshot_cache = DashboardSnapshotCache()
