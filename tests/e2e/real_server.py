"""Isolated SQLite fixture for API-to-browser tests; no upstream configuration."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.database import init_db  # noqa: E402
from src.persistence import save_play_session  # noqa: E402


async def seed():
    await init_db()
    start = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    for index in range(56):
        await save_play_session(
            {
                "last_seen_at": (start + timedelta(minutes=index)).isoformat(),
                "username": "listener" if index < 55 else "other-listener",
                "source_id": "legacy",
                "source_name": "Synthetic library",
                "client_name": "Synthetic player",
                "track_id": f"track-{index}",
                "title": (
                    "Night window" if index < 2 else
                    "<img src=x onerror=window.__listens_injected=true>" if index == 53 else
                    f"Synthetic track {index}"
                ),
                "artist": "Synthetic artist",
                "album": "Returning album" if index < 2 else "Synthetic album",
                "album_id": "returning-album" if index < 2 else "synthetic-album",
                "duration_sec": None if index == 54 else 120,
                "source": "listenbrainz" if index == 54 else "poller",
                "session_id": f"synthetic-session-{index}",
                "finalized": True,
            }
        )
    for timestamp, album, album_id in (
        ("2026-06-01T12:00:00+00:00", "Returning album", "returning-album"),
        ("2026-09-01T12:00:00+00:00", "Earlier album", "earlier-album"),
    ):
        await save_play_session({
            "last_seen_at": timestamp, "username": "listener", "source_id": "legacy",
            "track_id": f"old-{album_id}", "title": "Earlier track",
            "artist": "Synthetic artist", "album": album, "album_id": album_id,
            "duration_sec": 120,
        })


if __name__ == "__main__":
    asyncio.run(seed())
    import uvicorn

    uvicorn.run("src.main:app", host="127.0.0.1", port=39424)
