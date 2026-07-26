from datetime import datetime
from typing import Awaitable, Callable

from src.config import env_int

# Module-level defaults keep backwards compatibility for direct construction
# (tests, embedders). Effective runtime values are resolved in ``src.main``
# from the environment and passed into the tracker constructor.
PLAY_THRESHOLD_SEC = 30
STALE_THRESHOLD_SEC = 30
PAUSE_GRACE_SEC = 30

# Resolve env-driven defaults once at import time so simple consumers that
# construct ``PlaybackSessionTracker(save_session)`` still honour env vars.
_DEFAULT_PLAY_THRESHOLD_SEC = env_int(
    "PLAY_THRESHOLD_SEC", default=30, min_value=1, max_value=3600
)
_DEFAULT_PAUSE_GRACE_SEC = env_int(
    "PAUSE_GRACE_SEC", default=30, min_value=0, max_value=3600
)

SaveSessionCallback = Callable[[dict], Awaitable[None]]


class PlaybackSessionTracker:
    """Tracks in-memory playback sessions between Navidrome polls.

    Duration semantics (active listen time)
    --------------------------------------
    A running session accumulates ``active_duration_sec`` from
    actively-playing observations only. Each actively-playing poll of the
    same track adds ``current_time - previous_active_at`` to the accumulator;
    paused (``isPlaying=false``) and missing polls update neither the
    accumulator nor ``last_active_at``. On the next actively-playing poll
    after a pause/missing interval, accumulation is continued from the
    resume timestamp, so the idle gap is excluded from listen duration.
    A different actively-playing track from the same player finalizes the
    old session immediately.

    The accumulator already includes the final active interval when the
    commit is triggered during an actively-playing poll. ``finalize_session``
    uses ``active_duration_sec`` verbatim with no further addition, matching
    the documented ``>= threshold`` behavior for the common
    ``t0`` active, ``t1`` active sequence (yields ``t1 - t0``).
    """

    def __init__(
        self,
        save_session: SaveSessionCallback,
        *,
        play_threshold_sec: int = _DEFAULT_PLAY_THRESHOLD_SEC,
        stale_threshold_sec: int = STALE_THRESHOLD_SEC,
        pause_grace_sec: int = _DEFAULT_PAUSE_GRACE_SEC,
        save_attempt: SaveSessionCallback | None = None,
    ):
        self.active_sessions: dict[str, dict] = {}
        self._save_session = save_session
        self.play_threshold_sec = play_threshold_sec
        self.stale_threshold_sec = stale_threshold_sec
        self.pause_grace_sec = pause_grace_sec
        self._save_attempt = save_attempt

    async def finalize_session(self, player_id: str) -> None:
        if player_id not in self.active_sessions:
            return

        session = self.active_sessions.pop(player_id)
        if session.get("committed"):
            return

        duration = session.get("active_duration_sec", 0.0)
        if duration >= self.play_threshold_sec:
            await self._commit_session(session, int(duration))
        elif self._save_attempt is not None:
            await self._save_attempt({
                **session,
                "duration_sec": int(duration),
                "outcome": "short_play",
                "last_seen_at": (session.get("last_active_at") or session["last_seen_at"]).isoformat(),
            })

    async def _commit_session(self, session: dict, duration_sec: int) -> None:
        # ``played_at`` is anchored to the last actively-playing observation,
        # excluding the post-pause/missing wall-clock gap.
        last_active = session.get("last_active_at") or session["last_seen_at"]
        payload = {
            **session,
            "duration_sec": duration_sec,
            "last_seen_at": last_active.isoformat(),
        }
        await self._save_session(payload)

    async def _maybe_commit_active_session(self, player_id: str) -> None:
        session = self.active_sessions.get(player_id)
        if not session or session.get("committed"):
            return

        duration = session.get("active_duration_sec", 0.0)
        if duration >= self.play_threshold_sec:
            session["committed"] = True
            await self._commit_session(session, int(duration))

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
            "last_active_at": current_time,
            "active_duration_sec": 0.0,
            "username": entry.get("username"),
            "client_name": entry.get("playerName"),
            "track_id": entry.get("id"),
            "title": entry.get("title"),
            "artist": entry.get("artist"),
            "album": entry.get("album"),
            "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
            "paused": False,
        }

    async def process_poll(self, entries, current_time: datetime) -> None:
        # Players in this set emitted an actively-playing observation this
        # poll and are skipped by the grace-expiration sweep below. Paused
        # matching entries update the session but are deliberately NOT added
        # here, so the sweep can still finalize/expire them once
        # ``pause_grace_sec`` elapses since the last actively-playing
        # observation. This keeps repeated ``isPlaying=false`` polls for the
        # same track from keeping a session alive past its grace window.
        actively_seen_player_ids: set[str] = set()

        for entry in self._normalize_entries(entries):
            player_id_raw = entry.get("playerId")
            if player_id_raw is None:
                continue

            player_id = str(player_id_raw)
            track_id = entry.get("id")
            is_playing = entry.get("isPlaying", True)

            if not is_playing:
                # Paused entry for a matching in-memory session: refresh the
                # seen timestamp and mark it paused without advancing listen
                # duration, but do not suppress the grace-expiration sweep.
                if (
                    player_id in self.active_sessions
                    and self.active_sessions[player_id]["track_id"] == track_id
                ):
                    session = self.active_sessions[player_id]
                    session["last_seen_at"] = current_time
                    session["paused"] = True
                continue

            actively_seen_player_ids.add(player_id)

            if player_id in self.active_sessions:
                if self.active_sessions[player_id]["track_id"] == track_id:
                    session = self.active_sessions[player_id]
                    if session.get("paused"):
                        # Resume same track after a pause/missing window:
                        # continue accumulating from the resume timestamp so
                        # the idle gap is excluded from listen duration.
                        session["last_active_at"] = current_time
                        session["paused"] = False
                    else:
                        delta = (current_time - session["last_active_at"]).total_seconds()
                        if delta > 0:
                            session["active_duration_sec"] += delta
                            session["last_active_at"] = current_time
                    session["last_seen_at"] = current_time
                    await self._maybe_commit_active_session(player_id)
                else:
                    # Different actively-playing track: finalize old session
                    # immediately and start a new one.
                    await self.finalize_session(player_id)
                    self.active_sessions[player_id] = self._session_from_entry(entry, current_time)
            else:
                self.active_sessions[player_id] = self._session_from_entry(entry, current_time)

        stale_players: list[str] = []
        for pid, session in self.active_sessions.items():
            if pid in actively_seen_player_ids:
                continue
            last_active = session.get("last_active_at") or session["last_seen_at"]
            time_since_active = (current_time - last_active).total_seconds()
            if time_since_active < self.pause_grace_sec:
                # Player paused or went missing but still inside the grace
                # window: keep the in-memory session alive (whether or not it
                # has been committed) and exclude the idle gap from duration
                # by anchoring the next active poll to its resume timestamp.
                session["paused"] = True
                session["last_seen_at"] = current_time
                continue
            stale_players.append(pid)

        for pid in stale_players:
            if pid not in self.active_sessions:
                continue
            if self.active_sessions[pid].get("committed"):
                # Already saved once: just drop the in-memory session, no
                # duplicate commit.
                self.active_sessions.pop(pid)
            else:
                await self.finalize_session(pid)