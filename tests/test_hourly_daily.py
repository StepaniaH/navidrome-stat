import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from src.database import init_db, save_play_session, get_hourly_stats, get_daily_stats
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

    rows = asyncio.run(get_daily_stats(db_path=db_path))

    assert len(rows) == 2
    by_date = {row["date"]: row["count"] for row in rows}
    assert by_date[recent_a[:10]] == 2
    assert by_date[recent_b[:10]] == 1
    assert rows == sorted(rows, key=lambda r: r["date"])
    assert all(row["date"][:4].isdigit() for row in rows)


def test_get_daily_stats_counts_only(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_daily_stats(db_path=db_path))
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
    assert {r["date"] for r in rows_30} == {recent[:10], mid[:10]}

    rows_90 = asyncio.run(get_daily_stats(days=90, db_path=db_path))
    assert {r["date"] for r in rows_90} == {recent[:10], mid[:10], old[:10]}

    rows_7 = asyncio.run(get_daily_stats(days=7, db_path=db_path))
    assert {r["date"] for r in rows_7} == {recent[:10]}


@pytest.mark.asyncio
@patch("src.main.get_hourly_stats", new_callable=AsyncMock)
async def test_api_hourly_stats(mock_get):
    mock_get.return_value = [{"hour": 9, "count": 5}, {"hour": 21, "count": 7}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/hourly")
    assert response.status_code == 200
    assert response.json() == [{"hour": 9, "count": 5}, {"hour": 21, "count": 7}]


@pytest.mark.asyncio
@patch("src.main.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_stats(mock_get):
    mock_get.return_value = [{"date": "2024-03-24", "count": 3}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/daily")
    assert response.status_code == 200
    assert response.json() == [{"date": "2024-03-24", "count": 3}]


@pytest.mark.asyncio
@patch("src.main.get_hourly_stats", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_hourly_stats_database_error(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/hourly")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"


@pytest.mark.asyncio
@patch("src.main.get_daily_stats", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_daily_stats_database_error(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/daily")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"


@pytest.mark.asyncio
@patch("src.main.get_hourly_stats", new_callable=AsyncMock)
async def test_api_hourly_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/hourly")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.main.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/daily")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [7, 30, 90])
@patch("src.main.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_stats_days_param(mock_get, days):
    mock_get.return_value = [{"date": "2024-03-24", "count": 3}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/daily?days={days}")
    assert response.status_code == 200
    assert response.json() == [{"date": "2024-03-24", "count": 3}]
    mock_get.assert_awaited_once_with(days=days)


@pytest.mark.asyncio
@patch("src.main.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_stats_default_days_is_30(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/daily")
    assert response.status_code == 200
    mock_get.assert_awaited_once_with(days=30)


@pytest.mark.asyncio
@pytest.mark.parametrize("days,expected_status", [
    (6, 422),
    (91, 422),
    (0, 422),
    (-1, 422),
])
@patch("src.main.get_daily_stats", new_callable=AsyncMock)
async def test_api_daily_stats_days_bounds(mock_get, days, expected_status):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/daily?days={days}")
    assert response.status_code == expected_status
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_daily_stats_days_invalid_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/daily?days=not-a-number")
    assert response.status_code == 422