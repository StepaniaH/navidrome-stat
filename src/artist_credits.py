"""Artist attribution without creating additional listening records."""

import json
import re
from functools import lru_cache

ARTIST_MODES = ("combined", "separate")
# Unspaced slashes, commas and ampersands also occur in individual artist names.
_SEPARATOR = re.compile(r"\s*;\s*|\s+ / \s+|\s+(?:feat\.?|ft\.?)\s+", re.IGNORECASE | re.VERBOSE)


def normalize_artists(value) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    artists = []
    seen_names = set()
    seen_ids = set()
    for item in value[:64]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 512:
            continue
        name = name.strip()
        artist_id = item.get("id")
        if not isinstance(artist_id, str) or not 0 < len(artist_id) <= 128:
            artist_id = None
        if name.casefold() in seen_names or (artist_id and artist_id in seen_ids):
            continue
        seen_names.add(name.casefold())
        if artist_id:
            seen_ids.add(artist_id)
        artists.append(
            {
                "name": name,
                "id": artist_id,
            }
        )
    return artists


def encode_artists(value) -> str | None:
    artists = normalize_artists(value)
    return json.dumps(artists, ensure_ascii=False) if artists else None


@lru_cache(maxsize=4096)
def artist_credits(
    artist: str | None,
    artists_json: str | None,
    artist_id: str | None = None,
) -> str:
    """SQLite scalar function: structured credits take precedence over legacy text."""
    try:
        artists = normalize_artists(json.loads(artists_json)) if artists_json else []
    except (TypeError, ValueError):
        artists = []
    if not artists and artist:
        artists = normalize_artists([{"name": name} for name in _SEPARATOR.split(artist)])
    if (
        len(artists) == 1
        and artists[0]["name"] == (artist or "").strip()
        and not artists[0]["id"]
        and isinstance(artist_id, str)
        and 0 < len(artist_id) <= 128
    ):
        artists[0]["id"] = artist_id
    return json.dumps(artists, ensure_ascii=False)


def artist_query_source(mode: str) -> tuple[str, str, str]:
    if mode not in ARTIST_MODES:
        raise ValueError("artist_mode must be one of: combined, separate")
    if mode == "combined":
        return "play_history", "artist", "artist_id"
    return (
        """(SELECT play_history.*,
                   json_extract(credit.value, '$.name') AS credited_artist,
                   json_extract(credit.value, '$.id') AS credited_artist_id
            FROM play_history, json_each(artist_credits(artist, artists, artist_id)) AS credit)""",
        "credited_artist",
        "credited_artist_id",
    )
