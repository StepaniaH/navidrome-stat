import asyncio
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from src.database import init_db, save_play_session, get_top_artists, get_top_albums
from src.main import app


def _session(played_at: str, track_id: str = "t1", artist: str = "Artist", album: str = "Album", duration_sec: int = 30):
    return {
        "last_seen_at": played_at,
        "username": "testuser",
        "client_name": "Web Player",
        "track_id": track_id,
        "title": "Song",
        "artist": artist,
        "album": album,
        "is_transcoding": 0,
        "duration_sec": duration_sec,
    }


def test_get_top_artists_groups_and_orders(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", artist="Alpha"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", artist="Beta"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T03:00:00Z", "t3", artist="Alpha"), db_path=db_path))

    rows = asyncio.run(get_top_artists(db_path=db_path))

    assert rows == [{"artist": "Alpha", "count": 2}, {"artist": "Beta", "count": 1}]


def test_get_top_artists_skips_empty_artist(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", artist=""), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", artist="Alpha"), db_path=db_path))

    rows = asyncio.run(get_top_artists(db_path=db_path))

    assert rows == [{"artist": "Alpha", "count": 1}]


def test_get_top_artists_respects_limit(db_path):
    asyncio.run(init_db(db_path))
    for i in range(5):
        asyncio.run(save_play_session(_session(f"2024-03-24T0{i}:00:00Z", f"t{i}", artist=f"A{i}"), db_path=db_path))

    rows = asyncio.run(get_top_artists(limit=2, db_path=db_path))

    assert len(rows) == 2


def test_get_top_artists_empty_database(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_top_artists(db_path=db_path))
    assert rows == []


def test_get_top_albums_groups_and_orders(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", album="Record A"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", album="Record B"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T03:00:00Z", "t3", album="Record A"), db_path=db_path))

    rows = asyncio.run(get_top_albums(db_path=db_path))

    assert rows == [{"album": "Record A", "count": 2}, {"album": "Record B", "count": 1}]


def test_get_top_albums_skips_empty_album(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", album=""), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", album="Record A"), db_path=db_path))

    rows = asyncio.run(get_top_albums(db_path=db_path))

    assert rows == [{"album": "Record A", "count": 1}]


def test_get_top_albums_respects_limit(db_path):
    asyncio.run(init_db(db_path))
    for i in range(5):
        asyncio.run(save_play_session(_session(f"2024-03-24T0{i}:00:00Z", f"t{i}", album=f"Alb{i}"), db_path=db_path))

    rows = asyncio.run(get_top_albums(limit=2, db_path=db_path))

    assert len(rows) == 2


def test_get_top_albums_empty_database(db_path):
    asyncio.run(init_db(db_path))
    rows = asyncio.run(get_top_albums(db_path=db_path))
    assert rows == []


@pytest.mark.asyncio
@patch("src.main.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists(mock_get):
    mock_get.return_value = [{"artist": "Alpha", "count": 5}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 200
    assert response.json() == [{"artist": "Alpha", "count": 5}]
    mock_get.assert_awaited_once_with(limit=10)


@pytest.mark.asyncio
@patch("src.main.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums(mock_get):
    mock_get.return_value = [{"album": "Record A", "count": 3}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-albums")
    assert response.status_code == 200
    assert response.json() == [{"album": "Record A", "count": 3}]
    mock_get.assert_awaited_once_with(limit=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected_status", [
    (1, 200),
    (50, 200),
    (0, 422),
    (-1, 422),
    (51, 422),
])
@patch("src.main.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists_limit_bounds(mock_get, limit, expected_status):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/top-artists?limit={limit}")
    assert response.status_code == expected_status
    if expected_status == 200:
        mock_get.assert_awaited_once_with(limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected_status", [
    (1, 200),
    (50, 200),
    (0, 422),
    (-1, 422),
    (51, 422),
])
@patch("src.main.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums_limit_bounds(mock_get, limit, expected_status):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/top-albums?limit={limit}")
    assert response.status_code == expected_status
    if expected_status == 200:
        mock_get.assert_awaited_once_with(limit=limit)


@pytest.mark.asyncio
async def test_api_top_artists_limit_invalid_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists?limit=abc")
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("src.main.get_top_artists", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_top_artists_database_error(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"
    assert "db unavailable" not in response.text


@pytest.mark.asyncio
@patch("src.main.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.main.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/top-albums")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()