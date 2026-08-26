import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_daily_stats, get_hourly_stats, init_db, save_play_session
from src.main import app


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


def test_get_hourly_stats_aggregates_by_hour(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:30:00Z", "t2"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T16:00:00Z", "t3"), db_path=db_path))

    rows = asyncio.run(get_hourly_stats(db_path=db_path))

    by_hour = {row["hour"]: row["count"] for row in rows}
    assert by_hour.get(1) == 2
    assert by_hour.get(16) == 1
    assert all(0 <= row["hour"] <= 23 for row in rows)
    assert rows == sorted(rows, key=lambda r: r["hour"])


def test_get_hourly_stats_empty_database(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_hourly_stats(db_path=db_path))
    assert rows == []


def test_get_daily_stats_aggregates_recent_days(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc)
    recent_a = (now - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z")
    recent_b = (now - timedelta(days=2)).strftime("%Y-%m-%dT12:00:00Z")
    old = (now - timedelta(days=40)).strftime("%Y-%m-%dT12:00:00Z")

    asyncio.run(save_play_session(_session(recent_a, "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session(recent_a, "t2"), db_path=db_path))
    asyncio.run(save_play_session(_session(recent_b, "t3"), db_path=db_path))
    asyncio.run(save_play_session(_session(old, "t4"), db_path=db_path))

    # Default days=30 zero-fills every calendar date in the UTC window.
    rows = asyncio.run(get_daily_stats(db_path=db_path))

    assert len(rows) == 30
    by_date = {row["date"]: row["count"] for row in rows}
    assert by_date[recent_a[:10]] == 2
    assert by_date[recent_b[:10]] == 1
    assert by_date.get(old[:10], 0) == 0  # outside the window
    # All counts sum to the plays inside the window.
    assert sum(r["count"] for r in rows) == 3
    assert rows == sorted(rows, key=lambda r: r["date"])
    assert all(row["date"][:4].isdigit() for row in rows)


@pytest.mark.parametrize(
    "days,tz,expected_len",
    [
        (30, "UTC", 30),
        (7, "America/New_York", 7),
    ],
)
def test_get_daily_stats_zero_fills_every_calendar_date(db_path, days, tz, expected_len):
    """Finite windows produce every calendar date even with no data."""
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_daily_stats(days=days, timezone_name=tz, db_path=db_path))
    assert len(rows) == expected_len
    assert all(row["count"] == 0 for row in rows)
    assert rows == sorted(rows, key=lambda r: r["date"])


def test_get_daily_stats_all_history_empty(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_daily_stats(days=0, db_path=db_path))
    assert rows == []


def test_get_daily_stats_respects_days_window(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=3)).strftime("%Y-%m-%dT12:00:00Z")
    mid = (now - timedelta(days=20)).strftime("%Y-%m-%dT12:00:00Z")
    old = (now - timedelta(days=80)).strftime("%Y-%m-%dT12:00:00Z")

    asyncio.run(save_play_session(_session(recent, "t1"), db_path=db_path))
    asyncio.run(save_play_session(_session(mid, "t2"), db_path=db_path))
    asyncio.run(save_play_session(_session(old, "t3"), db_path=db_path))

    rows_30 = asyncio.run(get_daily_stats(days=30, db_path=db_path))
    # Finite window zero-fills every date from today-29 through today.
    assert len(rows_30) == 30
    by_date_30 = {r["date"]: r["count"] for r in rows_30}
    assert by_date_30[recent[:10]] == 1
    assert by_date_30[mid[:10]] == 1
    assert by_date_30.get(old[:10], 0) == 0  # outside the window
    assert sum(r["count"] for r in rows_30) == 2

    rows_90 = asyncio.run(get_daily_stats(days=90, db_path=db_path))
    assert len(rows_90) == 90
    by_date_90 = {r["date"]: r["count"] for r in rows_90}
    assert by_date_90.get(recent[:10]) == 1
    assert by_date_90.get(mid[:10]) == 1
    assert by_date_90.get(old[:10]) == 1
    assert sum(r["count"] for r in rows_90) == 3

    rows_7 = asyncio.run(get_daily_stats(days=7, db_path=db_path))
    assert len(rows_7) == 7
    by_date_7 = {r["date"]: r["count"] for r in rows_7}
    assert by_date_7[recent[:10]] == 1
    assert sum(r["count"] for r in rows_7) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,mock_path,payload",
    [
        (
            "/api/stats/hourly",
            "src.routes.stats.get_hourly_stats",
            [{"hour": 9, "count": 5}, {"hour": 21, "count": 7}],
        ),
        (
            "/api/stats/daily",
            "src.routes.stats.get_daily_stats",
            [{"date": "2024-03-24", "count": 3}],
        ),
    ],
)
async def test_api_stats_returns_payload(endpoint, mock_path, payload):
    mock_get = AsyncMock()
    mock_get.return_value = payload
    with patch(mock_path, mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(endpoint)
    assert response.status_code == 200
    assert response.json() == payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,mock_path",
    [
        ("/api/stats/hourly", "src.routes.stats.get_hourly_stats"),
        ("/api/stats/daily", "src.routes.stats.get_daily_stats"),
        ("/api/stats/heatmap", "src.routes.stats.get_weekday_hour_stats"),
    ],
)
async def test_api_stats_database_error_returns_503(endpoint, mock_path):
    mock_get = AsyncMock(side_effect=RuntimeError("db unavailable"))
    with patch(mock_path, mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(endpoint)
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,mock_path",
    [
        ("/api/stats/hourly", "src.routes.stats.get_hourly_stats"),
        ("/api/stats/daily", "src.routes.stats.get_daily_stats"),
        ("/api/stats/heatmap", "src.routes.stats.get_weekday_hour_stats"),
    ],
)
async def test_api_stats_requires_auth_when_token_configured(endpoint, mock_path):
    mock_get = AsyncMock()
    mock_get.return_value = []
    with patch(mock_path, mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
                response = await ac.get(endpoint)
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected_days",
    [
        ("", 30),
        ("?days=0", 0),
        ("?days=7", 7),
        ("?days=90", 90),
    ],
)
@patch("src.routes.stats.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_stats_days_param(mock_get, query, expected_days):
    payload = [{"date": "2024-03-24", "count": 3}]
    mock_get.return_value = payload
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/daily{query}")
    assert response.status_code == 200
    assert response.json() == payload
    mock_get.assert_awaited_once_with(days=expected_days, timezone_name="UTC")


@pytest.mark.asyncio
async def test_api_daily_stats_days_invalid_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/daily?days=not-a-number")
    assert response.status_code == 422