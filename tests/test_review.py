"""Year-in-review aggregation."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import src.stats_service as stats_service_module
from src.database import get_review_summary, init_db, save_play_session
from src.main import app


class FakeCache:
    async def invalidate(self):
        pass

    async def get_or_create(self, _key, factory):
        return await factory()


def session(days_ago, hour, *, track="t-1", title="Song", artist="Artist", album="Album",
            duration=200, tz_offset_hours=0):
    played = datetime.now(timezone.utc).replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) - timedelta(days=days_ago)
    played -= timedelta(hours=tz_offset_hours)
    return {
        "last_seen_at": played.isoformat(),
        "username": "synthetic-user",
        "client_name": "Synthetic Client",
        "track_id": track,
        "title": title,
        "artist": artist,
        "album": album,
        "is_transcoding": 0,
        "duration_sec": duration,
        "source": "poller",
        "source_id": "legacy",
        "source_name": "Legacy",
        "session_id": f"sess-{days_ago}-{hour}-{track}",
        "duration_confidence": "estimated",
        "finalized": True,
        "finalized_at": played.isoformat(),
        "checkpointed_at": played.isoformat(),
    }


@pytest.fixture
async def seeded_db(isolated_db):
    await init_db(isolated_db)
    year = datetime.now(timezone.utc).year
    # Three consecutive days, two tracks, two hours.
    for offset in (0, 1, 2):
        await save_play_session(session(offset, 8, track="t-1", title="Morning Song"), isolated_db)
    await save_play_session(session(5, 22, track="t-2", title="Night Song",
                                    artist="Other Artist", album="Other Album"), isolated_db)
    return year


@pytest.mark.asyncio
async def test_review_totals_and_buckets(seeded_db, isolated_db):
    year = seeded_db
    review = await get_review_summary(year, "UTC", db_path=isolated_db)
    assert review["year"] == year
    assert review["total_plays"] == 4
    assert review["total_listen_sec"] == 4 * 200
    assert review["unique_tracks"] == 2
    assert review["active_days"] == 4
    assert review["longest_streak_days"] == 3
    assert review["first_played_at"] is not None
    assert review["last_played_at"] is not None
    assert review["biggest_month"] == datetime.now(timezone.utc).strftime("%Y-%m")

    this_month = f"{year:04d}-{datetime.now(timezone.utc).month:02d}"
    monthly = {entry["month"]: entry["count"] for entry in review["monthly"]}
    assert len(review["monthly"]) == 12
    assert monthly[this_month] == 4

    hourly = {entry["hour"]: entry["count"] for entry in review["hourly"]}
    assert hourly[8] == 3
    assert hourly[22] == 1
    assert sum(entry["count"] for entry in review["hourly"]) == 4

    weekday_counts = sum(entry["count"] for entry in review["weekday"])
    assert weekday_counts == 4


@pytest.mark.asyncio
async def test_review_buckets_carry_listen_seconds(seeded_db, isolated_db):
    year = seeded_db
    review = await get_review_summary(year, "UTC", db_path=isolated_db)
    hourly = {entry["hour"]: entry["total_listen_sec"] for entry in review["hourly"]}
    assert hourly[8] == 600
    assert hourly[22] == 200
    month_key = f"{year:04d}-{datetime.now(timezone.utc).month:02d}"
    monthly = {entry["month"]: entry["total_listen_sec"] for entry in review["monthly"]}
    assert monthly[month_key] == 800
    assert sum(entry["total_listen_sec"] for entry in review["weekday"]) == 800


@pytest.mark.asyncio
async def test_review_top_lists(seeded_db, isolated_db):
    year = seeded_db
    review = await get_review_summary(year, "UTC", db_path=isolated_db)
    assert review["top_artists"][0]["name"] == "Artist"
    assert review["top_artists"][0]["count"] == 3
    assert review["top_albums"][0]["name"] == "Album"
    top_track = review["top_tracks"][0]
    assert top_track["name"] == "Morning Song"
    assert top_track["track_id"] == "t-1"
    assert top_track["count"] == 3


@pytest.mark.asyncio
async def test_review_respects_timezone_day_buckets(seeded_db, isolated_db):
    # 22:00 UTC is already the next day in UTC+2, moving that play out of hour 22.
    review = await get_review_summary(2026, "Europe/Kiev", db_path=isolated_db)
    hourly = {entry["hour"]: entry["count"] for entry in review["hourly"]}
    assert hourly.get(22, 0) <= 1


@pytest.mark.asyncio
async def test_review_empty_year(isolated_db):
    await init_db(isolated_db)
    review = await get_review_summary(1971, "UTC", db_path=isolated_db)
    assert review["total_plays"] == 0
    assert review["active_days"] == 0
    assert review["longest_streak_days"] == 0
    assert review["first_played_at"] is None
    assert review["top_tracks"] == []


@pytest.mark.asyncio
async def test_review_endpoint_is_cached(seeded_db, isolated_db, monkeypatch):
    from src.dashboard_cache import DashboardSnapshotCache
    from src.stats_service import StatsService

    cache = DashboardSnapshotCache(ttl_sec=60)
    service = StatsService(cache=cache)
    builds = {"n": 0}

    original = get_review_summary

    async def counting(*args, **kwargs):
        builds["n"] += 1
        return await original(*args, **kwargs)

    import src.stats_service as stats_module
    monkeypatch.setattr(stats_module, "get_review_summary", counting)
    await service.review(year=seeded_db, timezone_name="UTC", source_id=None, username="alice")
    await service.review(year=seeded_db, timezone_name="UTC", source_id=None, username="alice")
    await service.review(year=seeded_db, timezone_name="UTC", source_id=None, username="bob")
    assert builds["n"] == 2


@pytest.mark.asyncio
async def test_review_filters_every_aggregate_by_username(seeded_db, isolated_db):
    year = seeded_db
    await save_play_session(
        {
            **session(0, 12, track="other-track", title="Other Song"),
            "username": "other-user",
            "session_id": "other-user-session",
        },
        isolated_db,
    )

    review = await get_review_summary(
        year,
        "UTC",
        db_path=isolated_db,
        username="synthetic-user",
    )

    assert review["username"] == "synthetic-user"
    assert review["total_plays"] == 4
    assert {entry["name"] for entry in review["top_tracks"]} == {
        "Morning Song",
        "Night Song",
    }


@pytest.mark.asyncio
async def test_review_endpoint_forwards_and_returns_visible_username_scope(
    seeded_db,
    isolated_db,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/review",
            params={
                "year": seeded_db,
                "timezone": "UTC",
                "username": "synthetic-user",
            },
        )

    assert response.status_code == 200
    assert response.json()["username"] == "synthetic-user"
    assert response.json()["total_plays"] == 4


@pytest.mark.asyncio
async def test_review_top_tracks_carry_source_id(seeded_db, isolated_db):
    year = seeded_db
    review = await get_review_summary(year, "UTC", db_path=isolated_db)
    tracks = {entry["name"]: entry for entry in review["top_tracks"]}
    assert tracks["Morning Song"]["source_id"] == "legacy"
    assert tracks["Morning Song"]["track_id"] == "t-1"


@pytest.mark.asyncio
async def test_review_albums_stamp_single_server_source(seeded_db, isolated_db, monkeypatch):
    year = seeded_db
    async def fake_list_server_options():
        return [{"id": "srv-1", "display_name": "Main"}]
    monkeypatch.setattr(stats_service_module, "list_server_options", fake_list_server_options)
    service = stats_service_module.StatsService(cache=FakeCache(), retry_attempts=1)
    review = await service.review(year=year, timezone_name="UTC", source_id=None)
    assert review["top_albums"]
    for entry in review["top_albums"]:
        assert entry["source_id"] == "srv-1"


@pytest.mark.asyncio
async def test_review_albums_source_id_null_without_effective_source(seeded_db, isolated_db, monkeypatch):
    year = seeded_db
    async def fake_list_server_options():
        return [
            {"id": "srv-1", "display_name": "Main"},
            {"id": "srv-2", "display_name": "Second"},
        ]
    monkeypatch.setattr(stats_service_module, "list_server_options", fake_list_server_options)
    service = stats_service_module.StatsService(cache=FakeCache(), retry_attempts=1)
    review = await service.review(year=year, timezone_name="UTC", source_id=None)
    assert review["top_albums"]
    for entry in review["top_albums"]:
        assert entry["source_id"] is None
        assert entry["album_id"] is None
