import asyncio
import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
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
    LoginRequest,
    PlayerStat,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
    ReadinessResponse,
    RetentionApplyResponse,
    RetentionPreviewResponse,
    ConfirmRequest,
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
    import_user_data,
    list_users,
    preview_delete_user,
    preview_retention_purge,
    set_retention_days,
    validate_retention_days,
)
from src.sessions import PlaybackSessionTracker

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
        client = NavidromeClient()
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

AUTH_EXEMPT_PATHS = frozenset({"/health", "/health/ready", "/api/auth/login", "/api/auth/status"})


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=39421)
