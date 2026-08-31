"""getSongHistory importer for the proposed upstream endpoint (Navidrome PR #5650).

Inert until a server advertises the proposed ``getSongHistory`` read API;
pagination, normalization, cutoff suppression, and idempotent writes are all
in place so a native-history import lands the day the endpoint merges.
"""

from collections.abc import Awaitable, Callable

from src.config import env_int
from src.importers.events import apply_cutoff, normalize_song_history_entries
from src.importers.playlist_backfill import (
    ImportSourceError,
    compute_cutoff,
)

PAGE_SIZE = env_int(
    "SONG_HISTORY_PAGE_SIZE", default=200, min_value=1, max_value=1000
)
MAX_EVENTS_PER_RUN = env_int(
    "SONG_HISTORY_MAX_EVENTS_PER_RUN", default=5000, min_value=100, max_value=100000
)


def _page_entries(envelope) -> list:
    if not isinstance(envelope, dict):
        return []
    response = envelope.get("subsonic-response")
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise ImportSourceError("upstream rejected getSongHistory request")
    history = response.get("songHistory")
    if not isinstance(history, dict):
        return []
    entries = history.get("entry")
    if isinstance(entries, list):
        return entries
    if isinstance(entries, dict):
        return [entries]
    return []


async def run_song_history(
    client,
    *,
    record,
    source_id: str,
    source_name: str,
    username: str,
    earliest_poller_played_at: str | None = None,
    start_offset: int = 0,
    checkpoint: Callable[[int, bool], Awaitable[None]] | None = None,
) -> dict[str, int | bool]:
    """Import a limited number of pages and checkpoint each committed page."""
    imported = 0
    skipped = 0
    processed = 0
    offset = max(int(start_offset), 0)
    next_offset = offset
    complete = False
    cutoff = compute_cutoff(earliest_poller_played_at)

    while processed < MAX_EVENTS_PER_RUN:
        request_size = min(PAGE_SIZE, MAX_EVENTS_PER_RUN - processed)
        envelope = await client.get_song_history(size=request_size, offset=offset)
        entries = _page_entries(envelope)
        events, page_skipped = normalize_song_history_entries(
            entries,
            source_id=source_id,
            source_name=source_name,
            username=username,
        )
        skipped += page_skipped
        events, suppressed = apply_cutoff(events, cutoff)
        skipped += suppressed
        if events:
            imported += await record(events)

        processed += len(entries)
        next_offset = offset + len(entries)
        complete = len(entries) < request_size
        if checkpoint is not None:
            await checkpoint(next_offset, complete)
        if complete or processed >= MAX_EVENTS_PER_RUN:
            break
        offset = next_offset

    return {
        "imported": imported,
        "skipped": skipped,
        "next_offset": next_offset,
        "complete": complete,
    }
