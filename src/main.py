import asyncio
import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from src.client import NavidromeClient
from src.database import (
    init_db,
    save_play_session,
    get_player_stats,
    get_transcoding_stats,
    get_playback_history,
    ping_db,
)
from src.runtime_state import runtime_state
from src.sessions import PlaybackSessionTracker

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))


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

    while True:
        current_time = datetime.now(timezone.utc)
        try:
            data = await client.get_now_playing()
            response = data.get("subsonic-response", {})
            if response.get("status") != "ok":
                error_info = response.get("error", {})
                error_code = error_info.get("code") if isinstance(error_info, dict) else None
                runtime_state.record_poll_upstream_error(current_time, error_code)
                logger.error("Error from Navidrome API (code=%s)", error_code)
            else:
                now_playing = response.get("nowPlaying", {})
                entries = now_playing.get("entry", [])
                await session_tracker.process_poll(entries, current_time)
                runtime_state.record_poll_success(current_time)

        except Exception as e:
            runtime_state.record_poll_exception(current_time)
            logger.error("Error in polling loop: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()

    client = None
    task = None
    try:
        client = NavidromeClient()
        runtime_state.client_initialized = True
        logger.info("Starting background polling task...")
        task = asyncio.create_task(polling_loop(client))
        runtime_state.polling_task = task
    except Exception as e:
        runtime_state.client_initialized = False
        logger.error("Failed to initialize NavidromeClient: %s", e)

    yield

    logger.info("Shutting down background task...")
    if task is not None:
        task.cancel()
    for pid in list(session_tracker.active_sessions.keys()):
        await finalize_session(pid)
    if task is not None:
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Background task cancelled.")
    if client is not None:
        await client.close()
    runtime_state.polling_task = None


app = FastAPI(lifespan=lifespan)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Dashboard not found"}


@app.get("/health")
async def health():
    """Liveness probe: process is running."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe: database and background collector state."""
    report = await build_readiness_report()
    status_code = 200 if report["status"] != "not_ready" else 503
    return JSONResponse(content=report, status_code=status_code)


@app.get("/api/stats/players")
async def api_player_stats():
    """Endpoint for player usage distribution."""
    return await get_player_stats()


@app.get("/api/stats/transcoding")
async def api_transcoding_stats():
    """Endpoint for transcoding ratio."""
    return await get_transcoding_stats()


@app.get("/api/stats/history")
async def api_playback_history(limit: int = 10):
    """Endpoint for top playback history."""
    return await get_playback_history(limit=limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=39421)
