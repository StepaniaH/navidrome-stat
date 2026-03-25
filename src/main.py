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
    get_playback_history
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))
PLAY_THRESHOLD_SEC = 30  # Minimum seconds listened to count as a "Play"

# Global dictionary to track active playback sessions
# Structure: { "player_id": { ...session_data... } }
active_sessions = {}

async def finalize_session(player_id: str):
    """Calculates session duration and saves to DB if threshold is met."""
    if player_id not in active_sessions:
        return
        
    session = active_sessions.pop(player_id)
    duration = (session["last_seen_at"] - session["first_seen_at"]).total_seconds()
    
    if duration >= PLAY_THRESHOLD_SEC:
        session["duration_sec"] = int(duration)
        session["last_seen_at"] = session["last_seen_at"].isoformat()
        try:
            await save_play_session(session)
            logger.debug(f"Recorded play: {session['username']} - {session['title']} (Listened for {int(duration)}s)")
        except Exception as e:
            logger.error(f"Failed to save play session: {e}")
    else:
        logger.debug(f"Discarded short play: {session['title']} (Listened for {int(duration)}s)")

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
                
                if isinstance(entries, dict):
                    entries = [entries]
                
                current_time = datetime.now(timezone.utc)
                seen_player_ids = set()
                
                for entry in entries:
                    # Ignore paused tracks to avoid starting/continuing sessions when not actually playing
                    if not entry.get("isPlaying", True):
                        continue

                    player_id = str(entry.get("playerId"))
                    track_id = entry.get("id")
                    seen_player_ids.add(player_id)
                    
                    if player_id in active_sessions:
                        # Player is known
                        if active_sessions[player_id]["track_id"] == track_id:
                            # Still playing the same track, update last seen time
                            active_sessions[player_id]["last_seen_at"] = current_time
                        else:
                            # Track changed, finalize old session and start new
                            await finalize_session(player_id)
                            # Start new session
                            active_sessions[player_id] = {
                                "first_seen_at": current_time,
                                "last_seen_at": current_time,
                                "username": entry.get("username"),
                                "client_name": entry.get("playerName"),
                                "track_id": track_id,
                                "title": entry.get("title"),
                                "artist": entry.get("artist"),
                                "album": entry.get("album"),
                                "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
                            }
                    else:
                        # New player/session
                        active_sessions[player_id] = {
                            "first_seen_at": current_time,
                            "last_seen_at": current_time,
                            "username": entry.get("username"),
                            "client_name": entry.get("playerName"),
                            "track_id": track_id,
                            "title": entry.get("title"),
                            "artist": entry.get("artist"),
                            "album": entry.get("album"),
                            "is_transcoding": 1 if entry.get("transcodedContentType") else 0,
                        }
                
                # Garbage collection: finalize sessions that are no longer active
                stale_players = []
                for pid, session in active_sessions.items():
                    if pid not in seen_player_ids:
                        # If a player wasn't seen in the last 30 seconds, consider the session over
                        time_since_last_seen = (current_time - session["last_seen_at"]).total_seconds()
                        if time_since_last_seen >= 30:
                            stale_players.append(pid)
                
                for pid in stale_players:
                    await finalize_session(pid)

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
    # Finalize any remaining sessions before shutting down
    for pid in list(active_sessions.keys()):
        await finalize_session(pid)
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
    uvicorn.run(app, host="0.0.0.0", port=39421)
