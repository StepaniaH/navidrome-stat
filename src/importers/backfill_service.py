"""Backfill orchestration shared by the watch loop and the manual trigger.

One run per source at a time (per-source asyncio lock); each run resolves the
importer cutoff from live-poller coverage, converts smart-playlist tracks
into estimated listen events, and writes them through StatsService so the
dashboard cache invalidates only when new rows landed.
"""

import asyncio
import logging
import threading

from src.config import env_int
from src.importers.playlist_backfill import run_backfill

logger = logging.getLogger(__name__)

BACKFILL_INTERVAL_SEC = env_int(
    "BACKFILL_INTERVAL_SEC", default=3600, min_value=300, max_value=86400
)


def _record_result(state, source_id: str, result: dict) -> None:
    state.record_backfill_result(source_id, result.get("imported", 0))


async def watch_forever(runner, server: dict, client) -> None:
    """Run a backfill immediately, then once per interval until cancelled."""
    while True:
        try:
            await runner.run_once(server, client=client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Backfill watch cycle failed (source=%s, type=%s)",
                server.get("id"),
                type(exc).__name__,
            )
        await asyncio.sleep(BACKFILL_INTERVAL_SEC)


class BackfillRunner:
    """Serializes importer runs per source and accounts outcomes."""

    def __init__(self, *, stats=None, state=None, client_factory, earliest_lookup=None):
        import src.stats_service as stats_module
        from src.runtime_state import runtime_state as default_state

        self._stats = stats or stats_module.stats_service
        self._state = state or default_state
        self._client_factory = client_factory
        self._earliest_lookup = earliest_lookup or self._default_earliest
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_guard = threading.Lock()

    @staticmethod
    async def _default_earliest(source_id: str, username: str):
        from src.database import get_earliest_poller_played_at

        return await get_earliest_poller_played_at(source_id, username)

    def _lock_for(self, source_id: str) -> asyncio.Lock:
        with self._lock_guard:
            lock = self._locks.get(source_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[source_id] = lock
            return lock

    async def run_once(self, server: dict, client=None) -> dict | None:
        playlist_id = server.get("backfill_playlist_id")
        if not playlist_id:
            return None

        source_id = server["id"]
        username = server.get("username") or ""
        owned_client = client is None
        if client is None:
            client = self._client_factory(
                url=server.get("url"),
                user=username,
                password=server.get("password"),
            )

        try:
            async with self._lock_for(source_id):
                earliest = await self._earliest_lookup(source_id, username)
                try:
                    result = await run_backfill(
                        client,
                        playlist_id=playlist_id,
                        record=self._stats.record_imported_events,
                        source_id=source_id,
                        source_name=server.get("display_name", ""),
                        username=username,
                        earliest_poller_played_at=earliest,
                    )
                except Exception:
                    self._state.record_backfill_error(source_id)
                    raise
                _record_result(self._state, source_id, result)
                return result
        finally:
            if owned_client and client is not None:
                await client.close()
