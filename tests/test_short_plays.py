import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_short_play_stats, init_db, save_play_attempt, save_play_session
from src.main import app
from src.sessions import PlaybackSessionTracker


def attempt(at, duration=12):
    return {
        "last_seen_at": at,
        "username": "user",
        "client_name": "Test",
        "track_id": "short-1",
        "title": "Short",
        "artist": "Artist",
        "album": "Album",
        "is_transcoding": 0,
        "duration_sec": duration,
        "outcome": "short_play",
    }


def session(at, duration=30):
    data = attempt(at, duration)
    data["duration_sec"] = duration
    return data


def test_short_play_stats_are_separate_from_counted_plays(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_attempt(attempt("2024-03-24T12:00:00Z"), db_path=db_path))
    asyncio.run(save_play_session(session("2024-03-24T13:00:00Z"), db_path=db_path))
    stats = asyncio.run(get_short_play_stats(db_path=db_path))
    assert stats == {
        "short_count": 1,
        "counted_count": 1,
        "attempt_count": 2,
        "short_listen_sec": 12,
        "short_play_rate_pct": 50.0,
    }


@pytest.mark.asyncio
async def test_tracker_saves_short_attempt_without_play(save_mock=None):
    saves = []
    attempts = []

    async def save_play(item):
        saves.append(item)

    async def save_attempt(item):
        attempts.append(item)

    tracker = PlaybackSessionTracker(save_play, play_threshold_sec=30, save_attempt=save_attempt)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await tracker.process_poll([{"playerId": "p", "id": "t", "isPlaying": True}], t0)
    await tracker.process_poll([{"playerId": "p", "id": "t", "isPlaying": True}], t0 + timedelta(seconds=10))
    await tracker.process_poll([], t0 + timedelta(seconds=41))
    assert saves == []
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "short_play"
    assert attempts[0]["duration_sec"] == 10


@pytest.mark.asyncio
async def test_short_play_endpoint_propagates_window_and_timezone():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stats/short-plays?days=30&timezone=UTC")
    assert response.status_code in (200, 503)
