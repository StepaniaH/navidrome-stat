"""Small immutable values and structural payloads at core service boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, TypedDict

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


@dataclass(frozen=True, slots=True)
class PlaybackObservation:
    """One immutable upstream playback observation used by session tracking."""

    player_id: Any = None
    track_id: Any = None
    username: Any = None
    player_name: Any = None
    title: Any = None
    artist: Any = None
    artist_id: Any = None
    artists: Any = None
    album: Any = None
    album_id: Any = None
    transcoded_content_type: Any = None
    position_ms: Any = None
    playback_rate: Any = 1
    state: Any = None
    is_playing: Any = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PlaybackObservation:
        return cls(
            player_id=value.get("playerId"),
            track_id=value.get("id"),
            username=value.get("username"),
            player_name=value.get("playerName"),
            title=value.get("title"),
            artist=value.get("artist"),
            artist_id=value.get("artistId"),
            artists=value.get("artists"),
            album=value.get("album"),
            album_id=value.get("albumId"),
            transcoded_content_type=value.get("transcodedContentType"),
            position_ms=value.get("positionMs"),
            playback_rate=value.get("playbackRate", 1),
            state=value.get("state"),
            is_playing=value.get("isPlaying", True),
        )


class PlaybackSession(TypedDict, total=False):
    """Mutable tracker state and persistence payload shape."""

    session_id: str
    first_seen_at: datetime
    last_seen_at: datetime | str
    last_active_at: datetime
    active_duration_sec: float
    last_position_ms: float | None
    duration_confidence: str
    username: Any
    client_name: Any
    track_id: Any
    title: Any
    artist: Any
    artist_id: Any
    artists: Any
    album: Any
    album_id: Any
    is_transcoding: int
    paused: bool
    source_id: str
    source_name: str
    duration_sec: int
    outcome: str
    finalized: bool
    finalized_at: str | None
    checkpointed_at: str
    committed: bool
    last_checkpoint_duration_sec: float
    discarded: bool
