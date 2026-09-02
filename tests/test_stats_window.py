"""Tests for dashboard statistics windows and API propagation."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from src.dashboard_cache import dashboard_snapshot_cache
from src.database import (
    _previous_window_bounds,
    _window_bounds,
    get_daily_stats,
    get_hourly_stats,
    get_playback_history,
    get_player_stats,
    get_short_play_stats,
    get_summary,
    get_time_bucket_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    init_db,
    save_play_attempt,
    save_play_session,
    utc_instant,
)
from src.main import app
from src.stats_scope import StatsScope


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


def test_get_summary_empty_database_returns_null_safe(db_path):
    asyncio.run(init_db(db_path))
    summary = asyncio.run(get_summary(days=30, db_path=db_path))
    assert summary["total_plays"] == 0
    assert summary["total_listen_sec"] == 0
    assert summary["unique_tracks"] == 0
    assert summary["client_count"] == 0
    assert summary["active_days"] == 0
    assert summary["previous_total_plays"] == 0
    assert summary["previous_total_listen_sec"] == 0
    assert summary["plays_change_pct"] is None
    assert summary["listen_change_pct"] is None
    assert summary["window_days"] == 30
    assert summary["average_daily_plays"] == 0.0
    assert summary["average_daily_listen_sec"] == 0.0


def test_get_summary_finite_window_comparison_metrics(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    # Seed the current, previous, and an excluded window.
    cur = _iso(now - timedelta(days=1))
    prev1 = _iso(now - timedelta(days=10))
    prev2 = _iso(now - timedelta(days=12))
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
    assert summary["plays_change_pct"] == -50.0
    assert summary["listen_change_pct"] == -75.0
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


def test_get_summary_filters_by_username(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    ts = _iso(now - timedelta(days=1))
    asyncio.run(
        save_play_session(
            _session(ts, track_id="a1", username="alice", duration_sec=30),
            db_path=db_path,
        )
    )
    asyncio.run(
        save_play_session(
            _session(ts, track_id="b1", username="bob", duration_sec=90),
            db_path=db_path,
        )
    )

    summary = asyncio.run(get_summary(days=7, username="alice", db_path=db_path))
    assert summary["total_plays"] == 1
    assert summary["total_listen_sec"] == 30


def test_get_short_play_stats_filters_username_across_tables(db_path):
    asyncio.run(init_db(db_path))
    now = _now()
    ts = _iso(now - timedelta(days=1))
    for username in ("alice", "bob"):
        asyncio.run(
            save_play_attempt(
                {
                    "last_seen_at": ts,
                    "username": username,
                    "client_name": "Web",
                    "track_id": f"s-{username}",
                    "title": "Skipped",
                    "artist": "Artist",
                    "album": "Album",
                    "is_transcoding": 0,
                    "duration_sec": 5,
                    "outcome": "short_play",
                },
                db_path=db_path,
            )
        )
    asyncio.run(
        save_play_session(
            _session(ts, track_id="a1", username="alice", duration_sec=40),
            db_path=db_path,
        )
    )
    asyncio.run(
        save_play_session(
            _session(ts, track_id="b1", username="bob", duration_sec=40),
            db_path=db_path,
        )
    )

    stats = asyncio.run(get_short_play_stats(days=7, username="alice", db_path=db_path))
    assert stats["short_count"] == 1
    assert stats["counted_count"] == 1
    assert stats["attempt_count"] == 2


def test_previous_window_uses_local_calendar_days_across_dst(monkeypatch, db_path):
    """Preset previous windows follow local midnights, not UTC-span subtraction."""
    import src.windows

    tz = ZoneInfo("America/New_York")
    frozen = datetime(2024, 3, 12, 15, 0, tzinfo=tz)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen.astimezone(timezone.utc).replace(tzinfo=None)
            return frozen.astimezone(tz)

    monkeypatch.setattr(src.windows, "datetime", FrozenDateTime)

    start, end = _previous_window_bounds(7, tz)
    expected_start = utc_instant(datetime(2024, 2, 28, 0, 0, tzinfo=tz))
    expected_end = utc_instant(datetime(2024, 3, 6, 0, 0, tzinfo=tz))
    assert (start, end) == (expected_start, expected_end)

    current_start, current_end = _window_bounds(7, tz)
    utc_span = datetime.fromisoformat(current_end.replace(" ", "T") + "+00:00") - (
        datetime.fromisoformat(current_start.replace(" ", "T") + "+00:00")
    )
    naive_previous_start = datetime.fromisoformat(
        current_start.replace(" ", "T") + "+00:00"
    ) - utc_span
    assert utc_instant(naive_previous_start) != start

    asyncio.run(init_db(db_path))
    # 2024-02-28 00:30 EST is inside the local previous window, but would sit
    # before a UTC-span previous start (2024-02-28 01:00 EST).
    asyncio.run(
        save_play_session(
            _session("2024-02-28T05:30:00+00:00", track_id="dst-previous"),
            db_path=db_path,
        )
    )
    asyncio.run(
        save_play_session(
            _session("2024-03-12T16:00:00+00:00", track_id="dst-current"),
            db_path=db_path,
        )
    )
    summary = asyncio.run(
        get_summary(days=7, timezone_name="America/New_York", db_path=db_path)
    )
    assert summary["total_plays"] == 1
    assert summary["previous_total_plays"] == 1


def test_custom_date_window_filters_and_zero_fills_inclusive_dates(db_path):
    asyncio.run(init_db(db_path))
    for played_at, track_id in [
        ("2026-01-01T12:00:00Z", "previous"),
        ("2026-01-03T12:00:00Z", "current-a"),
        ("2026-01-05T23:59:00Z", "current-b"),
        ("2026-01-06T00:00:00Z", "outside"),
    ]:
        asyncio.run(
            save_play_session(
                _session(played_at, track_id=track_id),
                db_path=db_path,
            )
        )

    summary = asyncio.run(
        get_summary(
            days=30,
            timezone_name="UTC",
            start_date=date(2026, 1, 3),
            end_date=date(2026, 1, 5),
            db_path=db_path,
        )
    )
    buckets = asyncio.run(
        get_time_bucket_stats(
            days=30,
            timezone_name="UTC",
            start_date=date(2026, 1, 3),
            end_date=date(2026, 1, 5),
            db_path=db_path,
        )
    )

    assert summary["total_plays"] == 2
    assert summary["window_days"] == 3
    assert summary["previous_total_plays"] == 1
    assert buckets["daily"] == [
        {"date": "2026-01-03", "count": 1},
        {"date": "2026-01-04", "count": 0},
        {"date": "2026-01-05", "count": 1},
    ]


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
    assert summary["previous_total_plays"] is None
    assert summary["previous_total_listen_sec"] is None
    assert summary["plays_change_pct"] is None
    assert summary["listen_change_pct"] is None
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
    assert summary["average_daily_plays"] == 2.0
    assert summary["average_daily_listen_sec"] == 50.0


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
    # The inclusive span from today-80 through today-1 contains 80 dates.
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


def test_playback_history_uses_played_at_instead_of_import_order(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(
        save_play_session(
            _session("2026-01-02T12:00:00Z", track_id="same-track"),
            db_path=db_path,
        )
    )
    imported_old = _session("2025-01-02T12:00:00Z", track_id="same-track")
    imported_old["title"] = "Older imported title"
    asyncio.run(save_play_session(imported_old, db_path=db_path))

    rows = asyncio.run(get_playback_history(limit=10, days=0, db_path=db_path))

    assert len(rows) == 1
    assert rows[0]["title"] == "Song same-track"
    assert rows[0]["last_played_at"] == "2026-01-02T12:00:00Z"
    assert rows[0]["play_count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,target,mock_path,kwargs",
    [
        ("/api/stats/summary?days=30", "get_summary", "src.routes.stats.get_summary", {"days": 30, "timezone_name": "UTC"}),
        ("/api/stats/summary?days=0", "get_summary", "src.routes.stats.get_summary", {"days": 0, "timezone_name": "UTC"}),
        ("/api/stats/players?days=7", "get_player_stats", "src.routes.stats.get_player_stats", {"days": 7, "timezone_name": "UTC"}),
        ("/api/stats/transcoding?days=30", "get_transcoding_stats", "src.routes.stats.get_transcoding_stats", {"days": 30, "timezone_name": "UTC"}),
        ("/api/stats/hourly?days=90", "get_hourly_stats", "src.routes.stats.get_hourly_stats", {"days": 90, "timezone_name": "UTC"}),
        ("/api/stats/daily?days=90", "get_daily_stats", "src.routes.stats.get_daily_stats", {"days": 90, "timezone_name": "UTC"}),
        ("/api/stats/top-artists?limit=10&days=30", "get_top_artists", "src.routes.stats.get_top_artists", {"limit": 10, "days": 30, "timezone_name": "UTC", "metric": "plays", "artist_mode": "combined"}),
        ("/api/stats/top-albums?limit=10&days=30", "get_top_albums", "src.routes.stats.get_top_albums", {"limit": 10, "days": 30, "timezone_name": "UTC", "metric": "plays"}),
        ("/api/stats/history?limit=10&days=30", "get_playback_history", "src.routes.stats.get_playback_history", {"limit": 10, "days": 30, "timezone_name": "UTC"}),
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
@patch("src.routes.stats.get_summary", new_callable=AsyncMock)
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
@pytest.mark.parametrize(
    "endpoint,target,mock_path,kwargs",
    [
        (
            "/api/stats/summary?days=30&timezone=Asia/Shanghai",
            "get_summary",
            "src.routes.stats.get_summary",
            {"days": 30, "timezone_name": "Asia/Shanghai"},
        ),
        (
            "/api/stats/daily?days=30&timezone=America/New_York",
            "get_daily_stats",
            "src.routes.stats.get_daily_stats",
            {"days": 30, "timezone_name": "America/New_York"},
        ),
        (
            "/api/stats/heatmap?days=90&timezone=Europe/London",
            "get_weekday_hour_stats",
            "src.routes.stats.get_weekday_hour_stats",
            {"days": 90, "timezone_name": "Europe/London"},
        ),
        (
            "/api/stats/heatmap?days=0&timezone=UTC",
            "get_weekday_hour_stats",
            "src.routes.stats.get_weekday_hour_stats",
            {"days": 0, "timezone_name": "UTC"},
        ),
        (
            "/api/stats/heatmap?timezone=Asia/Shanghai",
            "get_weekday_hour_stats",
            "src.routes.stats.get_weekday_hour_stats",
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


def _username_mock_return(target):
    if target == "get_summary":
        return {
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
    if target == "get_short_play_stats":
        return {
            "short_count": 0,
            "counted_count": 0,
            "attempt_count": 0,
            "short_listen_sec": 0,
            "short_play_rate_pct": 0.0,
        }
    return []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,target,mock_path,kwargs",
    [
        (
            "/api/stats/summary?days=30&username=alice",
            "get_summary",
            "src.routes.stats.get_summary",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/players?days=30&username=alice",
            "get_player_stats",
            "src.routes.stats.get_player_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/transcoding?days=30&username=alice",
            "get_transcoding_stats",
            "src.routes.stats.get_transcoding_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/short-plays?days=30&username=alice",
            "get_short_play_stats",
            "src.routes.stats.get_short_play_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/hourly?days=30&username=alice",
            "get_hourly_stats",
            "src.routes.stats.get_hourly_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/daily?days=30&username=alice",
            "get_daily_stats",
            "src.routes.stats.get_daily_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/heatmap?days=30&username=alice",
            "get_weekday_hour_stats",
            "src.routes.stats.get_weekday_hour_stats",
            {"days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/history?limit=10&days=30&username=alice",
            "get_playback_history",
            "src.routes.stats.get_playback_history",
            {"limit": 10, "days": 30, "timezone_name": "UTC", "username": "alice"},
        ),
        (
            "/api/stats/top-artists?limit=10&days=30&username=alice",
            "get_top_artists",
            "src.routes.stats.get_top_artists",
            {"limit": 10, "days": 30, "timezone_name": "UTC", "metric": "plays", "username": "alice", "artist_mode": "combined"},
        ),
        (
            "/api/stats/top-albums?limit=10&days=30&username=alice",
            "get_top_albums",
            "src.routes.stats.get_top_albums",
            {"limit": 10, "days": 30, "timezone_name": "UTC", "metric": "plays", "username": "alice"},
        ),
    ],
)
async def test_historical_endpoints_propagate_username(endpoint, target, mock_path, kwargs):
    mock = AsyncMock()
    mock.return_value = _username_mock_return(target)
    with patch(mock_path, mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(endpoint)
    assert response.status_code == 200, response.text
    mock.assert_awaited_once_with(**kwargs)


@pytest.mark.asyncio
async def test_dashboard_propagates_username():
    await dashboard_snapshot_cache.invalidate()
    build = AsyncMock(return_value=_dashboard_snapshot())
    with patch("src.stats_service.StatsService._build_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/stats/dashboard?days=30&username=bob")
    assert response.status_code == 200
    build.assert_awaited_once_with(StatsScope.create(
        days=30,
        timezone_name="UTC",
        metric="plays",
        source_id=None,
        start_date=None,
        end_date=None,
        username="bob",
    ))


def _dashboard_snapshot():
    return {
        "summary": {
            "total_plays": 1,
            "total_listen_sec": 120,
            "unique_tracks": 1,
            "client_count": 1,
        },
        "players": [],
        "transcoding": [],
        "hourly": [],
        "daily": [],
        "heatmap": [],
        "history": [],
        "servers": [],
        "available_servers": [],
        "top_artists": [],
        "top_albums": [],
    }


@pytest.mark.asyncio
async def test_users_endpoint_requires_token_when_auth_enabled(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/users")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
async def test_users_endpoint_returns_distinct_usernames_nocase(isolated_db):
    await init_db(isolated_db)
    ts = _iso(_now() - timedelta(days=1))
    await save_play_session(_session(ts, track_id="u1", username="bob"), isolated_db)
    await save_play_session(_session(ts, track_id="u2", username="Alice"), isolated_db)
    await save_play_session(_session(ts, track_id="u3", username="Alice"), isolated_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/users")
    assert response.status_code == 200
    assert response.json() == {"users": ["Alice", "bob"]}
