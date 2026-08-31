"""Normalize upstream payloads into uniform, dedup-keyed listen events.

All importers emit the event shape consumed by ``play_history`` writes:
provenance columns (``source``/``source_id``/``source_name``), a
deterministic ``external_event_key`` that makes re-runs idempotent, and
accurate confidence values (imported durations are unknown, so they stay
NULL and count as plays without inflating listening minutes).
"""

from datetime import datetime, timezone

BACKFILL_SOURCE = "backfill"
SONG_HISTORY_SOURCE = "song_history"


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    return str(value)


def parse_instant(value) -> datetime | None:
    """Parse epoch seconds/milliseconds or ISO-8601 text as UTC."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        # Timestamps at/after 1e11 are millisecond epochs; no real second
        # value reaches year 5138.
        if seconds >= 100_000_000_000:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _format_instant(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _base_event(
    *,
    source: str,
    source_id: str,
    source_name: str,
    username: str,
    track_id: str,
    played_at: str,
) -> dict:
    return {
        "external_event_key": "",
        "played_at": played_at,
        "username": username,
        "client_name": None,
        "track_id": track_id,
        "title": None,
        "artist": None,
        "artist_id": None,
        "album": None,
        "album_id": None,
        "is_transcoding": 0,
        "listen_duration_sec": None,
        "duration_confidence": "estimated",
        "source": source,
        "source_id": source_id,
        "source_name": source_name,
    }


def _as_entry_list(entries) -> list:
    if isinstance(entries, dict):
        return [entries]
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def apply_cutoff(
    events: list[dict],
    cutoff: str | None,
) -> tuple[list[dict], int]:
    """Split event lists at the live-poller coverage bound.

    Returns ``(kept, suppressed)``; a ``None`` cutoff keeps everything.
    """
    if cutoff is None:
        return events, 0
    kept = [event for event in events if event["played_at"] < cutoff]
    return kept, len(events) - len(kept)


def _normalize_entries(
    entries,
    *,
    source: str,
    timestamp_field: str,
    key_prefix: str,
    source_id: str,
    source_name: str,
    username: str,
) -> tuple[list[dict], int]:
    events: list[dict] = []
    skipped = 0
    for entry in _as_entry_list(entries):
        track_id = _stringify(entry.get("id"))
        instant = parse_instant(entry.get(timestamp_field))
        if track_id is None or track_id == "" or instant is None:
            skipped += 1
            continue
        played_at = _format_instant(instant)
        event = _base_event(
            source=source,
            source_id=source_id,
            source_name=source_name,
            username=username,
            track_id=track_id,
            played_at=played_at,
        )
        event["external_event_key"] = (
            f"{key_prefix}:{source_id}:{track_id}:{played_at}"
        )
        event["title"] = entry.get("title")
        event["artist"] = entry.get("artist")
        event["artist_id"] = entry.get("artistId")
        event["album"] = entry.get("album")
        event["album_id"] = entry.get("albumId")
        events.append(event)
    return events, skipped


def normalize_playlist_entries(
    entries,
    *,
    source_id: str,
    source_name: str,
    username: str,
) -> tuple[list[dict], int]:
    """Convert smart-playlist tracks into one estimated event per track.

    Only each track's last-played time is exact; older listens under the same
    playCount cannot be reconstructed and are deliberately not invented.
    """
    return _normalize_entries(
        entries,
        source=BACKFILL_SOURCE,
        timestamp_field="played",
        key_prefix=BACKFILL_SOURCE,
        source_id=source_id,
        source_name=source_name,
        username=username,
    )


def normalize_song_history_entries(
    entries,
    *,
    source_id: str,
    source_name: str,
    username: str,
) -> tuple[list[dict], int]:
    """Convert getSongHistory entries (``playedAt`` epochs) into events."""
    return _normalize_entries(
        entries,
        source=SONG_HISTORY_SOURCE,
        timestamp_field="playedAt",
        key_prefix="gsh",
        source_id=source_id,
        source_name=source_name,
        username=username,
    )
