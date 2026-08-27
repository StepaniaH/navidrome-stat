"""getSongHistory importer seam for the upstream endpoint (Navidrome PR #5650).

Inert until a server advertises the proposed ``getSongHistory`` read API;
pagination, normalization, cutoff suppression, and idempotent writes are all
in place so a native-history import lands the day the endpoint merges.
"""

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
) -> dict[str, int]:
    """Fetch every available history page once and write through ``record``."""
    all_events: list[dict] = []
    skipped = 0
    offset = 0
    while offset <= MAX_EVENTS_PER_RUN:
        envelope = await client.get_song_history(size=PAGE_SIZE, offset=offset)
        entries = _page_entries(envelope)
        events, page_skipped = normalize_song_history_entries(
            entries,
            source_id=source_id,
            source_name=source_name,
            username=username,
        )
        skipped += page_skipped
        all_events.extend(events)
        if len(entries) < PAGE_SIZE or len(all_events) >= MAX_EVENTS_PER_RUN:
            break
        offset += PAGE_SIZE

    cutoff = compute_cutoff(earliest_poller_played_at)
    all_events, suppressed = apply_cutoff(all_events, cutoff)
    skipped += suppressed

    imported = await record(all_events) if all_events else 0
    return {"imported": imported, "skipped": skipped}
