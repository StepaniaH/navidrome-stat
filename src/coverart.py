"""Cover art lookup with a disk cache and search3 album resolution.

Binary cover art is fetched from the owning Navidrome server once, stored
under a content-addressed cache directory, and served from disk afterwards.
Legacy album entries in statistics may only carry names, so ``resolve_album_id``
maps an album name to a Navidrome album ID via ``search3`` and remembers both
hits and (time-boxed) misses in the ``album_art_map`` table.
"""

import asyncio
import hashlib
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import config
from src.client import DEFAULT_COVER_ART_MAX_BYTES, NavidromeClient
from src.config import env_int
from src.runtime_state import runtime_state
from src.source_config import credentials_for_source
from src.sqlite import connect_db
from src.windows import utc_instant

NEGATIVE_TTL = timedelta(hours=24)
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = env_int(
    "COVER_ART_RESPONSE_MAX_BYTES",
    default=DEFAULT_COVER_ART_MAX_BYTES,
    min_value=64 * 1024,
    max_value=64 * 1024 * 1024,
)

_MAGIC_TYPES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
def album_key(album: str | None, artist: str | None) -> str:
    return (
        (album or "").strip().casefold()
        + "\x1f"
        + (artist or "").strip().casefold()
    )


def _detect_type(data: bytes) -> str | None:
    for magic, content_type in _MAGIC_TYPES:
        if data.startswith(magic):
            return content_type
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {
        b"avif",
        b"avis",
    }:
        return "image/avif"
    return None


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class CoverArtService:
    """Fetches, caches, and resolves cover art for one Navidrome source."""

    def __init__(
        self,
        *,
        cache_dir: Path | str | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        client_factory=None,
        now=None,
    ):
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._max_bytes = max_bytes
        self._max_response_bytes = max_response_bytes
        self._client_factory = client_factory or NavidromeClient
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._locks: dict[str, _LockEntry] = {}
        self._locks_guard = asyncio.Lock()
        self._cache_io_guard = threading.RLock()
        self._tracked_bytes: int | None = None
        runtime_state.set_coverart_cache_limit(max_bytes)

    def cache_dir(self) -> Path:
        directory = self._cache_dir
        if directory is None:
            directory = Path(config.DATABASE_PATH).parent / "coverart-cache"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _path_for(self, source_id: str, item_id: str, size: int) -> Path:
        digest = hashlib.sha256(
            f"{source_id}\x1f{item_id}\x1f{size}".encode("utf-8")
        ).hexdigest()
        return self.cache_dir() / f"{digest}.img"

    @staticmethod
    def _mime_path(path: Path) -> Path:
        return path.with_suffix(".mime")

    def _cached_content_type(self, data: bytes) -> str | None:
        # A sidecar or upstream header is advisory only. Bytes must identify as
        # one of the supported formats before they are served by the proxy.
        return _detect_type(data)

    @asynccontextmanager
    async def _key_lock(self, key: str):
        async with self._locks_guard:
            entry = self._locks.get(key)
            if entry is None:
                entry = _LockEntry(asyncio.Lock())
                self._locks[key] = entry
            entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            async with self._locks_guard:
                entry.users -= 1
                if entry.users == 0 and self._locks.get(key) is entry:
                    self._locks.pop(key, None)

    async def _client_for(self, source_id: str):
        credentials = await credentials_for_source(source_id)
        if credentials is None:
            return None
        return self._client_factory(
            url=credentials["url"],
            user=credentials["user"],
            password=credentials["password"],
        )

    async def load(self, source_id: str, item_id: str, size: int):
        """Return ``(bytes, content_type)`` for an item's cover, or None."""
        path = await asyncio.to_thread(self._path_for, source_id, item_id, size)
        async with self._key_lock(path.name):
            cached = await asyncio.to_thread(self._read_cached, path)
            if cached is not None:
                data, content_type, cache_bytes = cached
                runtime_state.record_coverart_cache_access(
                    hit=True,
                    cache_bytes=cache_bytes,
                    limit_bytes=self._max_bytes,
                )
                return data, content_type
            runtime_state.record_coverart_cache_access(
                hit=False,
                cache_bytes=await asyncio.to_thread(self._cache_bytes),
                limit_bytes=self._max_bytes,
            )
            fetched = await self._fetch(source_id, item_id, size)
            if fetched is None:
                return None
            data, _upstream_content_type = fetched
            if len(data) > self._max_response_bytes:
                return None
            content_type = _detect_type(data)
            if content_type is None:
                return None
            cache_bytes = await asyncio.to_thread(self._store, path, data, content_type)
            runtime_state.coverart_cache_bytes = cache_bytes
            return data, content_type

    async def _fetch(self, source_id: str, item_id: str, size: int):
        client = await self._client_for(source_id)
        if client is None:
            return None
        try:
            return await client.get_cover_art(
                item_id,
                size,
                max_bytes=self._max_response_bytes,
            )
        except Exception:
            return None
        finally:
            await client.close()

    def _read_cached(self, path: Path) -> tuple[bytes, str, int] | None:
        with self._cache_io_guard:
            if not path.exists():
                return None
            path.touch()
            data = path.read_bytes()
            content_type = self._cached_content_type(data)
            if content_type is not None and len(data) <= self._max_response_bytes:
                return data, content_type, self._cache_bytes()
            path.unlink(missing_ok=True)
            self._mime_path(path).unlink(missing_ok=True)
            self._tracked_bytes = None
            return None

    def _store(self, path: Path, data: bytes, content_type: str) -> int:
        with self._cache_io_guard:
            self._cache_bytes()
            path.write_bytes(data)
            self._mime_path(path).write_text(content_type, encoding="ascii")
            self._tracked_bytes += len(data)
            if self._tracked_bytes > self._max_bytes:
                self._evict()
            return self._tracked_bytes

    def _cache_bytes(self) -> int:
        with self._cache_io_guard:
            if self._tracked_bytes is None:
                self._tracked_bytes = sum(
                    path.stat().st_size for path in self.cache_dir().glob("*.img")
                )
            return self._tracked_bytes

    def _evict(self) -> None:
        with self._cache_io_guard:
            files = sorted(self.cache_dir().glob("*.img"), key=lambda p: p.stat().st_mtime)
            total = sum(p.stat().st_size for p in files)
            for path in files:
                if total <= self._max_bytes:
                    break
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
                self._mime_path(path).unlink(missing_ok=True)
            self._tracked_bytes = total

    async def resolve_album_id(
        self,
        source_id: str,
        album: str | None,
        artist: str | None,
    ) -> str | None:
        """Map an album name to a Navidrome album ID, with a 24h miss cache."""
        if not album or not album.strip():
            return None
        key = album_key(album, artist)
        now = self._now()
        cached = await self._lookup_map(source_id, key)
        if cached is not None:
            album_id, attempted_at = cached
            if album_id:
                return album_id
            if now - attempted_at < NEGATIVE_TTL:
                return None

        client = await self._client_for(source_id)
        if client is None:
            return None
        try:
            albums = await client.search3(album.strip())
        except Exception:
            return None
        finally:
            await client.close()

        wanted = album.strip().casefold()
        artist_wanted = (artist or "").strip().casefold()
        match = None
        for candidate in albums:
            if str(candidate.get("name", "")).strip().casefold() != wanted:
                continue
            if artist_wanted and str(candidate.get("artist", "")).strip().casefold() != artist_wanted:
                continue
            match = candidate
            break
        album_id = str(match.get("id", "")) if match else ""
        await self._save_map(source_id, key, album_id, now)
        return album_id or None

    @staticmethod
    async def _lookup_map(source_id: str, key: str):
        async with connect_db(config.DATABASE_PATH) as db:
            async with db.execute(
                "SELECT album_id, attempted_at FROM album_art_map "
                "WHERE source_id = ? AND album_key = ?",
                (source_id, key),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        try:
            attempted = datetime.fromisoformat(str(row[1]))
        except ValueError:
            return None
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=timezone.utc)
        return str(row[0]), attempted

    @staticmethod
    async def _save_map(
        source_id: str,
        key: str,
        album_id: str,
        attempted: datetime,
    ) -> None:
        async with connect_db(config.DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO album_art_map (source_id, album_key, album_id, attempted_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id, album_key) DO UPDATE SET
                    album_id = excluded.album_id,
                    attempted_at = excluded.attempted_at
                """,
                (source_id, key, album_id, utc_instant(attempted)),
            )
            await db.commit()


cover_art_service = CoverArtService()
