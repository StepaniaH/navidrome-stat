import asyncio
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.client import NavidromeClient
from src.database import (
    init_db, 
    save_snapshot, 
    get_player_stats, 
    get_transcoding_stats, 
    get_playback_history
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))

async def polling_loop():
    logger.info(f"Starting polling loop with interval: {POLL_INTERVAL} seconds")
    try:
        client = NavidromeClient()
    except Exception as e:
        logger.error(f"Failed to initialize NavidromeClient: {e}")
        return

    while True:
        try:
            data = await client.get_now_playing()
            response = data.get("subsonic-response", {})
            if response.get("status") != "ok":
                error_info = response.get("error", {})
                logger.error(f"Error from Navidrome API: {error_info}")
            else:
                now_playing = response.get("nowPlaying", {})
                entries = now_playing.get("entry", [])
                
                # Handle single entry being returned as a dict instead of a list
                if isinstance(entries, dict):
                    entries = [entries]
                
                timestamp = datetime.utcnow().isoformat()
                
                for entry in entries:
                    snapshot = {
                        "timestamp": timestamp,
                        "username": entry.get("username"),
                        "player_id": str(entry.get("playerId")),
                        "client_name": entry.get("playerName"),
                        "track_id": entry.get("id"),
                        "title": entry.get("title"),
                        "artist": entry.get("artist"),
                        "album": entry.get("album"),
                        "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
                        "original_bitrate": entry.get("bitRate"),
                        "current_bitrate": entry.get("bitRate"),
                        "position_ms": 0, # getNowPlaying doesn't provide precise position
                        "player_state": "playing" if entry.get("isPlaying", True) else "paused"
                    }
                    await save_snapshot(snapshot)
                    logger.info(f"Saved snapshot for user: {snapshot['username']}, track: {snapshot['title']}")
                
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
        
        await asyncio.sleep(POLL_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    
    logger.info("Starting background polling task...")
    task = asyncio.create_task(polling_loop())
    
    yield
    
    # Shutdown
    logger.info("Shutting down background task...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background task cancelled.")

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
