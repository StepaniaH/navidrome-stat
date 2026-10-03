import asyncio
import base64
import secrets
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from src.collection_status import collection_status
from src.core_types import PlaybackObservation
from src.coverart import CoverArtService
from src.database import init_db
from src.instance_lock import database_instance_lock
from src.listening_history import get_listening_history
from src.main import app
from src.persistence import save_play_session
from src.runtime_state import runtime_state
from src.stats_query_overview import get_summary
from src.stats_scope import StatsScope


@pytest.fixture
async def listening_db(isolated_db, monkeypatch):
    for name in (
        "NAVIDROME_URL",
        "NAVIDROME_USER",
        "NAVIDROME_PASS",
        "STATS_API_TOKEN",
        "STATS_READ_ONLY_TOKEN",
        "LISTENBRAINZ_INGEST_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    runtime_state.reset()
    await init_db(isolated_db)
    for number, day in enumerate((1, 1, 10)):
        await save_play_session(
            {
                "last_seen_at": f"2024-01-{day:02d}T12:00:00+00:00",
                "username": "listener",
                "track_id": f"track-{number}",
                "title": "100% music" if number == 0 else f"Track {number}",
                "artist": "Artist",
                "album": "Album",
                "album_id": "album-1",
                "source_id": "synthetic",
                "duration_sec": 60,
                "finalized": True,
            },
            db_path=isolated_db,
        )
    yield isolated_db
    runtime_state.reset()


@pytest.mark.asyncio
async def test_individual_history_has_stable_pages_and_literal_search(listening_db):
    scope = StatsScope.create(days=0)
    first = await get_listening_history(scope, limit=2)
    await save_play_session(
        {"last_seen_at": "2024-02-01T00:00:00+00:00", "track_id": "new", "duration_sec": 60},
        db_path=listening_db,
    )
    second = await get_listening_history(scope, limit=2, cursor=first["next_cursor"])
    assert [item["track_id"] for item in first["items"] + second["items"]] == [
        "track-2",
        "track-1",
        "track-0",
    ]
    assert second["next_cursor"] is None
    literal = await get_listening_history(scope, search="%")
    assert [item["title"] for item in literal["items"]] == ["100% music"]
    assert first["items"][0]["album_id"] == "album-1"
    assert first["items"][0]["duration_quality"] == "lower_bound"


@pytest.mark.asyncio
async def test_calendar_day_average_matches_all_history_span(listening_db):
    all_history = await get_summary(days=0, db_path=listening_db)
    window = await get_summary(
        start_date=date(2024, 1, 1), end_date=date(2024, 1, 10), db_path=listening_db
    )
    assert all_history["average_daily_plays"] == 0.3
    assert window["average_daily_plays"] == 1.5
    for summary in (all_history, window):
        assert summary["average_calendar_daily_plays"] == 0.3
        assert summary["average_active_daily_plays"] == 1.5
        assert summary["average_calendar_daily_listen_sec"] == 18
        assert summary["average_active_daily_listen_sec"] == 90
        assert summary["calendar_days"] == 10
        assert summary["active_days"] == 2
        assert summary["first_recorded_date"] == "2024-01-01"


@pytest.mark.asyncio
async def test_database_to_api_history_contract_and_scoped_viewer(listening_db, monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("STATS_READ_ONLY_TOKEN", token)
    monkeypatch.setenv("STATS_READ_ONLY_SOURCE_ID", "synthetic")
    monkeypatch.setenv("STATS_READ_ONLY_USERNAME", "listener")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        response = await client.get("/api/stats/listens?days=0")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 3
        assert (await client.get("/api/stats/listens?days=0&username=other")).status_code == 403
        assert (await client.get("/api/stats/listens?days=0&cursor=invalid")).status_code == 422
        huge_cursor = base64.urlsafe_b64encode(b"999999999999999999999999:1").decode("ascii")
        assert (
            await client.get("/api/stats/listens", params={"cursor": huge_cursor})
        ).status_code == 422
        assert (await client.get("/api/stats/listens?limit=101")).status_code == 422
        assert (await client.get("/api/diagnostics")).status_code == 403
        history = await client.get("/api/stats/history?days=0")
        assert history.json()[0]["track_id"] == "track-2"
        assert history.json()[0]["album_id"] == "album-1"
        assert (await client.get("/history")).status_code == 200


@pytest.mark.asyncio
async def test_collection_status_requires_fresh_successful_collection(listening_db, monkeypatch):
    assert (await collection_status())["status"] == "unconfigured"
    monkeypatch.setenv("LISTENBRAINZ_INGEST_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("LISTENBRAINZ_INGEST_USERNAME", "listener")
    assert (await collection_status())["status"] == "receiver_enabled"
    monkeypatch.setattr(
        "src.collection_status.list_servers",
        AsyncMock(return_value=[{"id": "synthetic", "enabled": True}]),
    )
    assert (await collection_status()) == {"status": "degraded", "mixed_collection": True}
    runtime_state.set_collector_task("synthetic", Mock(done=lambda: False))
    assert (await collection_status("synthetic"))["status"] == "starting"
    runtime_state.record_poll_success(datetime.now(timezone.utc), "synthetic")
    assert (await collection_status("synthetic"))["status"] == "live"
    runtime_state.mark_save_failure("synthetic")
    assert (await collection_status("synthetic"))["status"] == "degraded"
    runtime_state.record_save_success("synthetic")
    runtime_state.record_poll_success(datetime.now(timezone.utc) - timedelta(hours=1), "synthetic")
    assert (await collection_status("synthetic"))["status"] == "degraded"
    assert (await collection_status("other"))["status"] == "unconfigured"


@pytest.mark.asyncio
async def test_legacy_album_cover_checks_viewer_history_before_lookup(listening_db, monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("STATS_READ_ONLY_TOKEN", token)
    monkeypatch.setenv("STATS_READ_ONLY_SOURCE_ID", "synthetic")
    monkeypatch.setenv("STATS_READ_ONLY_USERNAME", "listener")
    await save_play_session({
        "last_seen_at": "2024-01-11T00:00:00+00:00", "track_id": "private-track",
        "username": "other", "source_id": "synthetic", "album": "Private album",
        "artist": "Artist", "duration_sec": 60,
    }, db_path=listening_db)
    lookup = AsyncMock(return_value=(b"\x89PNG\r\n\x1a\n", "image/png"))
    monkeypatch.setattr("src.routes.stats.cover_art_service.load_album", lookup)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        response = await client.get("/api/stats/album-cover", params={
            "source_id": "synthetic", "album": "Album", "artist": "Artist",
        })
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert (await client.get("/api/stats/album-cover", params={
            "source_id": "synthetic", "album": "Private album",
        })).status_code == 404
        assert (await client.get("/api/stats/album-cover", params={
            "source_id": "other-source", "album": "Album",
        })).status_code == 403
        assert (await client.get("/api/stats/collection-status")).json() == {
            "status": "unconfigured", "mixed_collection": False,
        }
    lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_cover_can_use_the_only_saved_server(tmp_path, monkeypatch):
    monkeypatch.setattr("src.coverart.credentials_for_source", AsyncMock(return_value=None))
    monkeypatch.setattr("src.coverart.list_servers", AsyncMock(return_value=[{
        "url": "http://navidrome.example.invalid", "username": "synthetic",
        "password": "synthetic", "id": "saved-server",
    }]))
    factory = Mock(return_value=AsyncMock())
    factory.return_value.get_cover_art.return_value = (b"\x89PNG\r\n\x1a\n", "image/png")
    service = CoverArtService(cache_dir=tmp_path, client_factory=factory)
    assert await service.load("legacy", "cover", 100) is not None
    assert await service.load("unrelated-source", "cover", 100) is None
    assert factory.call_count == 1


def test_process_lock_rejects_second_process_and_releases(tmp_path):
    path = str(tmp_path / "locked.db")
    script = "from src.instance_lock import database_instance_lock; import sys\nwith database_instance_lock(sys.argv[1]): pass"
    with database_instance_lock(path):
        child = subprocess.run([sys.executable, "-c", script, path], capture_output=True)
        assert child.returncode != 0
        assert b"Another Navidrome Stat instance" in child.stderr
    assert subprocess.run([sys.executable, "-c", script, path], capture_output=True).returncode == 0


def test_observation_rejects_malformed_values_and_detaches_credits():
    credits = [{"name": "Artist", "id": "artist-1"}]
    observed = PlaybackObservation.from_mapping(
        {
            "playerId": 42,
            "id": {},
            "title": [],
            "positionMs": float("inf"),
            "playbackRate": float("nan"),
            "artists": credits,
        }
    )
    credits[0]["name"] = "Changed"
    assert observed.player_id == "42"
    assert observed.track_id is None and observed.title is None
    assert observed.position_ms is None and observed.playback_rate == 1
    assert observed.artist_mappings() == [{"name": "Artist", "id": "artist-1"}]


@pytest.mark.asyncio
async def test_cover_requests_have_a_concurrency_bound(tmp_path, monkeypatch):
    service = CoverArtService(cache_dir=tmp_path)
    active = peak = 0

    async def fetch(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return b"\x89PNG\r\n\x1a\n", "image/png"

    monkeypatch.setattr(service, "_fetch", fetch)
    results = await asyncio.gather(*(service.load("synthetic", str(i), 100) for i in range(12)))
    assert all(results)
    assert peak == 4


@pytest.mark.asyncio
async def test_cached_covers_bypass_busy_upstream_requests(tmp_path, monkeypatch):
    service = CoverArtService(cache_dir=tmp_path)
    image = (b"\x89PNG\r\n\x1a\n", "image/png")
    monkeypatch.setattr(service, "_fetch", AsyncMock(return_value=image))
    assert await service.load("synthetic", "cached", 100) == image
    release = asyncio.Event()
    all_started = asyncio.Event()
    active = 0

    async def fetch(*_args):
        nonlocal active
        active += 1
        if active == 4:
            all_started.set()
        await release.wait()
        return image

    monkeypatch.setattr(service, "_fetch", fetch)
    pending = [asyncio.create_task(service.load("synthetic", str(i), 100)) for i in range(4)]
    try:
        await asyncio.wait_for(all_started.wait(), timeout=2)
        assert await asyncio.wait_for(service.load("synthetic", "cached", 100), timeout=1) == image
    finally:
        release.set()
        await asyncio.gather(*pending)


@pytest.mark.asyncio
async def test_cover_timeout_closes_client_and_releases_capacity(tmp_path, monkeypatch):
    client = AsyncMock()
    service = CoverArtService(cache_dir=tmp_path, request_timeout_sec=0.01)
    monkeypatch.setattr(service, "_client_for", AsyncMock(return_value=client))

    async def stalled(*_args, **_kwargs):
        await asyncio.Event().wait()

    client.get_cover_art.side_effect = stalled
    assert await service.load("synthetic", "slow", 100) is None
    client.close.assert_awaited_once()
    client.get_cover_art.side_effect = None
    client.get_cover_art.return_value = (b"\x89PNG\r\n\x1a\n", "image/png")
    assert await service.load("synthetic", "recovered", 100) is not None


@pytest.mark.asyncio
async def test_cover_queue_wait_does_not_spend_upstream_timeout(tmp_path, monkeypatch):
    service = CoverArtService(cache_dir=tmp_path, request_timeout_sec=0.15, queue_timeout_sec=1)

    async def fetch(*_args):
        await asyncio.sleep(0.1)
        return b"\x89PNG\r\n\x1a\n", "image/png"

    monkeypatch.setattr(service, "_fetch", fetch)
    assert all(await asyncio.gather(*(service.load("synthetic", str(i), 100) for i in range(8))))


@pytest.mark.asyncio
async def test_review_highlights_use_recorded_gaps_and_previous_counts(listening_db):
    from src.review_queries import get_review_summary

    for timestamp in ("2023-09-01T00:00:00+00:00", "2023-12-01T00:00:00+00:00"):
        await save_play_session(
            {
                "last_seen_at": timestamp,
                "username": "listener",
                "track_id": "old-track",
                "artist": "Artist",
                "album": "Old album",
                "album_id": "old-album",
                "source_id": "synthetic",
                "duration_sec": 60,
            },
            db_path=listening_db,
        )
    review = await get_review_summary(2024, "UTC", month=1, db_path=listening_db)
    assert review["first_recorded_tracks"] == 3
    assert len(review["new_tracks"]) == 3
    assert review["rising_artist"]["previous_count"] == 1
    assert review["rising_artist"]["count"] == 3
    assert review["returning_albums"] == []
    await save_play_session(
        {
            "last_seen_at": "2023-01-01T00:00:00+00:00",
            "username": "listener",
            "track_id": "track-0",
            "artist": "Artist",
            "album": "Album",
            "album_id": "album-1",
            "source_id": "synthetic",
            "duration_sec": 60,
        },
        db_path=listening_db,
    )
    review = await get_review_summary(2024, "UTC", month=1, db_path=listening_db)
    assert review["first_recorded_tracks"] == 2
    assert review["returning_albums"][0]["name"] == "Album"


@pytest.mark.asyncio
async def test_review_highlights_keep_missing_duration_and_scoped_metadata(listening_db):
    from src.review_queries import get_review_summary

    for user, title in (("listener", "Visible track"), ("other", "Private title")):
        await save_play_session(
            {"last_seen_at": "2024-01-11T00:00:00+00:00", "track_id": "missing-duration",
             "title": title, "username": user, "source_id": "synthetic",
             "source": "listenbrainz", "duration_sec": None},
            db_path=listening_db,
        )
    review = await get_review_summary(2024, "UTC", month=1, username="listener", db_path=listening_db)
    track = next(item for item in review["new_tracks"] if item["track_id"] == "missing-duration")
    assert track["name"] == "Visible track"
    assert track["total_listen_sec"] is None
