from datetime import datetime
from typing import Awaitable, Callable
import uuid

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
        source_id: str = "legacy",
        source_name: str = "Legacy environment source",
    ):
        self.active_sessions: dict[str, dict] = {}
        self._save_session = save_session
        self.play_threshold_sec = play_threshold_sec
        self.stale_threshold_sec = stale_threshold_sec
        self.pause_grace_sec = pause_grace_sec
        self._save_attempt = save_attempt
        self.source_id = source_id
        self.source_name = source_name

    async def finalize_session(self, player_id: str) -> None:
        if player_id not in self.active_sessions:
            return

        session = self.active_sessions[player_id]
        duration = session.get("active_duration_sec", 0.0)
        if duration >= self.play_threshold_sec:
            await self._commit_session(session, int(duration), finalized=True)
        elif self._save_attempt is not None:
            await self._save_attempt({
                **session,
                "duration_sec": int(duration),
                "outcome": "short_play",
                "last_seen_at": (session.get("last_active_at") or session["last_seen_at"]).isoformat(),
            })
        self.active_sessions.pop(player_id, None)

    async def _commit_session(
        self,
        session: dict,
        duration_sec: int,
        *,
        finalized: bool,
    ) -> None:
        # ``played_at`` is anchored to the last actively-playing observation,
        # excluding the post-pause/missing wall-clock gap.
        last_active = session.get("last_active_at") or session["last_seen_at"]
        payload = {
            **session,
            "duration_sec": duration_sec,
            "last_seen_at": last_active.isoformat(),
            "finalized": finalized,
            "finalized_at": last_active.isoformat() if finalized else None,
        }
        await self._save_session(payload)

    async def _maybe_commit_active_session(self, player_id: str) -> None:
        session = self.active_sessions.get(player_id)
        if not session or session.get("committed"):
            return

        duration = session.get("active_duration_sec", 0.0)
        if duration >= self.play_threshold_sec:
            await self._commit_session(session, int(duration), finalized=False)
            # Mark committed only after durable persistence succeeds. If the
            # callback raises, the active session remains eligible for retry.
            session["committed"] = True

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
        position_ms = self._position_ms(entry)
        return {
            "session_id": uuid.uuid4().hex,
            "first_seen_at": current_time,
            "last_seen_at": current_time,
            "last_active_at": current_time,
            "active_duration_sec": 0.0,
            "last_position_ms": position_ms,
            "duration_confidence": (
                "reported"
                if self._has_playback_report(entry) and position_ms is not None
                else "estimated"
            ),
            "username": entry.get("username"),
            "client_name": entry.get("playerName"),
            "track_id": entry.get("id"),
            "title": entry.get("title"),
            "artist": entry.get("artist"),
            "album": entry.get("album"),
            "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
            "paused": False,
            "source_id": self.source_id,
            "source_name": self.source_name,
        }

    @staticmethod
    def _position_ms(entry: dict) -> float | None:
        value = entry.get("positionMs")
        if isinstance(value, bool):
            return None
        try:
            position = float(value)
        except (TypeError, ValueError):
            return None
        return position if position >= 0 else None

    @staticmethod
    def _playback_rate(entry: dict) -> float:
        value = entry.get("playbackRate", 1)
        if isinstance(value, bool):
            return 1.0
        try:
            rate = float(value)
        except (TypeError, ValueError):
            return 1.0
        return rate if rate > 0 else 1.0

    @staticmethod
    def _has_playback_report(entry: dict) -> bool:
        return entry.get("state") is not None

    @staticmethod
    def _is_playing(entry: dict) -> bool:
        state = entry.get("state")
        if isinstance(state, str):
            return state.lower() in {"starting", "playing"}
        return bool(entry.get("isPlaying", True))

    def _active_delta(self, session: dict, entry: dict, current_time: datetime) -> float:
        wall_delta = (current_time - session["last_active_at"]).total_seconds()
        if wall_delta <= 0:
            return 0.0

        current_position = self._position_ms(entry)
        previous_position = session.get("last_position_ms")
        if (
            self._has_playback_report(entry)
            and current_position is not None
            and previous_position is not None
        ):
            session["duration_confidence"] = "reported"
            progress_ms = current_position - previous_position
            if progress_ms == 0:
                return 0.0
            if progress_ms < 0:
                # A backwards seek still consumed wall-clock listening time;
                # do not count media position twice.
                return wall_delta
            reported_delta = progress_ms / 1000 / self._playback_rate(entry)
            # A large forward seek must not be counted as listened time.
            if reported_delta > wall_delta * 2 + 2:
                return wall_delta
            return min(reported_delta, wall_delta)

        session["duration_confidence"] = "estimated"
        return wall_delta

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
            is_playing = self._is_playing(entry)

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
                        session["last_position_ms"] = self._position_ms(entry)
                        session["paused"] = False
                    else:
                        delta = self._active_delta(session, entry, current_time)
                        if delta > 0:
                            session["active_duration_sec"] += delta
                        session["last_active_at"] = current_time
                        session["last_position_ms"] = self._position_ms(entry)
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
            await self.finalize_session(pid)
