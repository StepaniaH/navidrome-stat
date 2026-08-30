"""Process-local cache for immutable dashboard snapshots."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from src.runtime_state import runtime_state


class DashboardSnapshotCache:
    def __init__(self, ttl_sec: int = 60, max_entries: int = 64):
        self.ttl_sec = ttl_sec
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple, tuple[float, dict[str, Any]]] = OrderedDict()
        self._inflight: dict[
            tuple,
            tuple[asyncio.Task[dict[str, Any]], int],
        ] = {}
        self._generation = 0
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
                runtime_state.record_dashboard_cache_hit()
                return cached[1]
            self._entries.pop(key, None)
            inflight = self._inflight.get(key)
            if inflight is None:
                runtime_state.record_dashboard_cache_miss()
                generation = self._generation
                task = asyncio.create_task(factory())
                self._inflight[key] = (task, generation)
            else:
                runtime_state.record_dashboard_cache_shared()
                task, generation = inflight

        try:
            value = await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep the shared factory running if one waiter is cancelled.
            raise
        except Exception:
            async with self._lock:
                if self._inflight.get(key) == (task, generation):
                    self._inflight.pop(key, None)
            raise

        async with self._lock:
            if self._inflight.get(key) == (task, generation):
                self._inflight.pop(key, None)
            if generation == self._generation:
                self._entries[key] = (time.monotonic() + self.ttl_sec, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
        return value

    async def invalidate(self) -> None:
        async with self._lock:
            self._generation += 1
            self._entries.clear()
            self._inflight.clear()


dashboard_snapshot_cache = DashboardSnapshotCache()
