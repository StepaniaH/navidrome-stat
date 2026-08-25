"""Playback write paths and the cached dashboard snapshot.

Every mutation goes through :class:`StatsService` so that "data changed"
implies a snapshot-cache invalidation; callers cannot forget it. Read-only
callers use ``dashboard()`` and keep their cache keys opaque.
"""

import asyncio
import logging
import threading
from datetime import date
from weakref import WeakKeyDictionary

from src.config import env_int
from src.coverart import cover_art_service
from src.dashboard_cache import DashboardSnapshotCache, dashboard_snapshot_cache
from src.database import (
    delete_server,
    get_playback_history,
    get_player_stats,
    get_review_summary,
    get_server_stats,
    get_summary,
    get_time_bucket_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    list_servers,
    save_play_attempt,
    save_play_session,
    save_server,
)
from src.privacy_ops import (
    apply_retention_purge,
    delete_user_data,
    import_user_data,
)
from src.runtime_state import runtime_state
from src.schemas import HISTORY_LIMIT_DEFAULT, TOP_LIMIT_DEFAULT

logger = logging.getLogger(__name__)

SAVE_RETRY_ATTEMPTS = env_int(
    "SAVE_RETRY_ATTEMPTS", default=3, min_value=1, max_value=10
)


def exception_kind(exc: Exception) -> str:
    """Return a non-sensitive error category suitable for application logs."""
    return type(exc).__name__


async def retry_save(operation, *, kind: str, attempts: int) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await operation()
            return
        except Exception as exc:
            if attempt >= attempts:
                logger.error(
                    "%s persistence failed (type=%s, attempts=%s)",
                    kind,
                    exception_kind(exc),
                    attempt,
                )
                raise
            logger.warning(
                "%s persistence retry (type=%s, attempt=%s)",
                kind,
                exception_kind(exc),
                attempt,
            )
            await asyncio.sleep(0.05 * (2 ** (attempt - 1)))


class LoopLocalLock:
    """Provide one asyncio lock per event loop."""

    def __init__(self) -> None:
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            WeakKeyDictionary()
        )
        self._guard = threading.Lock()

    def __call__(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._guard:
            lock = self._locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[loop] = lock
            return lock


retention_policy_lock = LoopLocalLock()
server_mutation_lock = LoopLocalLock()


class StatsService:
    """Owns every playback write path; cache invalidation happens inside."""

    def __init__(
        self,
        cache: DashboardSnapshotCache | None = None,
        retry_attempts: int | None = None,
    ):
        self._cache = cache or dashboard_snapshot_cache
        self._retry_attempts = retry_attempts or SAVE_RETRY_ATTEMPTS

    async def invalidate(self) -> None:
        await self._cache.invalidate()

    async def record_session(self, session: dict) -> None:
        try:
            await retry_save(
                lambda: save_play_session(session),
                kind="play_session",
                attempts=self._retry_attempts,
            )
            runtime_state.record_save_success()
            await self._cache.invalidate()
            logger.debug("Recorded play session (duration=%ss)", session["duration_sec"])
        except Exception:
            runtime_state.record_save_failure()
            raise

    async def record_attempt(self, attempt: dict) -> None:
        await retry_save(
            lambda: save_play_attempt(attempt),
            kind="play_attempt",
            attempts=self._retry_attempts,
        )
        await self._cache.invalidate()

    async def purge_retention(self) -> dict:
        result = await apply_retention_purge()
        if result["deleted"]:
            await self._cache.invalidate()
        return result

    async def import_user(self, username: str, payload: dict, *, merge: bool) -> dict:
        result = await import_user_data(username, payload, merge=merge)
        if not merge or result["imported"] or result.get("attempts_imported", 0):
            await self._cache.invalidate()
        return result

    async def delete_user(self, username: str) -> dict:
        result = await delete_user_data(username)
        if result["deleted"]:
            await self._cache.invalidate()
        return result

    async def create_server(self, server: dict) -> None:
        await save_server(server)
        await self._cache.invalidate()

    async def update_server(self, server: dict) -> None:
        await save_server(server)
        await self._cache.invalidate()

    async def remove_server(self, server_id: str) -> bool:
        deleted = await delete_server(server_id)
        if not deleted:
            return False
        await self._cache.invalidate()
        return True

    async def dashboard(
        self,
        *,
        days: int,
        timezone_name: str,
        metric: str,
        source_id: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        key = (days, timezone_name, metric, source_id, start_date, end_date)

        async def build() -> dict:
            return await self._build_snapshot(
                days=days,
                timezone_name=timezone_name,
                metric=metric,
                source_id=source_id,
                start_date=start_date,
                end_date=end_date,
            )

        return await self._cache.get_or_create(key, build)

    async def review(self, *, year: int, timezone_name: str, source_id: str | None = None):
        key = ("review", year, timezone_name, source_id)

        async def build() -> dict:
            summary = await get_review_summary(
                year, timezone_name, source_id=source_id
            )
            servers = await list_servers()
            summary["top_albums"] = await self._attach_album_ids(
                source_id, summary["top_albums"], servers
            )
            effective_source = self._resolve_effective_source(source_id, servers)
            for entry in summary["top_albums"]:
                entry["source_id"] = effective_source
            return summary

        return await self._cache.get_or_create(key, build)

    @staticmethod
    def _resolve_effective_source(source_id: str | None, available_servers: list) -> str | None:
        if source_id:
            return source_id
        if len(available_servers) == 1:
            return available_servers[0].get("id")
        return None

    async def _attach_album_ids(
        self,
        source_id: str | None,
        albums: list,
        available_servers: list,
    ) -> list:
        if not albums:
            return albums
        effective_source = self._resolve_effective_source(source_id, available_servers)
        if effective_source is None:
            return [{**entry, "album_id": None} for entry in albums]
        attached = []
        for entry in albums:
            album_id = await cover_art_service.resolve_album_id(
                effective_source, entry.get("album"), None
            )
            attached.append({**entry, "album_id": album_id})
        return attached

    async def _build_snapshot(
        self,
        *,
        days: int,
        timezone_name: str,
        metric: str,
        source_id: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> dict:
        window_kwargs = {"start_date": start_date, "end_date": end_date}
        (
            summary,
            players,
            transcoding,
            time_buckets,
            history,
            servers,
            available_servers,
            top_artists,
            top_albums,
        ) = await asyncio.gather(
            get_summary(
                days=days,
                timezone_name=timezone_name,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_player_stats(
                days=days,
                timezone_name=timezone_name,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_transcoding_stats(
                days=days,
                timezone_name=timezone_name,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_time_bucket_stats(
                days=days,
                timezone_name=timezone_name,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_playback_history(
                limit=HISTORY_LIMIT_DEFAULT,
                days=days,
                timezone_name=timezone_name,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_server_stats(
                days=days,
                timezone_name=timezone_name,
                source_id=source_id,
                **window_kwargs,
            ),
            list_servers(),
            get_top_artists(
                limit=TOP_LIMIT_DEFAULT,
                days=days,
                timezone_name=timezone_name,
                metric=metric,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
            get_top_albums(
                limit=TOP_LIMIT_DEFAULT,
                days=days,
                timezone_name=timezone_name,
                metric=metric,
                **({"source_id": source_id} if source_id else {}),
                **window_kwargs,
            ),
        )
        top_albums = await self._attach_album_ids(source_id, top_albums, available_servers)
        return {
            "summary": summary,
            "players": players,
            "transcoding": transcoding,
            "hourly": time_buckets["hourly"],
            "daily": time_buckets["daily"],
            "heatmap": time_buckets["heatmap"],
            "history": history,
            "servers": servers,
            "available_servers": [
                {"id": server["id"], "display_name": server["display_name"]}
                for server in available_servers
            ],
            "top_artists": top_artists,
            "top_albums": top_albums,
        }


stats_service = StatsService()
