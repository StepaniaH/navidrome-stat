"""Tests for the Phase 2 timezone-aware listening heatmap.

All timestamps are synthetic and pinned to UTC instants around midnight or
close to DST transitions to exercise timezone bucket boundaries without any
dependence on real playback data. Cases covered:

* ``get_weekday_hour_stats`` always returns exactly 168 zero-filled cells
  (7 weekdays x 24 hours); empty database still returns the full grid.
* UTC midnight timestamps bucket into the correct UTC weekday/hour.
* Asia/Shanghai (UTC+08:00) boundary: a play at ``23:30Z`` lands on the
  next local date and hour 07, weekday advances across midnight.
* America/New_York (UTC-05:00 standard time): a play at ``04:30Z`` lands on
  the previous local date in the late evening.
* Finite window filtering uses UTC bounds derived from the requested
  timezone's local calendar.
* All-history aggregates every row.
* ``get_daily_stats`` zeroes through midnight in a non-UTC timezone and
  emits every calendar date in the requested window.
* API endpoint ``GET /api/stats/heatmap`` returns the full grid, forwards
  ``days`` and ``timezone``, and rejects 1..6 with 422 just like the other
  historical endpoints.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from src.database import (
    init_db,
    save_play_session,
    get_weekday_hour_stats,
    get_daily_stats,
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
    # 2024-03-24 is a Sunday (weekday 6 in Python's date.weekday()).
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
    # 2024-03-24T23:30:00Z -> Asia/Shanghai is 2024-03-25T07:30:00+08:00.
    # Python weekday: 2024-03-25 is a Monday (0). Local hour 7.
    asyncio.run(save_play_session(_session("2024-03-24T23:30:00Z", "t1"), db_path=db_path))

    rows = asyncio.run(get_weekday_hour_stats(days=0, timezone_name=SHANGHAI, db_path=db_path))
    lookup = _grid_lookup(rows)
    assert lookup[(0, 7)] == 1
    # The UTC weekday at 23:30 of Sunday was 6, so that UTC cell MUST be 0.
    assert lookup[(6, 23)] == 0


def test_heatmap_new_york_boundary_pulls_into_previous_local_day(db_path):
    asyncio.run(init_db(db_path))
    # 2024-03-24T04:30:00Z -> America/New_York (UTC-05:00 standard / -04:00 DST
    # in mid-March after US DST begins). 2024-03-24 is a Sunday (6). On
    # 2024-03-24 DST was already in effect (-04:00), so local time is
    # 2024-03-24T00:30:00-04:00 -- same calendar date but hour 0. Use an
    # earlier instant instead so the boundary clearly crosses midnight backward.
    # 2024-03-24T03:30:00Z -> 2024-03-23T23:30:00-04:00. The UTC instant falls
    # on Sunday 03:30Z, but the NY local date is 2024-03-23 (Saturday, weekday 5)
    # at hour 23.
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
    # Two plays at 2024-03-24T23:30:00Z and 2024-03-25T00:30:00Z.
    # In Asia/Shanghai these become 2024-03-25T07:30 and 2024-03-25T08:30 -- both
    # on the same local date. The UTC date for the second play is 25 March, the
    # first UTC date is 24 March, but local grouping collapses both to 25 March.
    asyncio.run(save_play_session(_session("2024-03-24T23:30:00Z", "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-25T00:30:00Z", "t2"), db_path=db_path))

    rows = asyncio.run(get_daily_stats(days=0, timezone_name=SHANGHAI, db_path=db_path))
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-03-25"
    assert rows[0]["count"] == 2


def test_daily_new_york_window_includes_each_calendar_date(db_path):
    asyncio.run(init_db(db_path))
    # A 7-day window with no data must still produce every local calendar date.
    rows = asyncio.run(get_daily_stats(days=7, timezone_name=NEW_YORK, db_path=db_path))
    assert len(rows) == 7
    assert rows == sorted(rows, key=lambda r: r["date"])
    assert all(r["count"] == 0 for r in rows)


def test_daily_all_history_empty_returns_empty(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_daily_stats(days=0, timezone_name=SHANGHAI, db_path=db_path))
    assert rows == []


@pytest.mark.asyncio
@patch("src.main.get_weekday_hour_stats", new_callable=AsyncMock)
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
@patch("src.main.get_weekday_hour_stats", new_callable=AsyncMock)
async def test_api_heatmap_propagates_timezone(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            f"/api/stats/heatmap?days=7&timezone={SHANGHAI}"
        )
    assert response.status_code == 200
    mock_get.assert_awaited_once_with(days=7, timezone_name=SHANGHAI)


@pytest.mark.asyncio
@patch("src.main.get_weekday_hour_stats", new_callable=AsyncMock)
async def test_api_heatmap_rejects_invalid_timezone(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/heatmap?days=7&timezone=Invalid/Zone")
    assert response.status_code == 422
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [6, 91, -1])
async def test_api_heatmap_rejects_invalid_days(days):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/heatmap?days={days}")
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("src.main.get_weekday_hour_stats", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_heatmap_database_error_returns_503(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/heatmap")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"


@pytest.mark.asyncio
@patch("src.main.get_weekday_hour_stats", new_callable=AsyncMock)
async def test_api_heatmap_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/heatmap")
    assert response.status_code == 401
    mock_get.assert_not_awaited()