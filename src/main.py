import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from src.auth import (
    SESSION_COOKIE_NAME,
    is_auth_enabled,
    is_authorized,
    login_rate_limiter,
    session_cookie_params,
    session_cookie_value,
    verify_login_token,
)
from src.client import NavidromeClient
from src.collector_manager import CollectorManager as BaseCollectorManager
from src.config import env_flag, env_int
from src.dashboard_cache import dashboard_snapshot_cache
from src.database import (
    LEGACY_SOURCE_ID,
    LEGACY_SOURCE_NAME,
    SCHEMA_VERSION,
    delete_server,
    get_daily_stats,
    get_hourly_stats,
    get_playback_history,
    get_player_stats,
    get_server,
    get_server_stats,
    get_short_play_stats,
    get_source_stats,
    get_summary,
    get_time_bucket_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    get_weekday_hour_stats,
    init_db,
    list_servers,
    ping_db,
    resolve_timezone,
    save_play_attempt,
    save_play_session,
    save_server,
)
from src.metrics import format_prometheus_metrics
from src.privacy_ops import (
    IMPORT_MAX_PAYLOAD_BYTES,
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    apply_retention_purge,
    delete_user_data,
    export_user_data,
    get_retention_days,
    get_storage_stats,
    import_user_data,
    list_users,
    preview_delete_user,
    preview_retention_purge,
    set_retention_days,
    validate_retention_days,
)
from src.request_limits import PrivacyImportBodyLimitMiddleware
from src.runtime_state import runtime_state
from src.schemas import (
    DAILY_DAYS_DEFAULT,
    DAILY_DAYS_MAX,
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    HISTORY_LIMIT_MIN,
    RANKING_METRIC_DEFAULT,
    RANKING_METRIC_VALIDATION_ERROR,
    RANKING_METRICS,
    STATS_DAYS_ALL,
    STATS_DAYS_DEFAULT,
    STATS_DAYS_MAX,
    STATS_DAYS_MIN,
    TIMEZONE_DEFAULT,
    TIMEZONE_VALIDATION_ERROR,
    TOP_LIMIT_DEFAULT,
    TOP_LIMIT_MAX,
    TOP_LIMIT_MIN,
    AboutResponse,
    AuthStatusResponse,
    ConfirmRequest,
    DailyStat,
    DashboardSnapshot,
    HealthLiveResponse,
    HistoryItem,
    HourlyStat,
    LoginRequest,
    NowPlayingItem,
    PlayerStat,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
    ReadinessResponse,
    RetentionApplyResponse,
    RetentionPreviewResponse,
    ServerRequest,
    ServerResponse,
    ServerStat,
    ServerTestResponse,
    ShortPlayStats,
    SourceConfigResponse,
    SourceConfigUpdate,
    SourceStat,
    SourceTestRequest,
    SourceTestResponse,
    StorageStatsResponse,
    SummaryStat,
    TopAlbumItem,
    TopArtistItem,
    TranscodingStat,
    UserDeletePreviewResponse,
    UserDeleteResponse,
    UserImportRequest,
    UserImportResponse,
    UserSummary,
    WeekdayHourStat,
)
from src.sessions import PlaybackSessionTracker
from src.source_config import (
    get_saved_source_config,
    has_full_config,
    redacted_view,
    resolve_effective_source_config,
    resolve_source_config,
    set_saved_source_config,
    validate_source_url,
)
from src.version import APP_VERSION, LICENSE, PROJECT_NAME, PROJECT_URL

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

POLL_INTERVAL = env_int("POLL_INTERVAL", default=10, min_value=5, max_value=300)
MAX_POLL_BACKOFF_SEC = env_int("MAX_POLL_BACKOFF_SEC", default=60, min_value=1, max_value=3600)
RETENTION_MAINTENANCE_SEC = env_int(
    "RETENTION_MAINTENANCE_SEC", default=86400, min_value=60, max_value=604800
)
PLAY_THRESHOLD_SEC = env_int(
    "PLAY_THRESHOLD_SEC", default=30, min_value=1, max_value=3600
)
PAUSE_GRACE_SEC = env_int("PAUSE_GRACE_SEC", default=30, min_value=0, max_value=3600)
SAVE_RETRY_ATTEMPTS = env_int(
    "SAVE_RETRY_ATTEMPTS", default=3, min_value=1, max_value=10
)
CHECKPOINT_INTERVAL_SEC = env_int(
    "CHECKPOINT_INTERVAL_SEC", default=60, min_value=10, max_value=3600
)
OPENAPI_ENABLED = env_flag("OPENAPI_ENABLED", default=True)


def _exception_kind(exc: Exception) -> str:
    """Return a non-sensitive error category suitable for application logs."""
    return type(exc).__name__


async def _retry_save(operation, *, kind: str) -> None:
    for attempt in range(1, SAVE_RETRY_ATTEMPTS + 1):
        try:
            await operation()
            return
        except Exception as exc:
            if attempt >= SAVE_RETRY_ATTEMPTS:
                logger.error(
                    "%s persistence failed (type=%s, attempts=%s)",
                    kind,
                    _exception_kind(exc),
                    attempt,
                )
                raise
            logger.warning(
                "%s persistence retry (type=%s, attempt=%s)",
                kind,
                _exception_kind(exc),
                attempt,
            )
            await asyncio.sleep(0.05 * (2 ** (attempt - 1)))


async def _save_play_session_with_logging(session: dict) -> None:
    try:
        await _retry_save(lambda: save_play_session(session), kind="play_session")
        runtime_state.record_save_success()
        await dashboard_snapshot_cache.invalidate()
        logger.debug(
            "Recorded play session (duration=%ss)",
            session["duration_sec"],
        )
    except Exception:
        runtime_state.record_save_failure()
        raise


async def _save_play_attempt_with_logging(attempt: dict) -> None:
    await _retry_save(lambda: save_play_attempt(attempt), kind="play_attempt")
    await dashboard_snapshot_cache.invalidate()


def _attempt_callback(source_id: str, source_name: str):
    async def save(attempt: dict) -> None:
        await _save_play_attempt_with_logging({
            **attempt, "source_id": source_id, "source_name": source_name,
        })
    return save


session_tracker = PlaybackSessionTracker(
    _save_play_session_with_logging,
    play_threshold_sec=PLAY_THRESHOLD_SEC,
    pause_grace_sec=PAUSE_GRACE_SEC,
    checkpoint_interval_sec=CHECKPOINT_INTERVAL_SEC,
    save_attempt=_save_play_attempt_with_logging,
)
_runtime_trackers: list[PlaybackSessionTracker] = []


def _live_trackers() -> tuple[PlaybackSessionTracker, ...]:
    trackers = tuple(_runtime_trackers)
    return trackers or (session_tracker,)


def _active_sessions() -> list[dict]:
    return [
        session
        for tracker in _live_trackers()
        for session in tuple(tracker.active_sessions.values())
        if not session.get("paused")
    ]


async def finalize_session(player_id: str):
    """Calculates session duration and saves to DB if threshold is met."""
    await session_tracker.finalize_session(player_id)


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
                except Exception as exc:
                    logger.error(
                        "Play persistence failed after successful poll (type=%s)",
                        _exception_kind(exc),
                    )
                runtime_state.record_poll_success(current_time, tracker.source_id)
                consecutive_failures = 0

        except Exception as exc:
            runtime_state.record_poll_exception(current_time, tracker.source_id)
            logger.error(
                "Polling cycle failed (type=%s)",
                _exception_kind(exc),
            )
            consecutive_failures += 1
            sleep_for = min(
                POLL_INTERVAL * (2 ** (consecutive_failures - 1)),
                MAX_POLL_BACKOFF_SEC,
            )

        await asyncio.sleep(sleep_for)


def _tracker_for_server(server: dict) -> PlaybackSessionTracker:
    return PlaybackSessionTracker(
        lambda session, sid=server["id"], name=server["display_name"]: _save_play_session_with_logging(
            {**session, "source_id": sid, "source_name": name}
        ),
        play_threshold_sec=PLAY_THRESHOLD_SEC,
        pause_grace_sec=PAUSE_GRACE_SEC,
        save_attempt=_attempt_callback(server["id"], server["display_name"]),
        source_id=server["id"],
        source_name=server["display_name"],
        checkpoint_interval_sec=CHECKPOINT_INTERVAL_SEC,
    )


class CollectorManager(BaseCollectorManager):
    """Application-configured collector manager; kept import-compatible."""

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


async def retention_maintenance_loop():
    """Periodically purge play history older than the configured retention window."""
    while True:
        await asyncio.sleep(RETENTION_MAINTENANCE_SEC)
        try:
            result = await apply_retention_purge()
            if result["deleted"]:
                await dashboard_snapshot_cache.invalidate()
                logger.info("Retention purge removed %s records", result["deleted"])
        except Exception as exc:
            logger.error(
                "Retention maintenance failed (type=%s)",
                _exception_kind(exc),
            )


async def run_startup_retention_purge():
    try:
        result = await apply_retention_purge()
        if result["deleted"]:
            await dashboard_snapshot_cache.invalidate()
            logger.info("Startup retention purge removed %s records", result["deleted"])
    except Exception as exc:
        logger.error(
            "Startup retention purge failed (type=%s)",
            _exception_kind(exc),
        )


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
            "active_sessions": len(_active_sessions()),
            "seconds_since_last_poll": seconds_since_poll,
            "last_upstream_error_code": runtime_state.last_upstream_error_code,
            "collector_count": len(collectors),
            "healthy_collector_count": healthy_collectors,
            "degraded_collector_count": degraded_collectors,
        },
    }


async def _query_stats(fetch):
    try:
        return await fetch()
    except Exception:
        logger.error("Database query failed")
        raise HTTPException(status_code=503, detail="Stats temporarily unavailable")


async def _apply_runtime_config(operation) -> None:
    try:
        await operation()
    except Exception:
        logger.error("Saved collector configuration could not be applied")
        raise HTTPException(
            status_code=503,
            detail="Saved configuration could not be applied",
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


async def _reconcile_collectors() -> None:
    await collector_manager.reconcile(await _desired_collector_configs())


def _validate_stats_days(days: int) -> int:
    """Validate the unified ``days`` window query parameter.

    Allowed values are ``STATS_DAYS_ALL`` (0, all history) and finite windows
    in ``[STATS_DAYS_MIN, STATS_DAYS_MAX]`` (7..90). Any other value produces
    HTTP 422. The endpoint-level ``Query`` already enforces ``ge=0, le=90`` so
    this function focuses on the finite bound gap (1..6).
    """
    if days == STATS_DAYS_ALL:
        return STATS_DAYS_ALL
    if STATS_DAYS_MIN <= days <= STATS_DAYS_MAX:
        return days
    raise HTTPException(
        status_code=422,
        detail=f"days must be {STATS_DAYS_ALL} (all history) or between "
        f"{STATS_DAYS_MIN} and {STATS_DAYS_MAX}",
    )


def _validate_stats_timezone(timezone_name: str) -> str:
    """Validate the optional ``timezone`` query parameter.

    Resolved against Python stdlib ``zoneinfo.ZoneInfo`` (no new dependency).
    Invalid names raise HTTP 422. The validated value is only used for Python
    date/hour/weekday bucket math and UTC cutoff computation in ``database.py``;
    it is never string-interpolated into SQL.
    """
    try:
        resolve_timezone(timezone_name)
    except ValueError:
        raise HTTPException(status_code=422, detail=TIMEZONE_VALIDATION_ERROR)
    return timezone_name


def _validate_ranking_metric(metric: str) -> str:
    """Validate the ranking ``metric`` query parameter for top artists/albums.

    Accepted values are defined by ``src.schemas.RANKING_METRICS``. Any other
    value produces HTTP 422 via FastAPI's request validation surface (the
    check happens here so the error body is uniform with the other stats
    validation errors).
    """
    if metric not in RANKING_METRICS:
        raise HTTPException(status_code=422, detail=RANKING_METRIC_VALIDATION_ERROR)
    return metric


def _source_kwargs(source_id: str | None) -> dict:
    return {"source_id": source_id} if source_id else {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    await run_startup_retention_purge()

    retention_task = None
    try:
        await _reconcile_collectors()
        retention_task = asyncio.create_task(retention_maintenance_loop())
    except Exception as exc:
        runtime_state.client_initialized = False
        logger.error(
            "Collector initialization failed (type=%s)",
            _exception_kind(exc),
        )

    yield

    logger.info("Shutting down background task...")
    if retention_task is not None:
        retention_task.cancel()
    await collector_manager.stop_all()
    if retention_task is not None:
        try:
            await retention_task
        except asyncio.CancelledError:
            logger.info("Retention maintenance task cancelled.")
    runtime_state.polling_task = None


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if OPENAPI_ENABLED else None,
    redoc_url="/redoc" if OPENAPI_ENABLED else None,
    openapi_url="/openapi.json" if OPENAPI_ENABLED else None,
)

ALWAYS_AUTH_EXEMPT_PATHS = frozenset(
    {"/health", "/health/ready", "/api/auth/login", "/api/auth/status"}
)


def _metrics_require_auth() -> bool:
    """Return True when /metrics should follow STATS_API_TOKEN."""
    return env_flag("STATS_METRICS_AUTH", default=False)


def _is_auth_exempt(path: str) -> bool:
    if path in ALWAYS_AUTH_EXEMPT_PATHS:
        return True
    if path == "/metrics":
        return not _metrics_require_auth()
    return False


def _with_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    return _with_security_headers(response)


@app.middleware("http")
async def stats_auth_middleware(request: Request, call_next):
    if not is_auth_enabled():
        return await call_next(request)

    path = request.url.path
    if _is_auth_exempt(path):
        return await call_next(request)
    if is_authorized(request):
        return await call_next(request)
    if path in ("/docs", "/redoc", "/openapi.json"):
        if not OPENAPI_ENABLED:
            return await call_next(request)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    if path.startswith("/api/") or path == "/metrics":
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


app.add_middleware(
    PrivacyImportBodyLimitMiddleware,
    max_bytes=IMPORT_MAX_PAYLOAD_BYTES,
    apply_headers=_with_security_headers,
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Dashboard not found"}


@app.get("/settings")
async def settings_page():
    settings_file = os.path.join(STATIC_DIR, "settings.html")
    if os.path.exists(settings_file):
        return FileResponse(settings_file)
    raise HTTPException(status_code=404, detail="Settings page not found")


@app.get("/health", response_model=HealthLiveResponse)
async def health():
    """Liveness probe: process is running."""
    return {"status": "ok"}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """Reports whether dashboard/API access requires authentication."""
    return {"auth_required": is_auth_enabled()}


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    """Creates a browser session when STATS_API_TOKEN is configured."""
    if not is_auth_enabled():
        raise HTTPException(status_code=404, detail="Authentication is not enabled")
    retry_after = login_rate_limiter.check(request)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    if not verify_login_token(body.token):
        login_rate_limiter.record_failure(request)
        raise HTTPException(status_code=401, detail="Unauthorized")
    login_rate_limiter.clear(request)
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_cookie_value(),
        max_age=60 * 60 * 24 * 30,
        **session_cookie_params(),
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout():
    """Clears the browser session cookie."""
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME, **session_cookie_params())
    return response


@app.get("/health/ready", response_model=ReadinessResponse)
async def health_ready():
    """Readiness probe: database and background collector state."""
    report = await build_readiness_report()
    status_code = 200 if report["status"] != "not_ready" else 503
    return JSONResponse(content=report, status_code=status_code)


@app.get("/metrics")
async def metrics():
    """Prometheus exposition endpoint; anonymous unless STATS_METRICS_AUTH is on."""
    active = len(_active_sessions())
    return PlainTextResponse(
        content=format_prometheus_metrics(active_sessions=active),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


async def _build_dashboard_snapshot(
    *,
    days: int,
    timezone_name: str,
    metric: str,
    source_id: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    source_kwargs = _source_kwargs(source_id)
    window_kwargs = {
        "start_date": start_date,
        "end_date": end_date,
    }
    (
        summary,
        players,
        transcoding,
        time_buckets,
        history,
        servers,
        available_servers,
        top_artists,
        top_albums,
    ) = await asyncio.gather(
        get_summary(
            days=days,
            timezone_name=timezone_name,
            **source_kwargs,
            **window_kwargs,
        ),
        get_player_stats(
            days=days,
            timezone_name=timezone_name,
            **source_kwargs,
            **window_kwargs,
        ),
        get_transcoding_stats(
            days=days,
            timezone_name=timezone_name,
            **source_kwargs,
            **window_kwargs,
        ),
        get_time_bucket_stats(
            days=days,
            timezone_name=timezone_name,
            **source_kwargs,
            **window_kwargs,
        ),
        get_playback_history(
            limit=HISTORY_LIMIT_DEFAULT,
            days=days,
            timezone_name=timezone_name,
            **source_kwargs,
            **window_kwargs,
        ),
        get_server_stats(
            days=days,
            timezone_name=timezone_name,
            source_id=source_id,
            **window_kwargs,
        ),
        list_servers(),
        get_top_artists(
            limit=TOP_LIMIT_DEFAULT,
            days=days,
            timezone_name=timezone_name,
            metric=metric,
            **source_kwargs,
            **window_kwargs,
        ),
        get_top_albums(
            limit=TOP_LIMIT_DEFAULT,
            days=days,
            timezone_name=timezone_name,
            metric=metric,
            **source_kwargs,
            **window_kwargs,
        ),
    )
    return {
        "summary": summary,
        "players": players,
        "transcoding": transcoding,
        "hourly": time_buckets["hourly"],
        "daily": time_buckets["daily"],
        "heatmap": time_buckets["heatmap"],
        "history": history,
        "servers": servers,
        "available_servers": [
            {"id": server["id"], "display_name": server["display_name"]}
            for server in available_servers
        ],
        "top_artists": top_artists,
        "top_albums": top_albums,
    }


@app.get("/api/stats/dashboard", response_model=DashboardSnapshot)
async def api_dashboard_snapshot(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Return one cached historical payload; now-playing remains real-time."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    ranking = _validate_ranking_metric(metric)
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be provided together",
        )
    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date must not be after end_date",
            )
        if (end_date - start_date).days + 1 > 366:
            raise HTTPException(
                status_code=422,
                detail="custom date range must not exceed 366 days",
            )
    key = (window, tz, ranking, source_id, start_date, end_date)
    return await _query_stats(
        lambda: dashboard_snapshot_cache.get_or_create(
            key,
            lambda: _build_dashboard_snapshot(
                days=window,
                timezone_name=tz,
                metric=ranking,
                source_id=source_id,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    )


@app.get("/api/stats/summary", response_model=SummaryStat)
async def api_summary_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for aggregate listening statistics over the selected window.

    ``days=0`` (default) means all history; ``days=7..90`` selects a finite
    rolling window with current-vs-previous comparison metrics. See
    ``src.database.get_summary`` for the exact semantics.

    ``timezone`` (optional, default ``UTC``) is validated against
    ``zoneinfo.ZoneInfo`` and controls date bucket boundaries and finite-window
    UTC cutoffs only; timestamps remain stored as UTC ISO strings.
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_summary(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/players", response_model=list[PlayerStat])
async def api_player_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for player usage distribution over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_player_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/transcoding", response_model=list[TranscodingStat])
async def api_transcoding_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for transcoding ratio over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_transcoding_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/short-plays", response_model=ShortPlayStats)
async def api_short_play_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return short-play rate; it does not claim intentional skips."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_short_play_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/sources", response_model=list[SourceStat])
async def api_source_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return formal play counts grouped by provenance source."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_source_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/servers", response_model=list[ServerStat])
async def api_server_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return formal play totals grouped by configured server identity."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(lambda: get_server_stats(days=window, timezone_name=tz, source_id=source_id))


@app.get("/api/stats/hourly", response_model=list[HourlyStat])
async def api_hourly_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for play counts grouped by local hour of day (0-23) over the
    selected window. Hours are taken in the requested timezone (default UTC).
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_hourly_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/heatmap", response_model=list[WeekdayHourStat])
async def api_weekday_hour_stats(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for the 7x24 weekday x hour heatmap over the selected window.

    Returns every cell (168 rows) of ``{weekday: 0..6, hour: 0..23, count: int}``,
    zero-filled. Weekday convention is Python's ``date.weekday()``: 0=Monday
    ... 6=Sunday. Hours are taken in the requested timezone (default ``UTC``).
    Default window is ``STATS_DAYS_DEFAULT`` (30 days); ``days=0`` selects all
    history. Finite windows must be ``0`` or ``7..90`` (1..6 returns 422 as on
    the other historical endpoints).
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_weekday_hour_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/daily", response_model=list[DailyStat])
async def api_daily_stats(
    days: int = Query(
        default=DAILY_DAYS_DEFAULT,
        ge=0,
        le=DAILY_DAYS_MAX,
    ),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for play counts per local day over the last ``days`` days.

    Backward compatible default is 30 days; ``days=0`` selects all history.
    Finite windows must be 7-90 (daily does not allow intermediate values).
    Every calendar date in the window (or all-history span) is included with
    at least count 0, ordered ascending. Date bucket boundaries use the
    requested timezone (default ``UTC``); timestamps are stored as UTC ISO
    strings.
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_daily_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@app.get("/api/stats/top-artists", response_model=list[TopArtistItem])
async def api_top_artists(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for top artists ranked by ``metric`` over the selected window.

    ``metric=plays`` (default) preserves the historical ``count DESC``
    ordering; ``metric=listen_time`` ranks by ``total_listen_sec``. Both
    responses keep ``count`` for backward compatibility and add
    ``total_listen_sec`` plus ``value`` (the active ranking key). Invalid
    metric values return 422. ``days``/``timezone`` filtering matches the
    other historical endpoints; timezone is not needed for totals but is
    accepted to keep the API contract consistent.
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    m = _validate_ranking_metric(metric)
    return await _query_stats(
        lambda: get_top_artists(
            limit=limit,
            days=window,
            timezone_name=tz,
            metric=m,
            **_source_kwargs(source_id),
        )
    )


@app.get("/api/stats/top-albums", response_model=list[TopAlbumItem])
async def api_top_albums(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for top albums ranked by ``metric`` over the selected window.

    Same contract as ``/api/stats/top-artists`` with ``album`` in place of
    ``artist``.
    """
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    m = _validate_ranking_metric(metric)
    return await _query_stats(
        lambda: get_top_albums(
            limit=limit,
            days=window,
            timezone_name=tz,
            metric=m,
            **_source_kwargs(source_id),
        )
    )


@app.get("/api/stats/now-playing", response_model=list[NowPlayingItem])
async def api_now_playing(
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for currently active playback sessions (in-memory, no DB access)."""
    try:
        now = datetime.now(timezone.utc)
        items: list[NowPlayingItem] = []
        for session in _active_sessions():
            if source_id and session.get("source_id") != source_id:
                continue
            first_seen_at = session.get("first_seen_at")
            seconds_elapsed = 0
            if first_seen_at is not None:
                seconds_elapsed = int((now - first_seen_at).total_seconds())
                if seconds_elapsed < 0:
                    seconds_elapsed = 0
            items.append(
                NowPlayingItem(
                    username=session.get("username"),
                    title=session.get("title"),
                    artist=session.get("artist"),
                    client_name=session.get("client_name"),
                    seconds_elapsed=seconds_elapsed,
                    source_name=session.get("source_name"),
                )
            )
        return items
    except Exception:
        logger.error("Now playing query failed")
        raise HTTPException(status_code=503, detail="Stats temporarily unavailable")


@app.get("/api/stats/history", response_model=list[HistoryItem])
async def api_playback_history(
    limit: int = Query(
        default=HISTORY_LIMIT_DEFAULT,
        ge=HISTORY_LIMIT_MIN,
        le=HISTORY_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for recent playback history over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_playback_history(
            limit=limit,
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
        )
    )


def _privacy_settings_response(days: int | None) -> PrivacySettingsResponse:
    return PrivacySettingsResponse(retention_days=days, permanent=days is None)


def _validated_username(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="username is required")
    if len(normalized) > 255:
        raise HTTPException(status_code=422, detail="username is too long")
    return normalized


@app.get("/api/privacy/settings", response_model=PrivacySettingsResponse)
async def api_privacy_settings():
    days = await get_retention_days()
    return _privacy_settings_response(days)


@app.put("/api/privacy/settings", response_model=PrivacySettingsResponse)
async def api_update_privacy_settings(body: PrivacySettingsUpdate):
    try:
        validate_retention_days(body.retention_days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await set_retention_days(body.retention_days)
    return _privacy_settings_response(body.retention_days)


@app.get("/api/privacy/storage", response_model=StorageStatsResponse)
async def api_privacy_storage():
    return await get_storage_stats()


@app.get("/api/privacy/retention/preview", response_model=RetentionPreviewResponse)
async def api_retention_preview(
    days: int | None = Query(default=None, ge=RETENTION_MIN_DAYS, le=RETENTION_MAX_DAYS),
):
    try:
        preview = await preview_retention_purge(days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return preview


@app.post("/api/privacy/retention/apply", response_model=RetentionApplyResponse)
async def api_retention_apply(body: ConfirmRequest):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to delete data")
    try:
        result = await apply_retention_purge()
        if result["deleted"]:
            await dashboard_snapshot_cache.invalidate()
        return result
    except Exception as exc:
        logger.error("Retention apply failed")
        raise HTTPException(status_code=503, detail="Retention operation failed") from exc


@app.get("/api/privacy/users", response_model=list[UserSummary])
async def api_privacy_users():
    users = await list_users()
    return users


@app.get("/api/privacy/users/{username}/export")
async def api_export_user(username: str):
    normalized = _validated_username(username)
    try:
        payload = await export_user_data(normalized)
    except Exception as exc:
        logger.error("User export failed")
        raise HTTPException(status_code=503, detail="Export failed") from exc
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="navidrome-stat-export.json"'
        },
    )


@app.post("/api/privacy/users/{username}/import", response_model=UserImportResponse)
async def api_import_user(username: str, body: UserImportRequest):
    normalized = _validated_username(username)
    try:
        result = await import_user_data(
            normalized,
            body.payload,
            merge=body.merge,
        )
        if result["imported"] or result.get("attempts_imported", 0):
            await dashboard_snapshot_cache.invalidate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("User import failed")
        raise HTTPException(status_code=503, detail="Import failed") from exc
    return UserImportResponse(
        imported=result["imported"],
        attempts_imported=result.get("attempts_imported", 0),
        merge=body.merge,
    )


@app.get(
    "/api/privacy/users/{username}/delete/preview",
    response_model=UserDeletePreviewResponse,
)
async def api_delete_user_preview(username: str):
    return await preview_delete_user(_validated_username(username))


@app.post("/api/privacy/users/{username}/delete", response_model=UserDeleteResponse)
async def api_delete_user(username: str, body: ConfirmRequest):
    normalized = _validated_username(username)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to delete data")
    try:
        result = await delete_user_data(normalized)
        if result["deleted"]:
            await dashboard_snapshot_cache.invalidate()
        return result
    except Exception as exc:
        logger.error("User delete failed")
        raise HTTPException(status_code=503, detail="Delete failed") from exc


@app.get("/api/source/config", response_model=SourceConfigResponse)
async def api_source_config_get():
    """Return non-sensitive view of the effective source config (env > saved).

    Never returns the password; only reports whether one is configured.
    """
    saved = await get_saved_source_config()
    config = resolve_source_config(overrides=None, saved=saved)
    view = redacted_view(config)
    return SourceConfigResponse(**view)


@app.put("/api/source/config", response_model=SourceConfigResponse)
async def api_source_config_put(body: SourceConfigUpdate):
    """Persist GUI fallback source config. Env vars keep priority at runtime.

    The password only changes when a non-empty value is supplied; the request
    value is never echoed back. URLs are validated to http/https.
    """
    if body.url is not None:
        try:
            body.url = validate_source_url(body.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.username is not None and not body.username.strip():
        raise HTTPException(status_code=422, detail="username must not be empty")

    saved = await get_saved_source_config()
    new_url = body.url if body.url is not None else saved.get("url")
    new_user = body.username if body.username is not None else saved.get("user")
    if not new_url or not new_user:
        raise HTTPException(status_code=422, detail="url and username are required")

    try:
        await set_saved_source_config(
            url=new_url,
            user=new_user,
            password=body.password,
        )
    except Exception as exc:
        logger.error("Source config persist failed")
        raise HTTPException(status_code=503, detail="Failed to save source config") from exc

    updated = await get_saved_source_config()
    config = resolve_source_config(overrides=None, saved=updated)
    await _apply_runtime_config(_reconcile_collectors)
    view = redacted_view(config)
    return SourceConfigResponse(**view)


@app.post("/api/source/test", response_model=SourceTestResponse)
async def api_source_test(body: SourceTestRequest):
    """Test connectivity with supplied/current settings without persisting.

    Returns only generic success/failure; never echoes upstream responses,
    credentials, or passwords.
    """
    saved = await get_saved_source_config()
    overrides = {
        "url": body.url,
        "user": body.username,
        "password": body.password,
    }
    config = resolve_source_config(overrides=overrides, saved=saved)
    if not has_full_config(config):
        return SourceTestResponse(ok=False, message="配置不完整，缺少 URL、用户名或密码")

    test_client = NavidromeClient(
        url=config["url"],
        user=config["user"],
        password=config["password"],
    )
    try:
        data = await test_client.get_now_playing()
        if not NavidromeClient.response_is_ok(data):
            return SourceTestResponse(ok=False, message="上游拒绝连接或返回错误")
    except Exception:
        return SourceTestResponse(ok=False, message="无法连接到上游 Navidrome")
    finally:
        try:
            await test_client.close()
        except Exception:
            logger.error("Failed to close test NavidromeClient")
    return SourceTestResponse(ok=True, message="连接成功")


def _server_view(server: dict) -> ServerResponse:
    snapshot = runtime_state.collector_snapshot(server["id"])
    seconds_since_last_poll = None
    if snapshot["last_poll_at"] is not None:
        seconds_since_last_poll = max(
            0,
            int(
                (
                    datetime.now(timezone.utc) - snapshot["last_poll_at"]
                ).total_seconds()
            ),
        )
    return ServerResponse(
        id=server["id"], display_name=server["display_name"], url=server["url"],
        username=server["username"], password_configured=bool(server.get("password")),
        enabled=bool(server.get("enabled", True)),
        runtime_status=snapshot["status"],
        last_poll_ok=snapshot["last_poll_ok"],
        seconds_since_last_poll=seconds_since_last_poll,
    )


@app.get("/api/servers", response_model=list[ServerResponse])
async def api_servers_get():
    return [_server_view(server) for server in await list_servers()]


@app.post("/api/servers", response_model=ServerResponse)
async def api_servers_create(body: ServerRequest):
    if not body.display_name.strip() or not body.username.strip():
        raise HTTPException(status_code=422, detail="display_name and username are required")
    try:
        url = validate_source_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not body.password:
        raise HTTPException(status_code=422, detail="password is required")
    server = {"id": uuid.uuid4().hex, "display_name": body.display_name.strip(), "url": url,
              "username": body.username.strip(), "password": body.password, "enabled": body.enabled}
    await save_server(server)
    await dashboard_snapshot_cache.invalidate()
    await _apply_runtime_config(_reconcile_collectors)
    return _server_view(server)


@app.put("/api/servers/{server_id}", response_model=ServerResponse)
async def api_servers_update(server_id: str, body: ServerRequest):
    existing = await get_server(server_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Server not found")
    if not body.display_name.strip() or not body.username.strip():
        raise HTTPException(
            status_code=422,
            detail="display_name and username are required",
        )
    try:
        url = validate_source_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    server = {"id": server_id, "display_name": body.display_name.strip(), "url": url,
              "username": body.username.strip(), "password": body.password or existing["password"],
              "enabled": body.enabled}
    await save_server(server)
    await dashboard_snapshot_cache.invalidate()
    await _apply_runtime_config(_reconcile_collectors)
    return _server_view(server)


@app.delete("/api/servers/{server_id}")
async def api_servers_delete(server_id: str):
    if not await delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    await dashboard_snapshot_cache.invalidate()
    await _apply_runtime_config(_reconcile_collectors)
    return {"status": "ok"}


@app.post("/api/servers/{server_id}/test", response_model=ServerTestResponse)
async def api_servers_test(server_id: str, body: ServerRequest | None = None):
    server = await get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    config = body or ServerRequest(
        display_name=server["display_name"],
        url=server["url"],
        username=server["username"],
    )
    if not config.username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    try:
        url = validate_source_url(config.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    password = config.password or server["password"]
    test_client = NavidromeClient(
        url=url,
        user=config.username.strip(),
        password=password,
    )
    try:
        data = await test_client.get_now_playing()
        if not NavidromeClient.response_is_ok(data):
            return ServerTestResponse(ok=False, message="上游拒绝连接或返回错误")
    except Exception:
        return ServerTestResponse(ok=False, message="无法连接到上游 Navidrome")
    finally:
        await test_client.close()
    return ServerTestResponse(ok=True, message="连接成功")


@app.get("/api/about", response_model=AboutResponse)
async def api_about():
    return AboutResponse(
        name=PROJECT_NAME,
        version=APP_VERSION,
        schema_version=SCHEMA_VERSION,
        features=["多 Navidrome 服务器", "播放历史统计", "隐私数据管理", "本地外观偏好"],
        license=LICENSE,
        project_url=PROJECT_URL,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=39421)
