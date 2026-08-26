"""Tests for timezone-aware heatmap and daily buckets."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import (
    get_daily_stats,
    get_weekday_hour_stats,
    init_db,
    save_play_session,
)
from src.main import app

SHANGHAI = "Asia/Shanghai"
NEW_YORK = "America/New_York"


def _session(played_at: str, track_id: str = "t1", duration_sec: int = 30):
    return {
        "last_seen_at": played_at,
        "username": "testuser",
        "client_name": "Web Player",
        "track_id": track_id,
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "is_transcoding": 0,
        "duration_sec": duration_sec,
    }


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _grid_lookup(rows):
    return {(r["weekday"], r["hour"]): r["count"] for r in rows}


def test_heatmap_returns_full_168_grid_for_empty_database(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_weekday_hour_stats(days=0, db_path=db_path))
    assert len(rows) == 168
    assert all(row["count"] == 0 for row in rows)
    keys = {(row["weekday"], row["hour"]) for row in rows}
    for w in range(7):
        for h in range(24):
            assert (w, h) in keys


def test_heatmap_buckets_utc_midnight_correctly(db_path):
    asyncio.run(init_db(db_path))
    # Python date.weekday() maps Sunday to 6.
    asyncio.run(save_play_session(_session("2024-03-24T00:30:00Z", "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T00:45:00Z", "t2"), db_path=db_path))

    rows = asyncio.run(get_weekday_hour_stats(days=0, timezone_name="UTC", db_path=db_path))
    lookup = _grid_lookup(rows)
    assert lookup[(6, 0)] == 2
    assert sum(lookup.values()) == 2


def test_heatmap_utc_window_excludes_old_rows(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    inside = _iso(now - timedelta(days=1))
    outside = _iso(now - timedelta(days=80))
    asyncio.run(save_play_session(_session(inside, "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session(outside, "t2"), db_path=db_path))

    rows = asyncio.run(get_weekday_hour_stats(days=30, timezone_name="UTC", db_path=db_path))
    assert sum(r["count"] for r in rows) == 1


def test_heatmap_shanghai_boundary_pushes_into_next_local_day(db_path):
    asyncio.run(init_db(db_path))
    # 23:30 UTC becomes Monday 07:30 in Asia/Shanghai.
    asyncio.run(save_play_session(_session("2024-03-24T23:30:00Z", "t1"), db_path=db_path))

    rows = asyncio.run(get_weekday_hour_stats(days=0, timezone_name=SHANGHAI, db_path=db_path))
    lookup = _grid_lookup(rows)
    assert lookup[(0, 7)] == 1
    # The original Sunday 23:00 UTC bucket remains empty.
    assert lookup[(6, 23)] == 0


def test_heatmap_new_york_boundary_pulls_into_previous_local_day(db_path):
    asyncio.run(init_db(db_path))
    # After the DST transition, Sunday 03:30 UTC is Saturday 23:30 in New York.
    asyncio.run(save_play_session(_session("2024-03-24T03:30:00Z", "t1"), db_path=db_path))

    rows = asyncio.run(get_weekday_hour_stats(days=0, timezone_name=NEW_YORK, db_path=db_path))
    lookup = _grid_lookup(rows)
    assert lookup[(5, 23)] == 1
    assert lookup[(6, 3)] == 0


def test_heatmap_invalid_timezone_raises_valueerror(db_path):
    asyncio.run(init_db(db_path))
    with pytest.raises(ValueError):
        asyncio.run(get_weekday_hour_stats(days=0, timezone_name="NotAReal/Zone", db_path=db_path))


def test_daily_zero_filled_in_shanghai_timestamps_cross_midnight(db_path):
    asyncio.run(init_db(db_path))
    # Adjacent UTC dates collapse into one local date in Asia/Shanghai.
    asyncio.run(save_play_session(_session("2024-03-24T23:30:00Z", "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-25T00:30:00Z", "t2"), db_path=db_path))

    rows = asyncio.run(get_daily_stats(days=0, timezone_name=SHANGHAI, db_path=db_path))
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-03-25"
    assert rows[0]["count"] == 2


@pytest.mark.asyncio
@patch("src.routes.stats.get_weekday_hour_stats", new_callable=AsyncMock)
async def test_api_heatmap_returns_full_grid(mock_get):
    mock_get.return_value = [
        {"weekday": w, "hour": h, "count": 0} for w in range(7) for h in range(24)
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/heatmap?days=30")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 168
    mock_get.assert_awaited_once_with(days=30, timezone_name="UTC")


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [6, 91, -1])
async def test_api_heatmap_rejects_invalid_days(days):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/heatmap?days={days}")
    assert response.status_code == 422
