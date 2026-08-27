import uuid
from datetime import datetime
from typing import Awaitable, Callable

from src.config import env_int

PLAY_THRESHOLD_SEC = 30
STALE_THRESHOLD_SEC = 30
PAUSE_GRACE_SEC = 30

# OpenSubsonic playbackReport terminal states: a stopped (or expired) entry
# ends the session immediately instead of entering the pause grace window.
TERMINAL_PLAYBACK_STATES = frozenset({"stopped", "expired"})

# Constructor defaults are read from the environment once at import time.
_DEFAULT_PLAY_THRESHOLD_SEC = env_int(
    "PLAY_THRESHOLD_SEC", default=30, min_value=1, max_value=3600
)
_DEFAULT_PAUSE_GRACE_SEC = env_int(
    "PAUSE_GRACE_SEC", default=30, min_value=0, max_value=3600
)
_DEFAULT_CHECKPOINT_INTERVAL_SEC = env_int(
    "CHECKPOINT_INTERVAL_SEC", default=60, min_value=10, max_value=3600
)

SaveSessionCallback = Callable[[dict], Awaitable[None]]


class SessionFinalizationError(RuntimeError):
    """Redacted batch-finalization failure."""


class PlaybackPersistenceError(RuntimeError):
    """A durable playback write failed after the upstream poll succeeded."""


class PlaybackSessionTracker:
    """Tracks in-memory playback sessions between Navidrome polls.

    Only intervals between active observations add to `active_duration_sec`;
    paused and missing gaps are excluded. A track change finalizes the current
    session immediately.
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
        supports_playback_report: bool = False,
        checkpoint_interval_sec: int = _DEFAULT_CHECKPOINT_INTERVAL_SEC,
    ):
        self._sessions: dict[str, dict] = {}
        self._save_session = save_session
        self.play_threshold_sec = play_threshold_sec
        self.stale_threshold_sec = stale_threshold_sec
        self.pause_grace_sec = pause_grace_sec
        self._save_attempt = save_attempt
        self.source_id = source_id
        self.source_name = source_name
        self.supports_playback_report = supports_playback_report
        self.checkpoint_interval_sec = checkpoint_interval_sec

    def set_playback_report_supported(self, supported: bool) -> None:
        """Use playback-report timing when the server advertises it."""
        self.supports_playback_report = bool(supported)

    def now_playing(self) -> list[dict]:
        """Return copies of unpaused sessions for display endpoints."""
        return [
            dict(session)
            for session in self._sessions.values()
            if not session.get("paused")
        ]

    def active_count(self) -> int:
        """Count unpaused sessions."""
        return sum(
            1 for session in self._sessions.values() if not session.get("paused")
        )

    async def finalize_session(self, player_id: str) -> None:
        if player_id not in self._sessions:
            return

        session = self._sessions[player_id]
        duration = session.get("active_duration_sec", 0.0)
        if duration >= self.play_threshold_sec:
            await self._commit_session(session, int(duration), finalized=True)
        elif self._save_attempt is not None:
            await self._persist(
                self._save_attempt,
                {
                    **session,
                    "duration_sec": int(duration),
                    "outcome": "short_play",
                    "last_seen_at": (
                        session.get("last_active_at") or session["last_seen_at"]
                    ).isoformat(),
                },
            )
        self._sessions.pop(player_id, None)

    @staticmethod
    async def _persist(callback: SaveSessionCallback, payload: dict) -> None:
        try:
            await callback(payload)
        except PlaybackPersistenceError:
            raise
        except Exception as exc:
            raise PlaybackPersistenceError("Playback persistence failed") from exc

    async def _commit_session(
        self,
        session: dict,
        duration_sec: int,
        *,
        finalized: bool,
    ) -> None:
        # Anchor played_at to active listening, excluding any trailing idle gap.
        last_active = session.get("last_active_at") or session["last_seen_at"]
        payload = {
            **session,
            "duration_sec": duration_sec,
            "last_seen_at": last_active.isoformat(),
            "finalized": finalized,
            "finalized_at": last_active.isoformat() if finalized else None,
            "checkpointed_at": last_active.isoformat(),
        }
        await self._persist(self._save_session, payload)

    async def _maybe_commit_active_session(self, player_id: str) -> None:
        session = self._sessions.get(player_id)
        if not session:
            return

        duration = session.get("active_duration_sec", 0.0)
        if duration < self.play_threshold_sec:
            return
        last_checkpoint = session.get("last_checkpoint_duration_sec")
        if session.get("committed") and (
            last_checkpoint is not None
            and duration - last_checkpoint < self.checkpoint_interval_sec
        ):
            return

        await self._commit_session(session, int(duration), finalized=False)
        # Mark the checkpoint only after persistence so failures remain retryable.
        session["committed"] = True
        session["last_checkpoint_duration_sec"] = duration

    async def finalize_all(self) -> None:
        errors: list[Exception] = []
        for player_id in list(self._sessions.keys()):
            try:
                await self.finalize_session(player_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise SessionFinalizationError(
                f"Failed to finalize {len(errors)} playback sessions"
            )

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
            "artist_id": entry.get("artistId"),
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

    def _has_playback_report(self, entry: dict) -> bool:
        return self.supports_playback_report and entry.get("state") is not None

    def _is_playing(self, entry: dict) -> bool:
        if self.supports_playback_report:
            state = entry.get("state")
            if isinstance(state, str):
                return state.lower() in {"starting", "playing"}
        return bool(entry.get("isPlaying", True))

    def _is_terminal_state(self, entry: dict) -> bool:
        if not self.supports_playback_report:
            return False
        state = entry.get("state")
        return isinstance(state, str) and state.lower() in TERMINAL_PLAYBACK_STATES

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
        # Paused players stay out of this set so repeated pause polls still expire.
        actively_seen_player_ids: set[str] = set()

        for entry in self._normalize_entries(entries):
            player_id_raw = entry.get("playerId")
            if player_id_raw is None:
                continue

            player_id = str(player_id_raw)
            track_id = entry.get("id")

            if self._is_terminal_state(entry):
                # stopped/expired end the session at once; do not linger in
                # the pause grace window after playback actually ended.
                await self.finalize_session(player_id)
                continue

            is_playing = self._is_playing(entry)

            if not is_playing:
                # A pause updates visibility without advancing listen duration.
                if (
                    player_id in self._sessions
                    and self._sessions[player_id]["track_id"] == track_id
                ):
                    session = self._sessions[player_id]
                    session["last_seen_at"] = current_time
                    session["paused"] = True
                continue

            actively_seen_player_ids.add(player_id)

            if player_id in self._sessions:
                if self._sessions[player_id]["track_id"] == track_id:
                    session = self._sessions[player_id]
                    if session.get("paused"):
                        # Resume from this timestamp so the idle gap is excluded.
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
                    await self.finalize_session(player_id)
                    self._sessions[player_id] = self._session_from_entry(entry, current_time)
            else:
                self._sessions[player_id] = self._session_from_entry(entry, current_time)

        stale_players: list[str] = []
        for pid, session in self._sessions.items():
            if pid in actively_seen_player_ids:
                continue
            last_active = session.get("last_active_at") or session["last_seen_at"]
            time_since_active = (current_time - last_active).total_seconds()
            if time_since_active < self.pause_grace_sec:
                # Keep the session during grace; the next active poll starts a new interval.
                session["paused"] = True
                session["last_seen_at"] = current_time
                continue
            stale_players.append(pid)

        for pid in stale_players:
            if pid not in self._sessions:
                continue
            await self.finalize_session(pid)
