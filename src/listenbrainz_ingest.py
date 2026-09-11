"""Validate ListenBrainz submissions and normalize stored listen events."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

LISTENBRAINZ_MAX_PAYLOAD_BYTES = 10_240_000
LISTENBRAINZ_MAX_LISTENS = 1_000
LISTENBRAINZ_MIN_TIMESTAMP = 1_033_430_400


@dataclass(frozen=True, slots=True)
class ListenBrainzIngestConfig:
    token: str
    username: str
    source_id: str
    source_name: str


@dataclass(frozen=True, slots=True)
class ParsedSubmission:
    listen_type: Literal["single", "import", "playing_now"]
    events: tuple[dict[str, Any], ...]


def _env_text(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def load_ingest_config() -> ListenBrainzIngestConfig | None:
    """Load the optional receiver identity; token presence enables the route."""

    token = _env_text("LISTENBRAINZ_INGEST_TOKEN")
    if token is None:
        return None
    username = _env_text("LISTENBRAINZ_INGEST_USERNAME")
    if username is None:
        raise RuntimeError(
            "LISTENBRAINZ_INGEST_USERNAME is required when the receiver is enabled"
        )
    source_id = _env_text("LISTENBRAINZ_INGEST_SOURCE_ID") or "listenbrainz"
    source_name = _env_text("LISTENBRAINZ_INGEST_SOURCE_NAME") or "ListenBrainz receiver"
    if len(username) > 128:
        raise RuntimeError("LISTENBRAINZ_INGEST_USERNAME must be at most 128 characters")
    if len(source_id) > 128:
        raise RuntimeError("LISTENBRAINZ_INGEST_SOURCE_ID must be at most 128 characters")
    if len(source_name) > 256:
        raise RuntimeError("LISTENBRAINZ_INGEST_SOURCE_NAME must be at most 256 characters")
    return ListenBrainzIngestConfig(
        token=token,
        username=username,
        source_id=source_id,
        source_name=source_name,
    )


def _required_text(value: Any, field: str, *, max_length: int = 1_024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return normalized


def _optional_text(value: Any, *, max_length: int = 1_024) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _track_identity(artist: str, title: str, additional: dict[str, Any]) -> str:
    recording_mbid = _optional_text(additional.get("recording_mbid"), max_length=128)
    if recording_mbid:
        return f"mbid:{recording_mbid}"
    recording_msid = _optional_text(additional.get("recording_msid"), max_length=128)
    if recording_msid:
        return f"msid:{recording_msid}"
    digest = hashlib.sha256(
        f"{artist.casefold()}\0{title.casefold()}".encode("utf-8")
    ).hexdigest()
    return f"listenbrainz:{digest[:32]}"


def _event_key(
    *,
    config: ListenBrainzIngestConfig,
    listened_at: int,
    artist: str,
    title: str,
    track_id: str,
    album: str | None,
    album_id: str | None,
) -> str:
    material = "\0".join(
        (
            "listenbrainz-v1",
            config.source_id,
            config.username.casefold(),
            str(listened_at),
            artist.casefold(),
            title.casefold(),
            track_id.casefold(),
            album.casefold() if album else "",
            album_id.casefold() if album_id else "",
        )
    )
    return f"lb:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def _parse_event(
    item: Any,
    *,
    config: ListenBrainzIngestConfig,
    now_epoch: int,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("each payload entry must be an object")
    listened_at = item.get("listened_at")
    if isinstance(listened_at, bool) or not isinstance(listened_at, int):
        raise ValueError("listened_at must be an integer Unix timestamp")
    if not LISTENBRAINZ_MIN_TIMESTAMP <= listened_at <= now_epoch + 86_400:
        raise ValueError("listened_at is outside the supported timestamp range")
    metadata = item.get("track_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("track_metadata must be an object")
    artist = _required_text(metadata.get("artist_name"), "artist_name")
    title = _required_text(metadata.get("track_name"), "track_name")
    album = _optional_text(metadata.get("release_name"))
    additional = metadata.get("additional_info") or {}
    if not isinstance(additional, dict):
        raise ValueError("additional_info must be an object")
    client_name = _optional_text(
        additional.get("media_player") or additional.get("submission_client"),
        max_length=256,
    )
    artist_mbids = additional.get("artist_mbids")
    artist_id = None
    if isinstance(artist_mbids, list) and artist_mbids:
        artist_id = _optional_text(artist_mbids[0], max_length=128)
    track_id = _track_identity(artist, title, additional)
    album_id = _optional_text(additional.get("release_mbid"), max_length=128)
    played_at = datetime.fromtimestamp(listened_at, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
    return {
        "external_event_key": _event_key(
            config=config,
            listened_at=listened_at,
            artist=artist,
            title=title,
            track_id=track_id,
            album=album,
            album_id=album_id,
        ),
        "played_at": played_at,
        "username": config.username,
        "client_name": client_name,
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "artist_id": artist_id,
        "artists": None,
        "album": album,
        "album_id": album_id,
        # ListenBrainz confirms a play, not its actual listened duration or
        # transcoding mode. Keeping these NULL prevents false precision.
        "is_transcoding": None,
        "listen_duration_sec": None,
        "duration_confidence": "unknown",
        "source": "listenbrainz",
        "source_id": config.source_id,
        "source_name": config.source_name,
    }


def parse_submission(
    payload: Any,
    config: ListenBrainzIngestConfig,
    *,
    now: datetime | None = None,
) -> ParsedSubmission:
    """Validate one protocol payload and normalize permanent listens."""

    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    listen_type = payload.get("listen_type")
    if listen_type not in {"single", "import", "playing_now"}:
        raise ValueError("listen_type must be single, import, or playing_now")
    listens = payload.get("payload")
    if not isinstance(listens, list) or not listens:
        raise ValueError("payload must contain at least one listen")
    if len(listens) > LISTENBRAINZ_MAX_LISTENS:
        raise ValueError(f"payload must contain at most {LISTENBRAINZ_MAX_LISTENS} listens")
    if listen_type in {"single", "playing_now"} and len(listens) != 1:
        raise ValueError(f"{listen_type} payload must contain exactly one listen")
    if listen_type == "playing_now":
        item = listens[0]
        if not isinstance(item, dict) or not isinstance(item.get("track_metadata"), dict):
            raise ValueError("playing_now track_metadata must be an object")
        if "listened_at" in item:
            raise ValueError("playing_now must not include listened_at")
        metadata = item["track_metadata"]
        _required_text(metadata.get("artist_name"), "artist_name")
        _required_text(metadata.get("track_name"), "track_name")
        return ParsedSubmission(listen_type="playing_now", events=())

    moment = now or datetime.now(timezone.utc)
    now_epoch = int(moment.timestamp())
    return ParsedSubmission(
        listen_type=listen_type,
        events=tuple(
            _parse_event(item, config=config, now_epoch=now_epoch) for item in listens
        ),
    )
