"""Backfill bridge: recover pre-install history through a smart playlist.

Reads the user-configured ``.nsp`` playlist via ``getPlaylist`` and converts
each track's last-played timestamp into one estimated listen event. Events on
or after the live-poller coverage boundary are suppressed so the bridge and
the poller never double-count the same listen.
"""

from datetime import timedelta

from src.config import env_int
from src.importers.events import (
    apply_cutoff,
    normalize_playlist_entries,
    parse_instant,
)

BACKFILL_CUTOFF_MARGIN_SEC = env_int(
    "BACKFILL_CUTOFF_MARGIN_SEC", default=60, min_value=0, max_value=3600
)


class ImportSourceError(RuntimeError):
    """The upstream import source rejected or failed the request."""


def _format_instant(moment) -> str:
    return moment.isoformat(timespec="seconds")


def compute_cutoff(earliest_poller_played_at: str | None, *, margin_sec: int | None = None) -> str | None:
    """Return the latest still-importable timestamp as an exclusive bound."""
    if earliest_poller_played_at is None:
        return None
    earliest = parse_instant(earliest_poller_played_at)
    if earliest is None:
        return None
    margin = (
        BACKFILL_CUTOFF_MARGIN_SEC if margin_sec is None else margin_sec
    )
    return _format_instant(earliest - timedelta(seconds=margin))


def _playlist_entries(envelope) -> list:
    if not isinstance(envelope, dict):
        return []
    response = envelope.get("subsonic-response")
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise ImportSourceError("upstream rejected getPlaylist request")
    playlist = response.get("playlist")
    if not isinstance(playlist, dict):
        return []
    entries = playlist.get("entry")
    if isinstance(entries, list):
        return entries
    if isinstance(entries, dict):
        return [entries]
    return []


async def run_backfill(
    client,
    *,
    playlist_id: str,
    record,
    source_id: str,
    source_name: str,
    username: str,
    earliest_poller_played_at: str | None = None,
) -> dict[str, int]:
    """Sync once against the configured playlist and write through ``record``."""
    envelope = await client.get_playlist(playlist_id)
    cutoff = compute_cutoff(earliest_poller_played_at)
    events, skipped = normalize_playlist_entries(
        _playlist_entries(envelope),
        source_id=source_id,
        source_name=source_name,
        username=username,
    )
    events, suppressed = apply_cutoff(events, cutoff)
    skipped += suppressed
    imported = await record(events) if events else 0
    return {"imported": imported, "skipped": skipped}
