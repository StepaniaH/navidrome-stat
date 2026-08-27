import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_top_albums, get_top_artists, init_db, save_play_session
from src.main import app


def _session(played_at: str, track_id: str = "t1", artist: str = "Artist", album: str = "Album", duration_sec: int = 30, transcoding: int = 0, artist_id=None):
    return {
        "last_seen_at": played_at,
        "username": "testuser",
        "client_name": "Web Player",
        "track_id": track_id,
        "title": "Song",
        "artist": artist,
        "album": album,
        "is_transcoding": transcoding,
        "duration_sec": duration_sec,
        "artist_id": artist_id,
    }


def _row(name_key: str, name: str, count: int, total_listen_sec: int, value: int, **extra):
    return {name_key: name, "count": count, "total_listen_sec": total_listen_sec, "value": value, **extra}


def test_get_top_artists_groups_and_orders(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", artist="Alpha", duration_sec=30), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", artist="Beta", duration_sec=10), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T03:00:00Z", "t3", artist="Alpha", duration_sec=40), db_path=db_path))

    rows = asyncio.run(get_top_artists(db_path=db_path))

    assert rows == [
        _row("artist", "Alpha", 2, 70, 2, artist_id=None),
        _row("artist", "Beta", 1, 10, 1, artist_id=None),
    ]


def test_get_top_artists_keeps_artist_id_for_ranking_row(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", artist="Alpha", artist_id="ar-7"), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", artist="Alpha", artist_id="ar-3"), db_path=db_path))

    rows = asyncio.run(get_top_artists(db_path=db_path))

    assert len(rows) == 1
    assert rows[0]["artist"] == "Alpha"
    assert rows[0]["artist_id"] == "ar-7"


def test_get_top_albums_groups_and_orders(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", album="Record A", duration_sec=30), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", album="Record B", duration_sec=10), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T03:00:00Z", "t3", album="Record A", duration_sec=40), db_path=db_path))

    rows = asyncio.run(get_top_albums(db_path=db_path))

    assert rows == [
        _row("album", "Record A", 2, 70, 2),
        _row("album", "Record B", 1, 10, 1),
    ]


@pytest.mark.parametrize(
    ("name_key", "default_name", "get_entity", "expected_extra"),
    [
        ("artist", "Alpha", get_top_artists, {"artist_id": None}),
        ("album", "Record A", get_top_albums, {}),
    ],
)
def test_get_top_entity_skips_empty_name(db_path, name_key, default_name, get_entity, expected_extra):
    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(_session("2024-03-24T01:00:00Z", "t1", **{name_key: ""}), db_path=db_path))
    asyncio.run(save_play_session(_session("2024-03-24T02:00:00Z", "t2", **{name_key: default_name}), db_path=db_path))

    rows = asyncio.run(get_entity(db_path=db_path))

    assert rows == [_row(name_key, default_name, 1, 30, 1, **expected_extra)]


@pytest.mark.parametrize(
    ("name_key", "get_entity"),
    [
        ("artist", get_top_artists),
        ("album", get_top_albums),
    ],
)
def test_get_top_entity_respects_limit(db_path, name_key, get_entity):
    asyncio.run(init_db(db_path))
    for i in range(5):
        asyncio.run(save_play_session(_session(f"2024-03-24T0{i}:00:00Z", f"t{i}", **{name_key: f"N{i}"}), db_path=db_path))

    rows = asyncio.run(get_entity(limit=2, db_path=db_path))

    assert len(rows) == 2


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists(mock_get):
    mock_get.return_value = [{"artist": "Alpha", "count": 5, "total_listen_sec": 120, "value": 5}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 200
    assert response.json() == [{"artist": "Alpha", "count": 5, "total_listen_sec": 120, "value": 5, "artist_id": None}]
    mock_get.assert_awaited_once_with(limit=10, days=0, timezone_name="UTC", metric="plays")


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums(mock_get):
    mock_get.return_value = [{"album": "Record A", "count": 3, "total_listen_sec": 90, "value": 3}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-albums")
    assert response.status_code == 200
    assert response.json() == [
        {"album": "Record A", "count": 3, "total_listen_sec": 90, "value": 3, "album_id": None}
    ]
    mock_get.assert_awaited_once_with(limit=10, days=0, timezone_name="UTC", metric="plays")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected_status", [
    (1, 200),
    (50, 200),
    (0, 422),
    (-1, 422),
    (51, 422),
])
@pytest.mark.parametrize("endpoint,mock_target", [
    ("/api/stats/top-artists", "src.routes.stats.get_top_artists"),
    ("/api/stats/top-albums", "src.routes.stats.get_top_albums"),
])
async def test_api_ranking_endpoint_limit_bounds(endpoint, mock_target, limit, expected_status):
    with patch(mock_target, new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"{endpoint}?limit={limit}")
        assert response.status_code == expected_status
        if expected_status == 200:
            mock_get.assert_awaited_once_with(limit=limit, days=0, timezone_name="UTC", metric="plays")


@pytest.mark.asyncio
async def test_api_top_artists_limit_invalid_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists?limit=abc")
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_artists", new_callable=AsyncMock, side_effect=RuntimeError("db unavailable"))
async def test_api_top_artists_database_error(mock_get):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 503
    assert response.json()["detail"] == "Stats temporarily unavailable"
    assert "db unavailable" not in response.text


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/top-artists")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums_requires_auth_when_token_configured(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/top-albums")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    mock_get.assert_not_awaited()
