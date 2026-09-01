"""Playback write paths and the cached dashboard snapshot.

Every mutation goes through :class:`StatsService` so that "data changed"
implies a snapshot-cache invalidation; callers cannot forget it. Read-only
callers use ``dashboard()`` and keep their cache keys opaque.
"""

import asyncio
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from weakref import WeakKeyDictionary

from src.config import env_int
from src.coverart import cover_art_service
from src.dashboard_cache import DashboardSnapshotCache, dashboard_snapshot_cache
from src.persistence import save_imported_events, save_play_attempt, save_play_session
from src.privacy_ops import (
    apply_retention_purge,
    delete_user_data,
    import_user_data,
)
from src.review_queries import get_review_summary
from src.runtime_state import runtime_state
from src.schema import LEGACY_SOURCE_ID
from src.server_registry import delete_server, list_server_options, save_server
from src.stats_query_entities import EntityIdentity
from src.stats_query_relations import RelationDimension
from src.stats_read_repository import StatsReadRepository, stats_read_repository
from src.stats_scope import StatsScope

logger = logging.getLogger(__name__)

SAVE_RETRY_ATTEMPTS = env_int("SAVE_RETRY_ATTEMPTS", default=3, min_value=1, max_value=10)


def exception_kind(exc: Exception) -> str:
    """Return a non-sensitive error category suitable for application logs."""
    return type(exc).__name__


def _is_sqlite_busy(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).lower() for marker in ("locked", "busy")
    )


async def retry_save(operation, *, kind: str, attempts: int):
    """Run ``operation`` with backoff; returns its result on success."""
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if _is_sqlite_busy(exc):
                runtime_state.record_sqlite_busy(retried=attempt < attempts)
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
playback_mutation_lock = LoopLocalLock()


class StatsService:
    """Owns every playback write path; cache invalidation happens inside."""

    def __init__(
        self,
        cache: DashboardSnapshotCache | None = None,
        retry_attempts: int | None = None,
        read_repository: StatsReadRepository | None = None,
    ):
        self._cache = cache or dashboard_snapshot_cache
        self._retry_attempts = retry_attempts or SAVE_RETRY_ATTEMPTS
        self._read_repository = read_repository or stats_read_repository
        self._discard_user_sessions: Callable[[str], set[str]] = lambda _username: set()
        self._suppressed_session_ids: OrderedDict[str, None] = OrderedDict()

    def set_session_discarder(
        self,
        discard_user_sessions: Callable[[str], set[str]],
    ) -> None:
        self._discard_user_sessions = discard_user_sessions

    def _suppress_sessions(self, session_ids: set[str]) -> None:
        for session_id in session_ids:
            self._suppressed_session_ids[session_id] = None
            self._suppressed_session_ids.move_to_end(session_id)
        while len(self._suppressed_session_ids) > 10_000:
            self._suppressed_session_ids.popitem(last=False)

    def _session_is_suppressed(self, payload: dict) -> bool:
        session_id = payload.get("session_id")
        return bool(session_id and str(session_id) in self._suppressed_session_ids)

    async def invalidate(self) -> None:
        await self._cache.invalidate()

    async def _invalidate_after_playback_write(self) -> None:
        try:
            await self._cache.invalidate()
        except Exception as exc:
            logger.error(
                "Dashboard cache invalidation failed after a successful playback write "
                "(type=%s)",
                exception_kind(exc),
            )

    async def record_session(self, session: dict) -> None:
        source_id = str(session.get("source_id") or "legacy")
        async with playback_mutation_lock():
            if self._session_is_suppressed(session):
                return
            try:
                await retry_save(
                    lambda: save_play_session(session),
                    kind="play_session",
                    attempts=self._retry_attempts,
                )
            except Exception:
                runtime_state.record_save_failure(source_id)
                raise
            runtime_state.record_save_success(source_id)
            await self._invalidate_after_playback_write()
            logger.debug("Recorded play session (duration=%ss)", session["duration_sec"])

    async def record_attempt(self, attempt: dict) -> None:
        source_id = str(attempt.get("source_id") or "legacy")
        async with playback_mutation_lock():
            if self._session_is_suppressed(attempt):
                return
            try:
                await retry_save(
                    lambda: save_play_attempt(attempt),
                    kind="play_attempt",
                    attempts=self._retry_attempts,
                )
            except Exception:
                runtime_state.record_save_failure(source_id)
                raise
            runtime_state.record_save_success(source_id)
            await self._invalidate_after_playback_write()

    async def record_imported_events(self, events: list[dict]) -> int:
        """Write importer events through the idempotent dedup path."""
        if not events:
            return 0
        started = time.perf_counter()
        source_id = str(events[0].get("source_id") or "legacy")
        try:
            async with playback_mutation_lock():
                try:
                    imported = await retry_save(
                        lambda: save_imported_events(events),
                        kind="imported_events",
                        attempts=self._retry_attempts,
                    )
                    runtime_state.record_save_success(source_id)
                except Exception:
                    runtime_state.record_save_failure(source_id)
                    raise
            if imported:
                await self._cache.invalidate()
            return imported
        finally:
            runtime_state.record_import(time.perf_counter() - started)

    async def purge_retention(self) -> dict:
        result = await apply_retention_purge()
        if result["deleted"]:
            await self._cache.invalidate()
        return result

    async def import_user(self, username: str, payload: dict, *, merge: bool) -> dict:
        started = time.perf_counter()
        try:
            result = await import_user_data(username, payload, merge=merge)
            if not merge or result["imported"] or result.get("attempts_imported", 0):
                await self._cache.invalidate()
            return result
        finally:
            runtime_state.record_import(time.perf_counter() - started)

    async def delete_user(self, username: str) -> dict:
        async with playback_mutation_lock():
            result = await delete_user_data(username)
            discarded = self._discard_user_sessions(username)
            self._suppress_sessions(discarded)
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

    async def dashboard(self, scope: StatsScope) -> dict:
        async def build() -> dict:
            started = time.perf_counter()
            try:
                return await self._build_snapshot(scope)
            finally:
                runtime_state.record_dashboard_build(time.perf_counter() - started)

        return await self._cache.get_or_create(("dashboard", scope), build)

    async def entity_detail(
        self,
        scope: StatsScope,
        identity: EntityIdentity,
    ) -> dict:
        """Return a cached artist, album, or client detail for one stats scope."""
        return await self._cache.get_or_create(
            ("entity_detail", scope, identity),
            lambda: self._read_repository.entity_detail(scope, identity),
        )

    async def data_relations(
        self,
        scope: StatsScope,
        dimension: RelationDimension,
    ) -> dict:
        """Return cached chart-ready relationships for one selected dimension."""
        return await self._cache.get_or_create(
            ("data_relations", scope, dimension),
            lambda: self._read_repository.data_relations(scope, dimension),
        )

    async def review(
        self,
        *,
        year: int,
        timezone_name: str,
        source_id: str | None = None,
        username: str | None = None,
    ):
        key = ("review", year, timezone_name, source_id, username)

        async def build() -> dict:
            summary = await get_review_summary(
                year,
                timezone_name,
                source_id=source_id,
                username=username,
            )
            servers = await list_server_options()
            summary["top_albums"] = await self._attach_album_ids(
                source_id, summary["top_albums"], servers
            )
            effective_source = self._resolve_effective_source(source_id, servers)
            for entry in summary["top_albums"]:
                if entry.get("source_id") in (None, LEGACY_SOURCE_ID):
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
        attached = []
        for entry in albums:
            if entry.get("album_id"):
                attached.append(entry)
                continue
            entry_source = entry.get("source_id") or effective_source
            if entry_source is None:
                attached.append({**entry, "album_id": None})
                continue
            try:
                album_id = await cover_art_service.resolve_album_id(
                    entry_source, entry.get("album"), entry.get("artist")
                )
            except Exception as exc:
                logger.warning(
                    "Album cover enrichment skipped (type=%s)",
                    exception_kind(exc),
                )
                attached.append({**entry, "album_id": None})
                continue
            attached.append({**entry, "album_id": album_id})
        return attached

    async def _build_snapshot(self, scope: StatsScope) -> dict:
        snapshot = await self._read_repository.dashboard(scope)
        summary = snapshot["summary"]
        time_buckets = snapshot["time_buckets"]
        available_servers = snapshot["available_servers"]
        top_albums = snapshot["top_albums"]
        top_albums = await self._attach_album_ids(
            scope.source_id,
            top_albums,
            available_servers,
        )
        return {
            "summary": summary,
            "players": snapshot["players"],
            "transcoding": snapshot["transcoding"],
            "hourly": time_buckets["hourly"],
            "daily": time_buckets["daily"],
            "heatmap": time_buckets["heatmap"],
            "history": snapshot["history"],
            "servers": snapshot["servers"],
            "available_servers": [
                {"id": server["id"], "display_name": server["display_name"]}
                for server in available_servers
            ],
            "top_artists": snapshot["top_artists"],
            "top_albums": top_albums,
        }


stats_service = StatsService()
