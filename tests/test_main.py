from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@patch("src.collectors.ping_db", return_value=True)
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
@patch("src.collectors.ping_db", return_value=False)
async def test_health_ready_not_ready_when_database_unavailable(mock_ping):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "error"

@pytest.mark.asyncio
@patch("src.routes.stats.get_player_stats", new_callable=AsyncMock)
async def test_api_player_stats(mock_get_stats):
    mock_get_stats.return_value = [{
        "client_name": "Feishin",
        "count": 10,
        "total_listen_sec": 1500,
        "average_listen_sec": 150.0,
        "transcoded_count": 2,
        "transcoding_rate_pct": 20.0,
    }]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/players")
    assert response.status_code == 200
    assert response.json() == [{
        "client_name": "Feishin",
        "count": 10,
        "total_listen_sec": 1500,
        "average_listen_sec": 150.0,
        "transcoded_count": 2,
        "transcoding_rate_pct": 20.0,
    }]

@pytest.mark.asyncio
@patch("src.routes.stats.get_summary", new_callable=AsyncMock)
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
@patch("src.routes.stats.get_transcoding_stats", new_callable=AsyncMock)
async def test_api_transcoding_stats(mock_get_stats):
    mock_get_stats.return_value = [{
        "is_transcoding": 0,
        "count": 5,
        "total_listen_sec": 600,
        "plays_pct": 100.0,
        "listen_sec_pct": 100.0,
    }]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/transcoding")
    assert response.status_code == 200
    assert response.json() == [{
        "is_transcoding": 0,
        "count": 5,
        "total_listen_sec": 600,
        "plays_pct": 100.0,
        "listen_sec_pct": 100.0,
    }]


@pytest.mark.asyncio
@patch("src.routes.stats.get_playback_history", new_callable=AsyncMock)
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
@patch("src.routes.stats.get_playback_history", new_callable=AsyncMock)
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
@patch("src.routes.stats.get_player_stats", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_stats_database_error_returns_generic_message(mock_get_stats):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/players")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"
    assert "db unavailable" not in response.text


@pytest.mark.asyncio
async def test_api_now_playing_empty_when_no_sessions():
    from src.collectors import session_tracker
    session_tracker._sessions.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/now-playing")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_now_playing_returns_active_sessions():
    from datetime import datetime, timedelta, timezone

    from src.collectors import session_tracker

    first_seen = datetime.now(timezone.utc) - timedelta(seconds=65)
    session_tracker._sessions.clear()
    await session_tracker.process_poll(
        [{
            "playerId": "player-1",
            "id": "t-1",
            "title": "Song A",
            "artist": "Artist A",
            "album": "Album A",
            "username": "alice",
            "playerName": "Feishin",
            "isPlaying": True,
        }],
        first_seen,
    )
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
        session_tracker._sessions.clear()


@pytest.mark.asyncio
async def test_api_now_playing_aggregates_runtime_trackers_and_excludes_paused(
    monkeypatch,
):
    from datetime import datetime, timedelta, timezone

    import src.collectors as collectors
    from src.sessions import PlaybackSessionTracker

    async def save_session(_session):
        return None

    now = datetime.now(timezone.utc)
    entries = {
        "player-1": {
            "playerId": "player-1",
            "id": "t-1",
            "title": "Synthetic Track 1",
            "artist": "Synthetic Artist 1",
            "username": "synthetic-user-1",
            "playerName": "Synthetic Client 1",
            "isPlaying": True,
        },
        "player-2": {
            "playerId": "player-2",
            "id": "t-2",
            "title": "Synthetic Track 2",
            "artist": "Synthetic Artist 2",
            "username": "synthetic-user-2",
            "playerName": "Synthetic Client 2",
            "isPlaying": True,
        },
        "paused-player": {
            "playerId": "paused-player",
            "id": "t-3",
            "title": "Synthetic Paused Track",
            "artist": "Synthetic Paused Artist",
            "username": "synthetic-paused-user",
            "playerName": "Synthetic Paused Client",
            "isPlaying": True,
        },
    }
    first_tracker = PlaybackSessionTracker(save_session)
    second_tracker = PlaybackSessionTracker(save_session)
    await first_tracker.process_poll([entries["player-1"]], now)
    await second_tracker.process_poll(
        [entries["player-2"], entries["paused-player"]], now
    )
    # A pause poll keeps that session visible but excluded from now-playing,
    # while players still reporting stay active.
    paused_entry = dict(entries["paused-player"], isPlaying=False)
    await second_tracker.process_poll(
        [entries["player-2"], paused_entry], now + timedelta(seconds=1)
    )
    monkeypatch.setattr(
        collectors, "_runtime_trackers", [first_tracker, second_tracker]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/now-playing")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == [
        "Synthetic Track 1",
        "Synthetic Track 2",
    ]
