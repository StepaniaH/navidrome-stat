"""Polling collectors and their playback-session trackers.

One collector runs per enabled Navidrome source. Desired state is derived
from saved servers, falling back to the legacy environment connection while
no server entries exist, and reconciled onto the collector manager.
"""

import asyncio
import logging
from datetime import datetime, timezone

import anyio

from src.client import NavidromeClient
from src.collector_manager import CollectorManager as BaseCollectorManager
from src.config import env_int
from src.database import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, list_servers, ping_db
from src.runtime_state import runtime_state
from src.sessions import PlaybackPersistenceError, PlaybackSessionTracker
from src.source_config import has_full_config, resolve_effective_source_config
from src.stats_service import exception_kind, stats_service

logger = logging.getLogger(__name__)


class CollectorApplyError(RuntimeError):
    """A saved collector configuration could not be applied at runtime."""

POLL_INTERVAL = env_int("POLL_INTERVAL", default=10, min_value=5, max_value=300)
MAX_POLL_BACKOFF_SEC = env_int(
    "MAX_POLL_BACKOFF_SEC", default=60, min_value=1, max_value=3600
)
PLAY_THRESHOLD_SEC = env_int(
    "PLAY_THRESHOLD_SEC", default=30, min_value=1, max_value=3600
)
PAUSE_GRACE_SEC = env_int("PAUSE_GRACE_SEC", default=30, min_value=0, max_value=3600)
CHECKPOINT_INTERVAL_SEC = env_int(
    "CHECKPOINT_INTERVAL_SEC", default=60, min_value=10, max_value=3600
)


def _record_source_session(session: dict, source_id: str, source_name: str) -> None:
    return stats_service.record_session(
        {**session, "source_id": source_id, "source_name": source_name}
    )


session_tracker = PlaybackSessionTracker(
    stats_service.record_session,
    play_threshold_sec=PLAY_THRESHOLD_SEC,
    pause_grace_sec=PAUSE_GRACE_SEC,
    checkpoint_interval_sec=CHECKPOINT_INTERVAL_SEC,
    save_attempt=stats_service.record_attempt,
)

# Trackers created for saved server connections; empty when only the legacy
# environment fallback is in use.
_runtime_trackers: list[PlaybackSessionTracker] = []


def _live_trackers() -> tuple[PlaybackSessionTracker, ...]:
    return tuple(_runtime_trackers) or (session_tracker,)


def active_now_playing() -> list[dict]:
    return [
        session
        for tracker in _live_trackers()
        for session in tracker.now_playing()
    ]


async def polling_loop(client: NavidromeClient):
    await polling_loop_for_tracker(client, session_tracker)


async def polling_loop_for_tracker(client: NavidromeClient, tracker: PlaybackSessionTracker):
    logger.info("Starting polling loop with interval: %s seconds", POLL_INTERVAL)
    consecutive_failures = 0
    try:
        playback_report = await client.supports_playback_report()
    except Exception:
        playback_report = False
    tracker.set_playback_report_supported(playback_report)
    logger.info(
        "OpenSubsonic playback report capability: %s",
        "available" if playback_report else "legacy_fallback",
    )

    while True:
        current_time = datetime.now(timezone.utc)
        sleep_for = POLL_INTERVAL
        try:
            data = await client.get_now_playing()
            response = data.get("subsonic-response", {})
            if response.get("status") != "ok":
                error_info = response.get("error", {})
                error_code_raw = (
                    error_info.get("code") if isinstance(error_info, dict) else None
                )
                try:
                    error_code = int(error_code_raw)
                except (TypeError, ValueError):
                    error_code = None
                runtime_state.record_poll_upstream_error(
                    current_time, error_code, tracker.source_id
                )
                logger.error("Error from Navidrome API (code=%s)", error_code)
                consecutive_failures += 1
                sleep_for = min(
                    POLL_INTERVAL * (2 ** (consecutive_failures - 1)),
                    MAX_POLL_BACKOFF_SEC,
                )
            else:
                entries = NavidromeClient.now_playing_entries(data)
                try:
                    await tracker.process_poll(entries, current_time)
                except PlaybackPersistenceError as exc:
                    logger.error(
                        "Play persistence failed after successful poll (type=%s)",
                        exception_kind(exc),
                    )
                runtime_state.record_poll_success(current_time, tracker.source_id)
                consecutive_failures = 0

        except Exception as exc:
            runtime_state.record_poll_exception(current_time, tracker.source_id)
            logger.error(
                "Polling cycle failed (type=%s)",
                exception_kind(exc),
            )
            consecutive_failures += 1
            sleep_for = min(
                POLL_INTERVAL * (2 ** (consecutive_failures - 1)),
                MAX_POLL_BACKOFF_SEC,
            )

        await asyncio.sleep(sleep_for)


def _tracker_for_server(server: dict) -> PlaybackSessionTracker:
    sid, name = server["id"], server["display_name"]
    return PlaybackSessionTracker(
        lambda session: _record_source_session(session, sid, name),
        play_threshold_sec=PLAY_THRESHOLD_SEC,
        pause_grace_sec=PAUSE_GRACE_SEC,
        save_attempt=lambda attempt: stats_service.record_attempt(
            {**attempt, "source_id": sid, "source_name": name}
        ),
        source_id=sid,
        source_name=name,
        checkpoint_interval_sec=CHECKPOINT_INTERVAL_SEC,
    )


class CollectorManager(BaseCollectorManager):
    """Collector manager bound to the application factories and runtime state."""

    def __init__(self, client_factory, poller, tracker_registry: list):
        super().__init__(
            client_factory,
            poller,
            tracker_registry,
            tracker_factory=_tracker_for_server,
            runtime_state=runtime_state,
        )


collector_manager = CollectorManager(
    lambda **config: NavidromeClient(**config),
    polling_loop_for_tracker,
    _runtime_trackers,
)


async def _desired_collector_configs() -> list[dict]:
    configured = await list_servers()
    if configured:
        return [server for server in configured if server.get("enabled", True)]
    config = await resolve_effective_source_config()
    if not has_full_config(config):
        return []
    return [{
        "id": LEGACY_SOURCE_ID,
        "display_name": LEGACY_SOURCE_NAME,
        **config,
        "enabled": True,
    }]


async def reconcile_collectors() -> None:
    await collector_manager.reconcile(await _desired_collector_configs())


async def _compensate_collector_config_mutation(restore) -> None:
    try:
        await restore()
    except Exception as exc:
        logger.error(
            "Collector configuration rollback failed (type=%s)",
            exception_kind(exc),
        )

    await stats_service.invalidate()
    try:
        await reconcile_collectors()
    except Exception as exc:
        logger.error(
            "Collector reconciliation after rollback failed (type=%s)",
            exception_kind(exc),
        )


async def apply_collector_runtime_or_rollback(restore) -> None:
    try:
        await reconcile_collectors()
    except asyncio.CancelledError:
        # ASGI cancellation is delivered repeatedly inside the request's cancel
        # scope, which would kill the rollback at its first await. Shielding
        # lets the compensation finish before the error propagates.
        with anyio.CancelScope(shield=True):
            await _compensate_collector_config_mutation(restore)
        raise
    except Exception as exc:
        logger.error("Saved collector configuration could not be applied")
        await _compensate_collector_config_mutation(restore)
        raise CollectorApplyError("Saved configuration could not be applied") from exc


async def build_readiness_report() -> dict:
    db_ok = await ping_db()
    collectors = list(runtime_state.collectors.values())
    polling_running = bool(collectors) and all(
        collector.task_alive() for collector in collectors
    )

    if runtime_state.client_initialized:
        polling_status = "running" if polling_running else "stopped"
    else:
        polling_status = "not_started"

    last_states = [collector.last_poll_ok for collector in collectors]
    if last_states and all(state is True for state in last_states):
        upstream_status = "ok"
    elif any(state is False for state in last_states):
        upstream_status = "error"
    else:
        upstream_status = "unknown"

    if not db_ok:
        overall = "not_ready"
    elif runtime_state.client_initialized and not polling_running:
        overall = "not_ready"
    elif upstream_status == "error" or not runtime_state.client_initialized:
        overall = "degraded"
    else:
        overall = "ready"

    seconds_since_poll = None
    poll_times = [
        collector.last_poll_at
        for collector in collectors
        if collector.last_poll_at is not None
    ]
    if poll_times:
        seconds_since_poll = int(
            (datetime.now(timezone.utc) - min(poll_times)).total_seconds()
        )
    healthy_collectors = sum(
        1
        for collector in collectors
        if collector.task_alive() and collector.last_poll_ok is True
    )
    degraded_collectors = sum(
        1
        for collector in collectors
        if not collector.task_alive() or collector.last_poll_ok is False
    )

    return {
        "status": overall,
        "checks": {
            "database": "ok" if db_ok else "error",
            "polling_task": polling_status,
            "upstream": upstream_status,
        },
        "metrics": {
            "poll_success_total": runtime_state.poll_success_count,
            "poll_failure_total": runtime_state.poll_failure_count,
            "save_success_total": runtime_state.save_success_count,
            "save_failure_total": runtime_state.save_failure_count,
            "active_sessions": len(active_now_playing()),
            "seconds_since_last_poll": seconds_since_poll,
            "last_upstream_error_code": runtime_state.last_upstream_error_code,
            "collector_count": len(collectors),
            "healthy_collector_count": healthy_collectors,
            "degraded_collector_count": degraded_collectors,
        },
    }
