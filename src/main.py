import asyncio
import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.client import NavidromeClient
from src.database import (
    init_db,
    save_play_session,
    get_player_stats,
    get_transcoding_stats,
    get_playback_history,
)
from src.sessions import PlaybackSessionTracker

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))


async def _save_play_session_with_logging(session: dict) -> None:
    try:
        await save_play_session(session)
        logger.debug(
            "Recorded play: %s - %s (Listened for %ss)",
            session["username"],
            session["title"],
            session["duration_sec"],
        )
    except Exception as e:
        logger.error("Failed to save play session: %s", e)


session_tracker = PlaybackSessionTracker(_save_play_session_with_logging)


async def finalize_session(player_id: str):
    """Calculates session duration and saves to DB if threshold is met."""
    await session_tracker.finalize_session(player_id)


async def polling_loop(client: NavidromeClient):
    logger.info("Starting polling loop with interval: %s seconds", POLL_INTERVAL)

    while True:
        try:
            data = await client.get_now_playing()
            response = data.get("subsonic-response", {})
            if response.get("status") != "ok":
                error_info = response.get("error", {})
                logger.error("Error from Navidrome API: %s", error_info)
            else:
                now_playing = response.get("nowPlaying", {})
                entries = now_playing.get("entry", [])
                current_time = datetime.now(timezone.utc)
                await session_tracker.process_poll(entries, current_time)

        except Exception as e:
            logger.error("Error in polling loop: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()

    client = None
    task = None
    try:
        client = NavidromeClient()
        logger.info("Starting background polling task...")
        task = asyncio.create_task(polling_loop(client))
    except Exception as e:
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
    return {"status": "ok"}


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
