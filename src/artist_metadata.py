"""Best-effort artist metadata lookup within one Navidrome source."""

import asyncio
import time
from collections import OrderedDict

from src.artist_credits import normalize_artists
from src.client import NavidromeClient


class ArtistMetadataResolver:
    """Bound lookup latency, request volume and memory independently of polling."""

    CACHE_SIZE = 1024
    CACHE_TTL_SEC = 6 * 60 * 60
    MISSING_TTL_SEC = 5 * 60
    FAILURE_TTL_SEC = 30
    LOOKUP_TIMEOUT_SEC = 2
    LOOKUPS_PER_POLL = 4

    def __init__(self, client: NavidromeClient):
        self.client = client
        self._cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()

    def _cached(self, track_id: str) -> list[dict] | None:
        cached = self._cache.get(track_id)
        if cached is None:
            return None
        expires, artists = cached
        if time.monotonic() >= expires:
            self._cache.pop(track_id)
            return None
        self._cache.move_to_end(track_id)
        return artists

    def _remember(self, track_id: str, artists: list[dict], ttl: float) -> None:
        self._cache[track_id] = (time.monotonic() + ttl, artists)
        self._cache.move_to_end(track_id)
        while len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)

    async def get_artists(self, track_id: str) -> list[dict]:
        cached = self._cached(track_id)
        if cached is not None:
            return [dict(artist) for artist in cached]
        artists = []
        ttl = self.MISSING_TTL_SEC
        try:
            data = await asyncio.wait_for(
                self.client.get_song(track_id), timeout=self.LOOKUP_TIMEOUT_SEC,
            )
            if NavidromeClient.response_is_ok(data):
                song = data["subsonic-response"].get("song")
                if isinstance(song, dict) and song.get("id") == track_id:
                    artists = normalize_artists(song.get("artists"))
            else:
                ttl = self.FAILURE_TTL_SEC
        except Exception:
            # Lookup failure must not discard playback observations. Request
            # exceptions can contain credentials, so do not log their text.
            ttl = self.FAILURE_TTL_SEC
        self._remember(track_id, artists, self.CACHE_TTL_SEC if artists else ttl)
        return [dict(artist) for artist in artists]

    async def enrich_entries(self, entries):
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return entries
        enriched = [dict(entry) if isinstance(entry, dict) else entry for entry in entries]
        missing: dict[str, list[dict]] = {}
        for entry in enriched:
            if not isinstance(entry, dict):
                continue
            track_id = entry.get("id")
            if not isinstance(track_id, str) or not 0 < len(track_id) <= 128:
                continue
            artists = normalize_artists(entry.get("artists"))
            if artists:
                entry["artists"] = artists
                self._remember(track_id, artists, self.CACHE_TTL_SEC)
            elif entry.get("playerId") is not None:
                missing.setdefault(track_id, []).append(entry)

        # Process cached tracks first, then at most one bounded parallel batch.
        # Remaining tracks are eligible on later polls as earlier results cache.
        lookups = []
        for track_id, targets in missing.items():
            cached = self._cached(track_id)
            if cached is not None:
                for entry in targets:
                    if cached:
                        entry["artists"] = [dict(artist) for artist in cached]
            elif len(lookups) < self.LOOKUPS_PER_POLL:
                lookups.append(track_id)
        results = await asyncio.gather(*(self.get_artists(track_id) for track_id in lookups))
        for track_id, artists in zip(lookups, results):
            if artists:
                for entry in missing[track_id]:
                    entry["artists"] = [dict(artist) for artist in artists]
        return enriched
