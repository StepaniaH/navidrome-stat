"""Tests for the unified dashboard statistics window contract (Phase 1).

Covers:

* ``get_summary`` with finite windows: ``active_days``, averages and the
  current-vs-previous comparison metrics (including zero previous window).
* ``get_summary`` with ``days=0`` (all history): averages span over the
  actual min..max played date and previous/comparison fields are ``null``.
* Empty database resilience.
* Window filtering applied consistently by every aggregate query
  (players, transcoding, hourly, daily, top artists, top albums, history).
* API propagation: each historical endpoint forwards the ``days`` query to
  the matching database function and rejects invalid bounds with 422.
* Now-playing is NOT window-filtered.

All timestamps are synthetic and explicitly offset from the current UTC
clock so this suite has no dependence on real playback data.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from src.database import (
    init_db,
    save_play_session,
    get_summary,
    get_player_stats,
    get_transcoding_stats,
    get_hourly_stats,
    get_daily_stats,
    get_top_artists,
    get_top_albums,
    get_playback_history,
)
from src.main import app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# ----------------------------------------------------------------------------
# get_summary: empty / comparison / all-history semantics
# ----------------------------------------------------------------------------


def test_get_summary_empty_database_returns_null_safe(db_path):
    asyncio.run(init_db(db_path))
    summary = asyncio.run(get_summary(days=30, db_path=db_path))
    assert summary["total_plays"] == 0
    assert summary["total_listen_sec"] == 0
    assert summary["unique_tracks"] == 0
    assert summary["client_count"] == 0
    assert summary["active_days"] == 0
    # Zero previous -> percentages are null even with finite window.
    assert summary["previous_total_plays"] == 0
    assert summary["previous_total_listen_sec"] == 0
    assert summary["plays_change_pct"] is None
    assert summary["listen_change_pct"] is None
    assert summary["window_days"] == 30
    # With active_days=0 averages fall back to 0.
    assert summary["average_daily_plays"] == 0.0
    assert summary["average_daily_listen_sec"] == 0.0


def test_get_summary_finite_window_comparison_metrics(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Current window (last 7 days): 1 play, 30 sec.
    cur = _iso(now - timedelta(days=1))
    # Previous window (7..14 days ago): 2 plays, 60 sec each.
    prev1 = _iso(now - timedelta(days=10))
    prev2 = _iso(now - timedelta(days=12))
    # Far outside (40 days): must not affect either window.
    far = _iso(now - timedelta(days=40))

    for ts, dur in [
        (cur, 30),
        (prev1, 60),
        (prev2, 60),
        (far, 999),
    ]:
        asyncio.run(
            save_play_session(
                _session(ts, track_id=f"t-{ts}", duration_sec=dur),
                db_path=db_path,
            )
        )

    summary = asyncio.run(get_summary(days=7, db_path=db_path))

    assert summary["total_plays"] == 1
    assert summary["total_listen_sec"] == 30
    assert summary["active_days"] == 1
    assert summary["window_days"] == 7
    assert summary["previous_total_plays"] == 2
    assert summary["previous_total_listen_sec"] == 120
    # (1 - 2) / 2 * 100 == -50.0
    assert summary["plays_change_pct"] == -50.0
    # (30 - 120) / 120 * 100 == -75.0
    assert summary["listen_change_pct"] == -75.0
    # Averages use active_days=1.
    assert summary["average_daily_plays"] == 1.0
    assert summary["average_daily_listen_sec"] == 30.0


def test_get_summary_zero_previous_window_yields_null_pct(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    asyncio.run(
        save_play_session(
            _session(_iso(now - timedelta(days=1)), track_id="t1", duration_sec=45),
            db_path=db_path,
        )
    )
    # Single old play outside the previous window too (40 days).
    asyncio.run(
        save_play_session(
            _session(_iso(now - timedelta(days=40)), track_id="t2", duration_sec=10),
            db_path=db_path,
        )
    )

    summary = asyncio.run(get_summary(days=7, db_path=db_path))
    assert summary["total_plays"] == 1
    assert summary["previous_total_plays"] == 0
    assert summary["previous_total_listen_sec"] == 0
    assert summary["plays_change_pct"] is None
    assert summary["listen_change_pct"] is None


def test_get_summary_all_history_disables_comparison(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    rows = [
        (_iso(now - timedelta(days=1)), 30, "a"),
        (_iso(now - timedelta(days=5)), 40, "b"),
        (_iso(now - timedelta(days=20)), 50, "c"),
    ]
    for ts, dur, tid in rows:
        asyncio.run(
            save_play_session(
                _session(ts, track_id=f"t-{tid}", duration_sec=dur),
                db_path=db_path,
            )
        )

    summary = asyncio.run(get_summary(days=0, db_path=db_path))
    assert summary["total_plays"] == 3
    assert summary["total_listen_sec"] == 120
    assert summary["active_days"] == 3
    assert summary["window_days"] is None
    # All-history never compares.
    assert summary["previous_total_plays"] is None
    assert summary["previous_total_listen_sec"] is None
    assert summary["plays_change_pct"] is None
    assert summary["listen_change_pct"] is None
    # Averages use span min..max date inclusive (20 days).
    assert summary["average_daily_plays"] == round(3 / 20, 2)
    assert summary["average_daily_listen_sec"] == round(120 / 20, 2)


def test_get_summary_all_history_single_day_span_is_one(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    asyncio.run(
        save_play_session(
            _session(_iso(now), track_id="t1", duration_sec=30),
            db_path=db_path,
        )
    )
    asyncio.run(
        save_play_session(
            _session(_iso(now), track_id="t2", duration_sec=20),
            db_path=db_path,
        )
    )
    summary = asyncio.run(get_summary(days=0, db_path=db_path))
    # Span is min..max date inclusive = 1 day.
    assert summary["average_daily_plays"] == 2.0
    assert summary["average_daily_listen_sec"] == 50.0


# ----------------------------------------------------------------------------
# Aggregate query helpers respect the window
# ----------------------------------------------------------------------------


def _seed_window_data(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    recent = _iso(now - timedelta(days=1))
    mid = _iso(now - timedelta(days=20))
    far = _iso(now - timedelta(days=80))
    for ts, tid, artist, album, client, trans in [
        (recent, "r1", "ArtistA", "AlbumA", "Web", 0),
        (mid, "m1", "ArtistB", "AlbumB", "Mobile", 1),
        (far, "f1", "ArtistC", "AlbumC", "Distant", 0),
    ]:
        asyncio.run(
            save_play_session(
                _session(
                    ts,
                    track_id=tid,
                    artist=artist,
                    album=album,
                    client=client,
                    transcoding=trans,
                ),
                db_path=db_path,
            )
        )


def test_get_player_stats_respects_window(db_path):
    _seed_window_data(db_path)
    all_rows = {r["client_name"]: r["count"] for r in asyncio.run(get_player_stats(days=0, db_path=db_path))}
    assert all_rows == {"Web": 1, "Mobile": 1, "Distant": 1}
    seven = {r["client_name"]: r["count"] for r in asyncio.run(get_player_stats(days=7, db_path=db_path))}
    assert seven == {"Web": 1}
    ninety = {r["client_name"]: r["count"] for r in asyncio.run(get_player_stats(days=90, db_path=db_path))}
    # 90-day window excludes the 80-day-old far row? 80 < 90 so it IS included.
    assert ninety == {"Web": 1, "Mobile": 1, "Distant": 1}


def test_get_transcoding_stats_respects_window(db_path):
    _seed_window_data(db_path)
    all_rows = {r["is_transcoding"]: r["count"] for r in asyncio.run(get_transcoding_stats(days=0, db_path=db_path))}
    assert all_rows == {0: 2, 1: 1}
    seven = {r["is_transcoding"]: r["count"] for r in asyncio.run(get_transcoding_stats(days=7, db_path=db_path))}
    assert seven == {0: 1}


def test_get_hourly_stats_respects_window(db_path):
    _seed_window_data(db_path)
    all_count = sum(r["count"] for r in asyncio.run(get_hourly_stats(days=0, db_path=db_path)))
    seven_count = sum(r["count"] for r in asyncio.run(get_hourly_stats(days=7, db_path=db_path)))
    assert all_count == 3
    assert seven_count == 1


def test_get_daily_stats_all_history_includes_every_date(db_path):
    _seed_window_data(db_path)
    all_rows = asyncio.run(get_daily_stats(days=0, db_path=db_path))
    # All-history spans from min to max local played date (UTC). Seed date
    # offsets are today-1, today-20 and today-80, so the inclusive span is 80
    # calendar days, zero-filled between plays.
    assert len(all_rows) == 80
    seven = asyncio.run(get_daily_stats(days=7, db_path=db_path))
    assert len(seven) == 7
    ninety = asyncio.run(get_daily_stats(days=90, db_path=db_path))
    assert len(ninety) == 90


def test_get_top_artists_respects_window(db_path):
    _seed_window_data(db_path)
    all_rows = {r["artist"]: r["count"] for r in asyncio.run(get_top_artists(limit=50, days=0, db_path=db_path))}
    assert all_rows == {"ArtistA": 1, "ArtistB": 1, "ArtistC": 1}
    seven = {r["artist"]: r["count"] for r in asyncio.run(get_top_artists(limit=50, days=7, db_path=db_path))}
    assert seven == {"ArtistA": 1}
    ninety = {r["artist"]: r["count"] for r in asyncio.run(get_top_artists(limit=50, days=90, db_path=db_path))}
    assert ninety == {"ArtistA": 1, "ArtistB": 1, "ArtistC": 1}


def test_get_top_albums_respects_window(db_path):
    _seed_window_data(db_path)
    all_rows = {r["album"]: r["count"] for r in asyncio.run(get_top_albums(limit=50, days=0, db_path=db_path))}
    assert all_rows == {"AlbumA": 1, "AlbumB": 1, "AlbumC": 1}
    seven = {r["album"]: r["count"] for r in asyncio.run(get_top_albums(limit=50, days=7, db_path=db_path))}
    assert seven == {"AlbumA": 1}


def test_get_playback_history_respects_window(db_path):
    _seed_window_data(db_path)
    all_rows = asyncio.run(get_playback_history(limit=50, days=0, db_path=db_path))
    assert len(all_rows) == 3
    seven = asyncio.run(get_playback_history(limit=50, days=7, db_path=db_path))
    assert len(seven) == 1
    assert seven[0]["title"] == "Song r1"


# ----------------------------------------------------------------------------
# API days= propagation and bounds
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,target,mock_path,kwargs",
    [
        ("/api/stats/summary?days=30", "get_summary", "src.main.get_summary", {"days": 30, "timezone_name": "UTC"}),
        ("/api/stats/summary?days=0", "get_summary", "src.main.get_summary", {"days": 0, "timezone_name": "UTC"}),
        ("/api/stats/players?days=7", "get_player_stats", "src.main.get_player_stats", {"days": 7, "timezone_name": "UTC"}),
        ("/api/stats/transcoding?days=30", "get_transcoding_stats", "src.main.get_transcoding_stats", {"days": 30, "timezone_name": "UTC"}),
        ("/api/stats/hourly?days=90", "get_hourly_stats", "src.main.get_hourly_stats", {"days": 90, "timezone_name": "UTC"}),
        ("/api/stats/daily?days=90", "get_daily_stats", "src.main.get_daily_stats", {"days": 90, "timezone_name": "UTC"}),
        ("/api/stats/top-artists?limit=10&days=30", "get_top_artists", "src.main.get_top_artists", {"limit": 10, "days": 30, "timezone_name": "UTC"}),
        ("/api/stats/top-albums?limit=10&days=30", "get_top_albums", "src.main.get_top_albums", {"limit": 10, "days": 30, "timezone_name": "UTC"}),
        ("/api/stats/history?limit=10&days=30", "get_playback_history", "src.main.get_playback_history", {"limit": 10, "days": 30, "timezone_name": "UTC"}),
    ],
)
async def test_historical_endpoints_propagate_days(endpoint, target, mock_path, kwargs):
    mock = AsyncMock()
    if target == "get_summary":
        mock.return_value = {
            "total_plays": 0,
            "total_listen_sec": 0,
            "unique_tracks": 0,
            "client_count": 0,
            "active_days": 0,
            "average_daily_plays": 0.0,
            "average_daily_listen_sec": 0.0,
            "previous_total_plays": None,
            "previous_total_listen_sec": None,
            "plays_change_pct": None,
            "listen_change_pct": None,
            "window_days": None,
        }
    else:
        mock.return_value = []
    with patch(mock_path, mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(endpoint)
    assert response.status_code == 200, response.text
    mock.assert_awaited_once_with(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/stats/summary?days=5",
        "/api/stats/summary?days=91",
        "/api/stats/summary?days=-1",
        "/api/stats/players?days=1",
        "/api/stats/transcoding?days=6",
        "/api/stats/hourly?days=100",
        "/api/stats/daily?days=6",
        "/api/stats/daily?days=91",
        "/api/stats/top-artists?limit=10&days=4",
        "/api/stats/top-albums?limit=10&days=200",
        "/api/stats/history?limit=10&days=3",
    ],
)
async def test_historical_endpoints_reject_invalid_days(endpoint):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(endpoint)
    assert response.status_code == 422, endpoint


@pytest.mark.asyncio
@patch("src.main.get_summary", new_callable=AsyncMock)
async def test_summary_response_includes_comparison_fields(mock_get):
    mock_get.return_value = {
        "total_plays": 100,
        "total_listen_sec": 3600,
        "unique_tracks": 50,
        "client_count": 3,
        "active_days": 28,
        "average_daily_plays": 3.57,
        "average_daily_listen_sec": 128.57,
        "previous_total_plays": 80,
        "previous_total_listen_sec": 3000,
        "plays_change_pct": 25.0,
        "listen_change_pct": 20.0,
        "window_days": 30,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/summary?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["total_plays"] == 100
    assert body["active_days"] == 28
    assert body["average_daily_plays"] == 3.57
    assert body["previous_total_plays"] == 80
    assert body["plays_change_pct"] == 25.0
    assert body["listen_change_pct"] == 20.0
    assert body["window_days"] == 30


@pytest.mark.asyncio
@patch("src.main.get_now_playing_data", new_callable=AsyncMock, create=True)
async def test_now_playing_endpoint_accepts_no_days_param(_mock):
    # now-playing stays real-time and must not declare a days query.
    import inspect
    from src.main import api_now_playing

    sig = inspect.signature(api_now_playing)
    assert "days" not in sig.parameters
    assert "timezone" not in sig.parameters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,target,mock_path,kwargs",
    [
        (
            "/api/stats/summary?days=30&timezone=Asia/Shanghai",
            "get_summary",
            "src.main.get_summary",
            {"days": 30, "timezone_name": "Asia/Shanghai"},
        ),
        (
            "/api/stats/daily?days=30&timezone=America/New_York",
            "get_daily_stats",
            "src.main.get_daily_stats",
            {"days": 30, "timezone_name": "America/New_York"},
        ),
        (
            "/api/stats/heatmap?days=90&timezone=Europe/London",
            "get_weekday_hour_stats",
            "src.main.get_weekday_hour_stats",
            {"days": 90, "timezone_name": "Europe/London"},
        ),
        (
            "/api/stats/heatmap?days=0&timezone=UTC",
            "get_weekday_hour_stats",
            "src.main.get_weekday_hour_stats",
            {"days": 0, "timezone_name": "UTC"},
        ),
        (
            "/api/stats/heatmap?timezone=Asia/Shanghai",
            "get_weekday_hour_stats",
            "src.main.get_weekday_hour_stats",
            {"days": 30, "timezone_name": "Asia/Shanghai"},
        ),
    ],
)
async def test_historical_endpoints_propagate_timezone(endpoint, target, mock_path, kwargs):
    mock = AsyncMock()
    if target == "get_summary":
        mock.return_value = {
            "total_plays": 0,
            "total_listen_sec": 0,
            "unique_tracks": 0,
            "client_count": 0,
            "active_days": 0,
            "average_daily_plays": 0.0,
            "average_daily_listen_sec": 0.0,
            "previous_total_plays": None,
            "previous_total_listen_sec": None,
            "plays_change_pct": None,
            "listen_change_pct": None,
            "window_days": None,
        }
    else:
        mock.return_value = []
    with patch(mock_path, mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(endpoint)
    assert response.status_code == 200, response.text
    mock.assert_awaited_once_with(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/stats/summary?timezone=Invalid/Zone",
        "/api/stats/players?timezone=NotAZone",
        "/api/stats/transcoding?timezone=Foo/Bar",
        "/api/stats/hourly?timezone=Local",
        "/api/stats/daily?timezone=America/New_YorkFake",
        "/api/stats/heatmap?timezone=Asia/ShanghaiFake",
        "/api/stats/top-artists?timezone=Europe Rome",
        "/api/stats/top-albums?timezone=UTC%2B02:00",
        "/api/stats/history?timezone=%20",
    ],
)
async def test_historical_endpoints_reject_invalid_timezone(endpoint):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(endpoint)
    assert response.status_code == 422, endpoint
    assert response.json()["detail"] == "timezone must be a valid IANA timezone name"


@pytest.mark.asyncio
async def test_heatmap_endpoint_default_window_is_30_days():
    import inspect
    from src.main import api_weekday_hour_stats

    sig = inspect.signature(api_weekday_hour_stats)
    days_default = sig.parameters["days"].default
    assert getattr(days_default, "default", None) == 30
    tz_default = sig.parameters["timezone"].default
    assert getattr(tz_default, "default", None) == "UTC"