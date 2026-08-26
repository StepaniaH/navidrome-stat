"""Tests for rankings and client/transcoding aggregates."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import (
    get_player_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    init_db,
    save_play_session,
)
from src.main import app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _session(
    played_at: str,
    *,
    track_id: str = "t1",
    artist: str = "Artist",
    album: str = "Album",
    client: str = "Web Player",
    duration_sec: int = 30,
    transcoding: int = 0,
    username: str = "testuser",
):
    return {
        "last_seen_at": played_at,
        "username": username,
        "client_name": client,
        "track_id": track_id,
        "title": f"Song {track_id}",
        "artist": artist,
        "album": album,
        "is_transcoding": transcoding,
        "duration_sec": duration_sec,
    }


def test_top_artists_listen_time_ranks_by_seconds(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Fewer plays but more listening time puts Beta first for this metric.
    for i in range(10):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"a{i}", artist="Alpha", duration_sec=10), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="b1", artist="Beta", duration_sec=600), db_path=db_path))

    rows = asyncio.run(get_top_artists(limit=10, days=0, metric="listen_time", db_path=db_path))

    assert [r["artist"] for r in rows] == ["Beta", "Alpha"]
    assert rows[0]["value"] == 600
    assert rows[1]["value"] == 100
    assert rows[0]["count"] == 1
    assert rows[1]["count"] == 10


def test_top_albums_listen_time_ranks_by_seconds(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    for i in range(8):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"a{i}", album="Album A", duration_sec=5), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="b1", album="Album B", duration_sec=300), db_path=db_path))

    rows = asyncio.run(get_top_albums(limit=10, days=0, metric="listen_time", db_path=db_path))

    assert [r["album"] for r in rows] == ["Album B", "Album A"]
    assert rows[0]["value"] == 300
    assert rows[1]["value"] == 40


def test_top_artists_ties_break_by_name_asc_under_plays(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Equal counts sort by name.
    for artist in ("Zephyr", "Alpha", "Mike"):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"t-{artist}", artist=artist, duration_sec=10), db_path=db_path))
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"t-{artist}-2", artist=artist, duration_sec=10), db_path=db_path))

    rows = asyncio.run(get_top_artists(limit=10, days=0, db_path=db_path))

    assert [r["artist"] for r in rows] == ["Alpha", "Mike", "Zephyr"]
    assert all(r["count"] == 2 for r in rows)


def test_top_artists_ties_break_by_name_asc_under_listen_time(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Equal listening times sort by name, not insertion order.
    for artist in ("Zulu", "Alpha", "Mike"):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"{artist}-1", artist=artist, duration_sec=30), db_path=db_path))
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"{artist}-2", artist=artist, duration_sec=30), db_path=db_path))

    rows = asyncio.run(get_top_artists(limit=10, days=0, metric="listen_time", db_path=db_path))

    assert [r["artist"] for r in rows] == ["Alpha", "Mike", "Zulu"]
    assert all(r["value"] == 60 for r in rows)


def test_top_albums_listen_time_tie_break_by_name_asc(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    for album in ("Zeta", "Alpha"):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"{album}-1", album=album, duration_sec=40), db_path=db_path))

    rows = asyncio.run(get_top_albums(limit=10, days=0, metric="listen_time", db_path=db_path))

    assert [r["album"] for r in rows] == ["Alpha", "Zeta"]


def test_invalid_metric_raises_value_error_db_layer(db_path):
    asyncio.run(init_db(db_path))
    with pytest.raises(ValueError):
        asyncio.run(get_top_artists(limit=10, days=0, metric="invalid", db_path=db_path))


def test_top_artists_listen_time_respects_timezone_window(db_path):
    # Timezone changes the cutoff boundary, not accumulated seconds.
    asyncio.run(init_db(db_path))
    now = _now()
    asyncio.run(save_play_session(_session(_iso(now - timedelta(hours=2)), track_id="b1", artist="Beta", duration_sec=600), db_path=db_path))

    rows = asyncio.run(get_top_artists(limit=10, days=7, timezone_name="Asia/Shanghai", metric="listen_time", db_path=db_path))

    assert rows == [{"artist": "Beta", "count": 1, "total_listen_sec": 600, "value": 600}]


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists_propagates_metric_listen_time(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-artists?metric=listen_time")
    assert response.status_code == 200
    mock_get.assert_awaited_once_with(limit=10, days=0, timezone_name="UTC", metric="listen_time")


@pytest.mark.asyncio
@patch("src.routes.stats.get_top_albums", new_callable=AsyncMock)
async def test_api_top_albums_propagates_metric_listen_time(mock_get):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/top-albums?days=30&metric=listen_time&timezone=Asia/Shanghai")
    assert response.status_code == 200
    mock_get.assert_awaited_once_with(limit=10, days=30, timezone_name="Asia/Shanghai", metric="listen_time")


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["listen_time"])
@patch("src.routes.stats.get_top_artists", new_callable=AsyncMock)
async def test_api_top_artists_accepts_valid_metrics(mock_get, metric):
    mock_get.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/top-artists?metric={metric}")
    assert response.status_code == 200
    mock_get.assert_awaited_once_with(limit=10, days=0, timezone_name="UTC", metric=metric)


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["invalid", "PLAYS"])
async def test_api_top_artists_rejects_invalid_metric(metric):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/stats/top-artists?metric={metric}")
    assert response.status_code == 422
    assert response.json()["detail"] == "metric must be one of: plays, listen_time"


@pytest.mark.parametrize(
    ("query_func", "kwargs"),
    [
        pytest.param(get_top_artists, {"metric": "plays"}, id="top-artists-plays"),
        pytest.param(get_top_artists, {"metric": "listen_time"}, id="top-artists-listen-time"),
        pytest.param(get_top_albums, {"metric": "plays"}, id="top-albums-plays"),
        pytest.param(get_top_albums, {"metric": "listen_time"}, id="top-albums-listen-time"),
        pytest.param(get_player_stats, {}, id="player"),
        pytest.param(get_transcoding_stats, {}, id="transcoding"),
    ],
)
def test_ranking_queries_return_no_rows_on_fresh_database(db_path, query_func, kwargs):
    asyncio.run(init_db(db_path))
    assert asyncio.run(query_func(db_path=db_path, **kwargs)) == []


def _player_row(client_name, count, total_listen_sec, average_listen_sec, transcoded_count, transcoding_rate_pct):
    return {
        "client_name": client_name,
        "count": count,
        "total_listen_sec": total_listen_sec,
        "average_listen_sec": average_listen_sec,
        "transcoded_count": transcoded_count,
        "transcoding_rate_pct": transcoding_rate_pct,
    }


def test_player_stats_extended_fields_and_ordering(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Web: 3 plays (60s) including 1 transcoded. Transcoded = 1, rate = 33.33
    asyncio.run(save_play_session(_session(_iso(now), track_id="w1", client="Web", duration_sec=10, transcoding=0), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="w2", client="Web", duration_sec=20, transcoding=1), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="w3", client="Web", duration_sec=30, transcoding=0), db_path=db_path))
    # Mobile: 2 plays (50s), both transcoded. Transcoded = 2, rate = 100.0
    asyncio.run(save_play_session(_session(_iso(now), track_id="m1", client="Mobile", duration_sec=20, transcoding=1), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="m2", client="Mobile", duration_sec=30, transcoding=1), db_path=db_path))

    rows = asyncio.run(get_player_stats(days=0, db_path=db_path))

    assert rows == [
        _player_row("Web", 3, 60, round(60 / 3, 2), 1, round(1 / 3 * 100, 2)),
        _player_row("Mobile", 2, 50, round(50 / 2, 2), 2, 100.0),
    ]


def test_player_stats_tie_breaks_by_client_name_asc(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Equal counts sort by name.
    for client in ("Zeta", "Alpha", "Mike"):
        asyncio.run(save_play_session(_session(_iso(now), track_id=f"{client}-1", client=client, duration_sec=30), db_path=db_path))

    rows = asyncio.run(get_player_stats(days=0, db_path=db_path))

    assert [r["client_name"] for r in rows] == ["Alpha", "Mike", "Zeta"]
    assert all(r["count"] == 1 for r in rows)


def test_player_stats_groups_null_and_empty_separately_and_sorts_above_nonempty(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Count ordering puts BigClient first; empty and null remain separate tied groups.
    asyncio.run(save_play_session(_session(_iso(now), track_id="a1", client="BigClient", duration_sec=30), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="a2", client="BigClient", duration_sec=30), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="e1", client="", duration_sec=10), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="n1", client=None, duration_sec=10), db_path=db_path))

    rows = asyncio.run(get_player_stats(days=0, db_path=db_path))

    assert rows[0]["client_name"] == "BigClient"
    assert rows[0]["count"] == 2
    assert {rows[1]["client_name"], rows[2]["client_name"]} == {"", None}
    assert rows[1]["count"] == 1
    assert rows[2]["count"] == 1


def test_transcoding_stats_extended_fields_and_percentages(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Direct: 3 plays, 90 sec. Transcoded: 1 play, 60 sec. Total plays = 4,
    # total listen = 150 sec.
    asyncio.run(save_play_session(_session(_iso(now), track_id="d1", client="X", duration_sec=30, transcoding=0), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="d2", client="X", duration_sec=30, transcoding=0), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="d3", client="X", duration_sec=30, transcoding=0), db_path=db_path))
    asyncio.run(save_play_session(_session(_iso(now), track_id="t1", client="X", duration_sec=60, transcoding=1), db_path=db_path))

    rows = asyncio.run(get_transcoding_stats(days=0, db_path=db_path))

    # Query order is unspecified, so compare rows by mode.
    by_mode = {r["is_transcoding"]: r for r in rows}
    assert by_mode[0] == {
        "is_transcoding": 0,
        "count": 3,
        "total_listen_sec": 90,
        "plays_pct": round(3 / 4 * 100, 2),
        "listen_sec_pct": round(90 / 150 * 100, 2),
    }
    assert by_mode[1] == {
        "is_transcoding": 1,
        "count": 1,
        "total_listen_sec": 60,
        "plays_pct": round(1 / 4 * 100, 2),
        "listen_sec_pct": round(60 / 150 * 100, 2),
    }


def test_transcoding_stats_single_mode_pct_is_100(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    asyncio.run(save_play_session(_session(_iso(now), track_id="t1", client="X", duration_sec=42, transcoding=1), db_path=db_path))

    rows = asyncio.run(get_transcoding_stats(days=0, db_path=db_path))

    assert rows == [{
        "is_transcoding": 1,
        "count": 1,
        "total_listen_sec": 42,
        "plays_pct": 100.0,
        "listen_sec_pct": 100.0,
    }]
