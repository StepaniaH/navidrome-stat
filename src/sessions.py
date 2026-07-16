from datetime import datetime
from typing import Awaitable, Callable, Optional

PLAY_THRESHOLD_SEC = 30
STALE_THRESHOLD_SEC = 30

SaveSessionCallback = Callable[[dict], Awaitable[None]]


class PlaybackSessionTracker:
    """Tracks in-memory playback sessions between Navidrome polls."""

    def __init__(
        self,
        save_session: SaveSessionCallback,
        *,
        play_threshold_sec: int = PLAY_THRESHOLD_SEC,
        stale_threshold_sec: int = STALE_THRESHOLD_SEC,
    ):
        self.active_sessions: dict[str, dict] = {}
        self._save_session = save_session
        self.play_threshold_sec = play_threshold_sec
        self.stale_threshold_sec = stale_threshold_sec

    async def finalize_session(self, player_id: str) -> None:
        if player_id not in self.active_sessions:
            return

        session = self.active_sessions.pop(player_id)
        duration = (session["last_seen_at"] - session["first_seen_at"]).total_seconds()

        if duration >= self.play_threshold_sec:
            session["duration_sec"] = int(duration)
            session["last_seen_at"] = session["last_seen_at"].isoformat()
            await self._save_session(session)

    async def finalize_all(self) -> None:
        for player_id in list(self.active_sessions.keys()):
            await self.finalize_session(player_id)

    def _normalize_entries(self, entries) -> list[dict]:
        if isinstance(entries, dict):
            return [entries]
        if isinstance(entries, list):
            return entries
        return []

    def _session_from_entry(self, entry: dict, current_time: datetime) -> dict:
        return {
            "first_seen_at": current_time,
            "last_seen_at": current_time,
            "username": entry.get("username"),
            "client_name": entry.get("playerName"),
            "track_id": entry.get("id"),
            "title": entry.get("title"),
            "artist": entry.get("artist"),
            "album": entry.get("album"),
            "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
        }

    async def process_poll(self, entries, current_time: datetime) -> None:
        seen_player_ids: set[str] = set()

        for entry in self._normalize_entries(entries):
            if not entry.get("isPlaying", True):
                continue

            player_id_raw = entry.get("playerId")
            if player_id_raw is None:
                continue

            player_id = str(player_id_raw)
            track_id = entry.get("id")
            seen_player_ids.add(player_id)

            if player_id in self.active_sessions:
                if self.active_sessions[player_id]["track_id"] == track_id:
                    self.active_sessions[player_id]["last_seen_at"] = current_time
                else:
                    await self.finalize_session(player_id)
                    self.active_sessions[player_id] = self._session_from_entry(entry, current_time)
            else:
                self.active_sessions[player_id] = self._session_from_entry(entry, current_time)

        stale_players: list[str] = []
        for pid, session in self.active_sessions.items():
            if pid not in seen_player_ids:
                time_since_last_seen = (current_time - session["last_seen_at"]).total_seconds()
                if time_since_last_seen >= self.stale_threshold_sec:
                    stale_players.append(pid)

        for pid in stale_players:
            await self.finalize_session(pid)
