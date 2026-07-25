import asyncio
import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from src.auth import (
    SESSION_COOKIE_NAME,
    is_auth_enabled,
    is_authorized,
    session_cookie_value,
    verify_login_token,
)
from src.client import NavidromeClient
from src.database import (
    init_db,
    save_play_session,
    get_player_stats,
    get_transcoding_stats,
    get_hourly_stats,
    get_daily_stats,
    get_top_artists,
    get_top_albums,
    get_playback_history,
    get_summary,
    ping_db,
)
from src.runtime_state import runtime_state
from src.schemas import (
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    HISTORY_LIMIT_MIN,
    AuthStatusResponse,
    HealthLiveResponse,
    HistoryItem,
    HourlyStat,
    DailyStat,
    LoginRequest,
    NowPlayingItem,
    PlayerStat,
    TopArtistItem,
    TopAlbumItem,
    TOP_LIMIT_DEFAULT,
    TOP_LIMIT_MAX,
    TOP_LIMIT_MIN,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
    ReadinessResponse,
    RetentionApplyResponse,
    RetentionPreviewResponse,
    ConfirmRequest,
    SourceConfigResponse,
    SourceConfigUpdate,
    SourceTestRequest,
    SourceTestResponse,
    StorageStatsResponse,
    SummaryStat,
    TranscodingStat,
    UserDeletePreviewResponse,
    UserDeleteResponse,
    UserImportRequest,
    UserImportResponse,
    UserSummary,
)
from src.privacy_ops import (
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
from src.metrics import format_prometheus_metrics
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))
MAX_POLL_BACKOFF_SEC = int(os.getenv("MAX_POLL_BACKOFF_SEC", 60))
RETENTION_MAINTENANCE_SEC = int(os.getenv("RETENTION_MAINTENANCE_SEC", 86400))


async def _save_play_session_with_logging(session: dict) -> None:
    try:
        await save_play_session(session)
        runtime_state.record_save_success()
        logger.debug(
            "Recorded play session (duration=%ss)",
            session["duration_sec"],
        )
    except Exception as e:
        runtime_state.record_save_failure()
        logger.error("Failed to save play session: %s", e)


session_tracker = PlaybackSessionTracker(_save_play_session_with_logging)


async def finalize_session(player_id: str):
    """Calculates session duration and saves to DB if threshold is met."""
    await session_tracker.finalize_session(player_id)


async def polling_loop(client: NavidromeClient):
    logger.info("Starting polling loop with interval: %s seconds", POLL_INTERVAL)
    consecutive_failures = 0

    while True:
        current_time = datetime.now(timezone.utc)
        sleep_for = POLL_INTERVAL
        try:
            data = await client.get_now_playing()
            response = data.get("subsonic-response", {})
            if response.get("status") != "ok":
                error_info = response.get("error", {})
                error_code = error_info.get("code") if isinstance(error_info, dict) else None
                runtime_state.record_poll_upstream_error(current_time, error_code)
                logger.error("Error from Navidrome API (code=%s)", error_code)
                consecutive_failures += 1
                sleep_for = min(
                    POLL_INTERVAL * (2 ** (consecutive_failures - 1)),
                    MAX_POLL_BACKOFF_SEC,
                )
            else:
                now_playing = response.get("nowPlaying", {})
                entries = now_playing.get("entry", [])
                await session_tracker.process_poll(entries, current_time)
                runtime_state.record_poll_success(current_time)
                consecutive_failures = 0

        except Exception as e:
            runtime_state.record_poll_exception(current_time)
            logger.error("Error in polling loop: %s", e)
            consecutive_failures += 1
            sleep_for = min(
                POLL_INTERVAL * (2 ** (consecutive_failures - 1)),
                MAX_POLL_BACKOFF_SEC,
            )

        await asyncio.sleep(sleep_for)


async def retention_maintenance_loop():
    """Periodically purge play history older than the configured retention window."""
    while True:
        await asyncio.sleep(RETENTION_MAINTENANCE_SEC)
        try:
            result = await apply_retention_purge()
            if result["deleted"]:
                logger.info("Retention purge removed %s records", result["deleted"])
        except Exception as e:
            logger.error("Retention maintenance failed: %s", e)


async def run_startup_retention_purge():
    try:
        result = await apply_retention_purge()
        if result["deleted"]:
            logger.info("Startup retention purge removed %s records", result["deleted"])
    except Exception as e:
        logger.error("Startup retention purge failed: %s", e)


async def build_readiness_report() -> dict:
    db_ok = await ping_db()
    polling_running = runtime_state.polling_task_alive()

    if runtime_state.client_initialized:
        polling_status = "running" if polling_running else "stopped"
    else:
        polling_status = "not_started"

    if runtime_state.last_poll_ok is True:
        upstream_status = "ok"
    elif runtime_state.last_poll_ok is False:
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
    if runtime_state.last_poll_at is not None:
        seconds_since_poll = int(
            (datetime.now(timezone.utc) - runtime_state.last_poll_at).total_seconds()
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
            "active_sessions": len(session_tracker.active_sessions),
            "seconds_since_last_poll": seconds_since_poll,
            "last_upstream_error_code": runtime_state.last_upstream_error_code,
        },
    }


async def _query_stats(fetch):
    try:
        return await fetch()
    except Exception:
        logger.error("Database query failed")
        raise HTTPException(status_code=503, detail="Stats temporarily unavailable")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    await run_startup_retention_purge()

    client = None
    task = None
    retention_task = None
    try:
        config = await resolve_effective_source_config()
        if not has_full_config(config):
            raise ValueError(
                "Missing Navidrome configuration. Provide via environment "
                "variables (NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASS) "
                "or save a fallback in the settings UI."
            )
        client = NavidromeClient(
            url=config["url"],
            user=config["user"],
            password=config["password"],
        )
        runtime_state.client_initialized = True
        logger.info("Starting background polling task...")
        task = asyncio.create_task(polling_loop(client))
        runtime_state.polling_task = task
        retention_task = asyncio.create_task(retention_maintenance_loop())
    except Exception as e:
        runtime_state.client_initialized = False
        logger.error("Failed to initialize NavidromeClient: %s", e)

    yield

    logger.info("Shutting down background task...")
    if task is not None:
        task.cancel()
    if retention_task is not None:
        retention_task.cancel()
    for pid in list(session_tracker.active_sessions.keys()):
        await finalize_session(pid)
    if task is not None:
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Background task cancelled.")
    if retention_task is not None:
        try:
            await retention_task
        except asyncio.CancelledError:
            logger.info("Retention maintenance task cancelled.")
    if client is not None:
        await client.close()
    runtime_state.polling_task = None


app = FastAPI(lifespan=lifespan)

AUTH_EXEMPT_PATHS = frozenset({"/health", "/health/ready", "/metrics", "/api/auth/login", "/api/auth/status"})


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    return response


@app.middleware("http")
async def stats_auth_middleware(request: Request, call_next):
    if not is_auth_enabled():
        return await call_next(request)

    path = request.url.path
    if path in AUTH_EXEMPT_PATHS:
        return await call_next(request)
    if is_authorized(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    if path in ("/docs", "/redoc", "/openapi.json"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)

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
async def auth_login(body: LoginRequest):
    """Creates a browser session when STATS_API_TOKEN is configured."""
    if not is_auth_enabled():
        raise HTTPException(status_code=404, detail="Authentication is not enabled")
    if not verify_login_token(body.token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_cookie_value(),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout():
    """Clears the browser session cookie."""
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response


@app.get("/health/ready", response_model=ReadinessResponse)
async def health_ready():
    """Readiness probe: database and background collector state."""
    report = await build_readiness_report()
    status_code = 200 if report["status"] != "not_ready" else 503
    return JSONResponse(content=report, status_code=status_code)


@app.get("/metrics")
async def metrics():
    """Prometheus exposition endpoint; always anonymous."""
    active = len(session_tracker.active_sessions)
    return PlainTextResponse(
        content=format_prometheus_metrics(active_sessions=active),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/stats/summary", response_model=SummaryStat)
async def api_summary_stats():
    """Endpoint for aggregate listening statistics."""
    return await _query_stats(get_summary)


@app.get("/api/stats/players", response_model=list[PlayerStat])
async def api_player_stats():
    """Endpoint for player usage distribution."""
    return await _query_stats(get_player_stats)


@app.get("/api/stats/transcoding", response_model=list[TranscodingStat])
async def api_transcoding_stats():
    """Endpoint for transcoding ratio."""
    return await _query_stats(get_transcoding_stats)


@app.get("/api/stats/hourly", response_model=list[HourlyStat])
async def api_hourly_stats():
    """Endpoint for play counts grouped by hour of day (0-23)."""
    return await _query_stats(get_hourly_stats)


@app.get("/api/stats/daily", response_model=list[DailyStat])
async def api_daily_stats():
    """Endpoint for play counts per day over the last 30 days."""
    return await _query_stats(get_daily_stats)


@app.get("/api/stats/top-artists", response_model=list[TopArtistItem])
async def api_top_artists(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
):
    """Endpoint for top artists by play count."""
    return await _query_stats(lambda: get_top_artists(limit=limit))


@app.get("/api/stats/top-albums", response_model=list[TopAlbumItem])
async def api_top_albums(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
):
    """Endpoint for top albums by play count."""
    return await _query_stats(lambda: get_top_albums(limit=limit))


@app.get("/api/stats/now-playing", response_model=list[NowPlayingItem])
async def api_now_playing():
    """Endpoint for currently active playback sessions (in-memory, no DB access)."""
    try:
        now = datetime.now(timezone.utc)
        items: list[NowPlayingItem] = []
        for session in session_tracker.active_sessions.values():
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
):
    """Endpoint for recent playback history."""
    return await _query_stats(lambda: get_playback_history(limit=limit))


def _privacy_settings_response(days: int | None) -> PrivacySettingsResponse:
    return PrivacySettingsResponse(retention_days=days, permanent=days is None)


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
        return await apply_retention_purge()
    except Exception as exc:
        logger.error("Retention apply failed")
        raise HTTPException(status_code=503, detail="Retention operation failed") from exc


@app.get("/api/privacy/users", response_model=list[UserSummary])
async def api_privacy_users():
    users = await list_users()
    return users


@app.get("/api/privacy/users/{username}/export")
async def api_export_user(username: str):
    if not username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    try:
        payload = await export_user_data(username.strip())
    except Exception as exc:
        logger.error("User export failed")
        raise HTTPException(status_code=503, detail="Export failed") from exc
    filename = f"navidrome-stat-{username.strip()}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/privacy/users/{username}/import", response_model=UserImportResponse)
async def api_import_user(username: str, body: UserImportRequest):
    if not username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    try:
        result = await import_user_data(
            username.strip(),
            body.payload,
            merge=body.merge,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("User import failed")
        raise HTTPException(status_code=503, detail="Import failed") from exc
    return UserImportResponse(imported=result["imported"], merge=body.merge)


@app.get(
    "/api/privacy/users/{username}/delete/preview",
    response_model=UserDeletePreviewResponse,
)
async def api_delete_user_preview(username: str):
    if not username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    return await preview_delete_user(username.strip())


@app.post("/api/privacy/users/{username}/delete", response_model=UserDeleteResponse)
async def api_delete_user(username: str, body: ConfirmRequest):
    if not username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to delete data")
    try:
        return await delete_user_data(username.strip())
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
        await test_client.get_now_playing()
    except Exception:
        return SourceTestResponse(ok=False, message="无法连接到上游 Navidrome")
    finally:
        try:
            await test_client.close()
        except Exception:
            logger.error("Failed to close test NavidromeClient")
    return SourceTestResponse(ok=True, message="连接成功")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=39421)
