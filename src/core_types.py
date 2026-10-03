"""Small immutable values and structural payloads at core service boundaries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Literal, Mapping, NotRequired, TypedDict

from src.artist_credits import normalize_artists

DurationQuality = Literal["reported", "estimated", "lower_bound", "unknown"]


def classify_history_duration_quality(
    *,
    listen_duration_sec: int | None,
    source: str | None,
    session_id: str | None,
    finalized: bool | int | None,
    duration_confidence: str | None,
) -> DurationQuality:
    """Return the strongest duration claim supported by one history row."""

    if listen_duration_sec is None:
        return "unknown"
    if duration_confidence == "lower_bound":
        return "lower_bound"
    if source == "poller":
        if not session_id or not bool(finalized):
            return "lower_bound"
        return "estimated"
    if duration_confidence == "reported":
        return "reported"
    return "estimated"


def combine_duration_qualities(
    qualities: Iterable[DurationQuality],
) -> DurationQuality:
    """Combine row-level claims without overstating an aggregate duration."""

    observed = set(qualities)
    if not observed or observed == {"unknown"}:
        return "unknown"
    if "unknown" in observed or "lower_bound" in observed:
        return "lower_bound"
    if "estimated" in observed:
        return "estimated"
    return "reported"


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Validated-shape server configuration detached from mutable request dicts."""

    id: str
    display_name: str
    url: str
    username: str
    password: str
    enabled: bool = True
    backfill_playlist_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ServerConfig:
        return cls(
            id=value["id"],
            display_name=value["display_name"],
            url=value["url"],
            username=value["username"],
            password=value["password"],
            enabled=bool(value.get("enabled", True)),
            backfill_playlist_id=value.get("backfill_playlist_id") or None,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "url": self.url,
            "username": self.username,
            "password": self.password,
            "enabled": self.enabled,
            "backfill_playlist_id": self.backfill_playlist_id,
        }


def _text(value: object, *, identifier: bool = False, max_length: int = 1024) -> str | None:
    if identifier and isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > (128 if identifier else max_length):
        return None
    return value


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and number >= 0 else None


@dataclass(frozen=True, slots=True)
class ArtistCredit:
    name: str
    id: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybackObservation:
    """Normalized upstream values, detached from mutable response metadata."""

    player_id: str | None = None
    track_id: str | None = None
    username: str | None = None
    player_name: str | None = None
    title: str | None = None
    artist: str | None = None
    artist_id: str | None = None
    artists: tuple[ArtistCredit, ...] = ()
    album: str | None = None
    album_id: str | None = None
    transcoded_content_type: str | None = None
    position_ms: float | None = None
    playback_rate: float = 1.0
    state: str | None = None
    is_playing: bool = True

    def artist_mappings(self) -> list[dict[str, str | None]]:
        return [{"name": credit.name, "id": credit.id} for credit in self.artists]

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> PlaybackObservation:
        return cls(
            player_id=_text(value.get("playerId"), identifier=True),
            track_id=_text(value.get("id"), identifier=True),
            username=_text(value.get("username"), max_length=128),
            player_name=_text(value.get("playerName")),
            title=_text(value.get("title")),
            artist=_text(value.get("artist"), max_length=512),
            artist_id=_text(value.get("artistId"), identifier=True),
            artists=tuple(ArtistCredit(**item) for item in normalize_artists(value.get("artists"))),
            album=_text(value.get("album"), max_length=512),
            album_id=_text(value.get("albumId"), identifier=True),
            transcoded_content_type=_text(value.get("transcodedContentType")),
            position_ms=_number(value.get("positionMs")),
            playback_rate=_number(value.get("playbackRate")) or 1.0,
            state=_text(value.get("state")),
            is_playing=value.get("isPlaying", True) is True,
        )


class PlaybackMetadata(TypedDict):
    username: str | None
    client_name: str | None
    track_id: str | None
    title: str | None
    artist: str | None
    artist_id: str | None
    artists: list[dict[str, str | None]] | None
    album: str | None
    album_id: str | None
    is_transcoding: int
    source_id: str
    source_name: str


class PlaybackSession(PlaybackMetadata):
    """Required live tracker state; timestamps stay as datetime values."""

    session_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    last_active_at: datetime
    active_duration_sec: float
    last_position_ms: float | None
    duration_confidence: str
    paused: bool
    committed: NotRequired[bool]
    last_checkpoint_duration_sec: NotRequired[float]
    artist_metadata_changed: NotRequired[bool]
    discarded: NotRequired[bool]


class PlaybackWrite(PlaybackMetadata):
    """Durable fields only, with serialized timestamps at the write boundary."""

    session_id: str
    last_seen_at: str
    duration_sec: int
    duration_confidence: str
    finalized: bool
    finalized_at: str | None
    checkpointed_at: str
    outcome: NotRequired[str]
