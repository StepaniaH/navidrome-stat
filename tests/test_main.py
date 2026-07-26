import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@patch("src.main.ping_db", return_value=True)
async def test_health_ready_ok_when_database_available(mock_ping):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ready", "degraded", "not_ready")
    assert body["checks"]["database"] == "ok"
    assert "metrics" in body
    assert "poll_success_total" in body["metrics"]


@pytest.mark.asyncio
@patch("src.main.ping_db", return_value=False)
async def test_health_ready_not_ready_when_database_unavailable(mock_ping):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "error"

@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_api_player_stats(mock_get_stats):
    mock_get_stats.return_value = [{"client_name": "Feishin", "count": 10}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/players")
    assert response.status_code == 200
    assert response.json() == [{"client_name": "Feishin", "count": 10}]

@pytest.mark.asyncio
@patch("src.main.get_summary", new_callable=AsyncMock)
async def test_api_summary_stats(mock_get_summary):
    mock_get_summary.return_value = {
        "total_plays": 12,
        "total_listen_sec": 3600,
        "unique_tracks": 8,
        "client_count": 2,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/summary")
    assert response.status_code == 200
    assert response.json()["total_plays"] == 12


@pytest.mark.asyncio
@patch("src.main.get_transcoding_stats", new_callable=AsyncMock)
async def test_api_transcoding_stats(mock_get_stats):
    mock_get_stats.return_value = [{"is_transcoding": 0, "count": 5}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/transcoding")
    assert response.status_code == 200
    assert response.json() == [{"is_transcoding": 0, "count": 5}]


@pytest.mark.asyncio
@patch("src.main.get_playback_history", new_callable=AsyncMock)
async def test_api_history_limit_default(mock_get_history):
    mock_get_history.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/history")
    assert response.status_code == 200
    mock_get_history.assert_awaited_once_with(limit=10, days=0, timezone_name="UTC")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected_status", [
    (1, 200),
    (100, 200),
    (0, 422),
    (-1, 422),
    (101, 422),
])
@patch("src.main.get_playback_history", new_callable=AsyncMock)
async def test_api_history_limit_bounds(mock_get_history, limit, expected_status):
    mock_get_history.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/history?limit={limit}")
    assert response.status_code == expected_status
    if expected_status == 200:
        mock_get_history.assert_awaited_once_with(limit=limit, days=0, timezone_name="UTC")


@pytest.mark.asyncio
async def test_api_history_limit_invalid_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/history?limit=abc")
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_stats_database_error_returns_generic_message(mock_get_stats):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/players")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"
    assert "db unavailable" not in response.text


@pytest.mark.asyncio
async def test_api_now_playing_empty_when_no_sessions():
    from src.main import session_tracker
    session_tracker.active_sessions.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/now-playing")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_now_playing_returns_active_sessions():
    from datetime import datetime, timezone, timedelta
    from src.main import session_tracker
    first_seen = datetime.now(timezone.utc) - timedelta(seconds=65)
    session_tracker.active_sessions.clear()
    session_tracker.active_sessions["player-1"] = {
        "first_seen_at": first_seen,
        "last_seen_at": first_seen,
        "username": "alice",
        "client_name": "Feishin",
        "track_id": "t-1",
        "title": "Song A",
        "artist": "Artist A",
        "album": "Album A",
        "is_transcoding": 0,
        "committed": False,
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/stats/now-playing")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        item = body[0]
        assert item["username"] == "alice"
        assert item["title"] == "Song A"
        assert item["artist"] == "Artist A"
        assert item["client_name"] == "Feishin"
        assert isinstance(item["seconds_elapsed"], int)
        assert item["seconds_elapsed"] >= 65
        assert "first_seen_at" not in item
        assert "last_seen_at" not in item
        assert "committed" not in item
    finally:
        session_tracker.active_sessions.clear()
