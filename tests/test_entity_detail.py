"""Artist, album, and client drill-down query and API tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import init_db, save_play_session
from src.main import app
from src.stats_query_entities import EntityIdentity, get_entity_detail
from src.stats_scope import StatsScope


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _play(
    moment: datetime,
    *,
    track_id: str,
    title: str,
    artist: str,
    album: str,
    duration: int | None = 60,
    source_id: str = "source-a",
    source_name: str = "Source A",
    username: str = "listener",
    client_name: str = "Test Player",
    artist_id: str | None = None,
    album_id: str | None = None,
    session_id: str | None = None,
    duration_confidence: str = "estimated",
    source: str = "poller",
) -> dict:
    return {
        "last_seen_at": _iso(moment),
        "username": username,
        "client_name": client_name,
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "artist_id": artist_id,
        "album": album,
        "album_id": album_id,
        "is_transcoding": 0,
        "duration_sec": duration,
        "duration_confidence": duration_confidence,
        "session_id": session_id,
        "source": source,
        "source_id": source_id,
        "source_name": source_name,
        "finalized": True,
    }


def _save(db_path: str, payload: dict) -> None:
    asyncio.run(save_play_session(payload, db_path=db_path))


def test_artist_detail_preserves_scope_and_builds_drilldown(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

    # Current period: Artist A is second with three plays across two tracks.
    _save(db_path, _play(
        now - timedelta(days=1),
        track_id="song-1",
        title="Song One",
        artist="Artist A",
        artist_id="artist-a",
        album="Album A",
        duration=120,
    ))
    _save(db_path, _play(
        now,
        track_id="song-1",
        title="Song One",
        artist="Artist A",
        artist_id="artist-a",
        album="Album A",
        duration=180,
    ))
    _save(db_path, _play(
        now,
        track_id="song-2",
        title="Song Two",
        artist="Artist A",
        artist_id="artist-a",
        album="Album B",
        duration=60,
    ))
    for index in range(4):
        _save(db_path, _play(
            now,
            track_id=f"rival-current-{index}",
            title=f"Rival {index}",
            artist="Current Leader",
            album="Other",
        ))

    # Previous equal period: Artist A was first, so it falls one rank.
    for index in range(5):
        _save(db_path, _play(
            now - timedelta(days=8),
            track_id=f"artist-previous-{index}",
            title=f"Previous {index}",
            artist="Artist A",
            artist_id="artist-a",
            album="Archive",
        ))
    for index in range(2):
        _save(db_path, _play(
            now - timedelta(days=8),
            track_id=f"rival-previous-{index}",
            title=f"Previous rival {index}",
            artist="Current Leader",
            album="Archive",
        ))

    scope = StatsScope.create(days=7, timezone_name="UTC", metric="plays")
    identity = EntityIdentity.create(
        entity_type="artist",
        name="Artist A",
        entity_id="artist-a",
    )

    detail = asyncio.run(get_entity_detail(scope, identity, db_path=db_path))

    assert detail["entity_type"] == "artist"
    assert detail["name"] == "Artist A"
    assert detail["entity_id"] == "artist-a"
    assert detail["total_plays"] == 3
    assert detail["total_listen_sec"] == 360
    assert detail["unique_tracks"] == 2
    assert detail["average_listen_sec"] == 120.0
    assert detail["current_rank"] == 2
    assert detail["previous_rank"] == 1
    assert detail["rank_change"] == -1
    assert detail["comparison_available"] is True
    assert len(detail["trend"]) == 7
    assert sum(point["play_count"] for point in detail["trend"]) == 3
    assert sum(point["total_listen_sec"] for point in detail["trend"]) == 360
    assert sum(point["play_count"] == 0 for point in detail["trend"]) == 5
    assert [(row["title"], row["play_count"], row["total_listen_sec"]) for row in detail["top_tracks"]] == [
        ("Song One", 2, 300),
        ("Song Two", 1, 60),
    ]
    assert len(detail["recent_plays"]) == 3
    assert detail["recent_plays"][0]["title"] == "Song Two"
    assert detail["first_played_at"] == _iso(now - timedelta(days=1))
    assert detail["last_played_at"] == _iso(now)


def test_album_detail_uses_source_and_album_identity(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for index in range(2):
        _save(db_path, _play(
            now + timedelta(seconds=index),
            track_id=f"wanted-{index}",
            title=f"Wanted {index}",
            artist="Artist A",
            album="Live",
            album_id="album-a",
            source_id="source-a",
        ))
    for index in range(3):
        _save(db_path, _play(
            now + timedelta(seconds=10 + index),
            track_id=f"other-source-{index}",
            title=f"Other source {index}",
            artist="Artist B",
            album="Live",
            album_id="album-b",
            source_id="source-b",
            source_name="Source B",
        ))
    _save(db_path, _play(
        now + timedelta(seconds=20),
        track_id="legacy-same-name",
        title="Legacy same name",
        artist="Artist B",
        album="Live",
        source_id="source-a",
    ))

    detail = asyncio.run(get_entity_detail(
        StatsScope.create(days=0, timezone_name="UTC", metric="listen_time"),
        EntityIdentity.create(
            entity_type="album",
            name="Live",
            entity_id="album-a",
            source_id="source-a",
            artist="Artist A",
        ),
        db_path=db_path,
    ))

    assert detail["total_plays"] == 2
    assert detail["total_listen_sec"] == 120
    assert detail["entity_source_id"] == "source-a"
    assert detail["artist"] == "Artist A"
    assert {row["source_id"] for row in detail["recent_plays"]} == {"source-a"}
    assert detail["comparison_available"] is False
    assert detail["previous_rank"] is None
    assert detail["rank_change"] is None


def test_client_detail_builds_cross_track_history_and_period_rank(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

    for index, artist in enumerate(("Artist A", "Artist A", "Artist B")):
        _save(db_path, _play(
            now - timedelta(days=index % 2),
            track_id=f"client-current-{index}",
            title=f"Client track {index}",
            artist=artist,
            album=f"Album {artist[-1]}",
            duration=90 + index * 30,
            client_name="Focused Client",
        ))
    for index in range(4):
        _save(db_path, _play(
            now,
            track_id=f"rival-current-{index}",
            title=f"Rival current {index}",
            artist="Rival Artist",
            album="Rival Album",
            client_name="Current Leader",
        ))
    for index in range(5):
        _save(db_path, _play(
            now - timedelta(days=8),
            track_id=f"client-previous-{index}",
            title=f"Client previous {index}",
            artist="Archive Artist",
            album="Archive",
            client_name="Focused Client",
        ))
    for index in range(2):
        _save(db_path, _play(
            now - timedelta(days=8),
            track_id=f"rival-previous-{index}",
            title=f"Rival previous {index}",
            artist="Rival Artist",
            album="Archive",
            client_name="Current Leader",
        ))

    detail = asyncio.run(get_entity_detail(
        StatsScope.create(days=7, timezone_name="UTC", metric="plays"),
        EntityIdentity.create(
            entity_type="client",
            name="Focused Client",
            entity_id="ignored-id",
            source_id="ignored-source",
            artist="ignored-artist",
        ),
        db_path=db_path,
    ))

    assert detail["entity_type"] == "client"
    assert detail["name"] == "Focused Client"
    assert detail["entity_id"] is None
    assert detail["artist"] is None
    assert detail["total_plays"] == 3
    assert detail["total_listen_sec"] == 360
    assert detail["unique_tracks"] == 3
    assert detail["current_rank"] == 2
    assert detail["previous_rank"] == 1
    assert detail["rank_change"] == -1
    assert {row["artist"] for row in detail["top_tracks"]} == {"Artist A", "Artist B"}
    assert {row["client_name"] for row in detail["recent_plays"]} == {"Focused Client"}


def test_legacy_album_detail_does_not_merge_identified_album_rows(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _save(db_path, _play(
        now,
        track_id="legacy",
        title="Legacy row",
        artist="Artist A",
        album="Live",
        source_id="source-a",
    ))
    _save(db_path, _play(
        now + timedelta(seconds=1),
        track_id="identified",
        title="Identified row",
        artist="Artist A",
        album="Live",
        album_id="album-a",
        source_id="source-a",
    ))

    detail = asyncio.run(get_entity_detail(
        StatsScope.create(days=0, timezone_name="UTC", metric="plays"),
        EntityIdentity.create(
            entity_type="album",
            name="Live",
            source_id="source-a",
            artist="Artist A",
        ),
        db_path=db_path,
    ))

    assert detail["total_plays"] == 1
    assert [row["title"] for row in detail["recent_plays"]] == ["Legacy row"]


def test_entity_detail_exposes_duration_quality_without_inventing_precision(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _save(db_path, _play(
        now,
        track_id="legacy",
        title="Legacy checkpoint",
        artist="Artist A",
        album="Live",
        duration=45,
    ))
    _save(db_path, _play(
        now + timedelta(seconds=1),
        track_id="threshold",
        title="Threshold checkpoint",
        artist="Artist A",
        album="Live",
        duration=30,
        session_id="affected-session",
        duration_confidence="reported",
    ))
    _save(db_path, _play(
        now + timedelta(seconds=2),
        track_id="legacy",
        title="Legacy checkpoint",
        artist="Artist A",
        album="Live",
        duration=120,
        session_id="modern-session",
        duration_confidence="reported",
    ))
    _save(db_path, _play(
        now + timedelta(seconds=3),
        track_id="estimated",
        title="Estimated session",
        artist="Artist A",
        album="Live",
        duration=60,
        session_id="estimated-session",
    ))
    _save(db_path, _play(
        now + timedelta(seconds=4),
        track_id="imported",
        title="Imported history",
        artist="Artist A",
        album="Archive",
        duration=None,
        source="backfill",
    ))

    detail = asyncio.run(get_entity_detail(
        StatsScope.create(days=0, timezone_name="UTC", metric="plays"),
        EntityIdentity.create(entity_type="artist", name="Artist A"),
        db_path=db_path,
    ))

    assert detail["total_plays"] == 5
    assert detail["total_listen_sec"] == 255
    assert detail["duration_quality"] == "lower_bound"
    assert detail["trend"][0]["duration_quality"] == "lower_bound"
    assert detail["top_tracks"][0]["play_count"] == 2
    assert detail["top_tracks"][0]["total_listen_sec"] == 165
    assert detail["top_tracks"][0]["duration_quality"] == "lower_bound"
    track_qualities = {
        row["title"]: row["duration_quality"] for row in detail["top_tracks"]
    }
    assert track_qualities == {
        "Legacy checkpoint": "lower_bound",
        "Threshold checkpoint": "lower_bound",
        "Estimated session": "estimated",
        "Imported history": "unknown",
    }
    assert [row["duration_quality"] for row in detail["recent_plays"]] == [
        "unknown",
        "estimated",
        "reported",
        "lower_bound",
        "lower_bound",
    ]
    assert detail["recent_plays"][0]["listen_duration_sec"] is None


def test_empty_entity_detail_returns_zero_derived_metrics(db_path):
    asyncio.run(init_db(db_path))

    detail = asyncio.run(get_entity_detail(
        StatsScope.create(days=0, timezone_name="UTC", metric="plays"),
        EntityIdentity.create(entity_type="artist", name="Missing Artist"),
        db_path=db_path,
    ))

    assert detail["total_plays"] == 0
    assert detail["unique_tracks"] == 0
    assert detail["average_listen_sec"] == 0
    assert detail["trend"] == []


def _empty_api_detail(entity_type: str, name: str, *, metric: str) -> dict:
    return {
        "entity_type": entity_type,
        "name": name,
        "artist": None,
        "entity_id": None,
        "entity_source_id": None,
        "metric": metric,
        "total_plays": 0,
        "total_listen_sec": 0,
        "unique_tracks": 0,
        "average_listen_sec": 0,
        "first_played_at": None,
        "last_played_at": None,
        "current_rank": None,
        "previous_rank": None,
        "rank_change": None,
        "comparison_available": True,
        "trend": [],
        "top_tracks": [],
        "recent_plays": [],
    }


@pytest.mark.asyncio
@patch("src.routes.stats.stats_service.entity_detail", new_callable=AsyncMock)
async def test_entity_detail_api_builds_stats_scope(mock_detail):
    mock_detail.return_value = {
        **_empty_api_detail("artist", "Artist A", metric="listen_time"),
        "entity_id": "artist-a",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/entity-detail",
            params={
                "entity_type": "artist",
                "name": "Artist A",
                "entity_id": "artist-a",
                "days": 30,
                "timezone": "Asia/Shanghai",
                "metric": "listen_time",
                "source_id": "source-a",
                "username": "listener",
            },
        )

    assert response.status_code == 200
    scope, identity = mock_detail.await_args.args
    assert scope == StatsScope.create(
        days=30,
        timezone_name="Asia/Shanghai",
        metric="listen_time",
        source_id="source-a",
        username="listener",
    )
    assert identity == EntityIdentity.create(
        entity_type="artist",
        name="Artist A",
        entity_id="artist-a",
    )


@pytest.mark.asyncio
@patch("src.routes.stats.stats_service.entity_detail", new_callable=AsyncMock)
async def test_client_detail_api_uses_post_body_for_private_identity(mock_detail):
    mock_detail.return_value = _empty_api_detail(
        "client",
        "Symfonium",
        metric="listen_time",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/stats/client-detail",
            json={
                "name": "Symfonium",
                "days": 30,
                "timezone": "Asia/Shanghai",
                "metric": "listen_time",
                "source_id": "source-a",
                "username": "listener",
            },
        )

    assert response.status_code == 200
    scope, identity = mock_detail.await_args.args
    assert scope == StatsScope.create(
        days=30,
        timezone_name="Asia/Shanghai",
        metric="listen_time",
        source_id="source-a",
        username="listener",
    )
    assert identity == EntityIdentity.create(entity_type="client", name="Symfonium")


@pytest.mark.asyncio
async def test_entity_detail_api_rejects_unknown_entity_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/entity-detail",
            params={"entity_type": "track", "name": "Song"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_entity_detail_get_rejects_client_identity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/entity-detail",
            params={"entity_type": "client", "name": "Symfonium"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_entity_detail_api_requires_stable_album_source_identity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/entity-detail",
            params={"entity_type": "album", "name": "Live", "entity_id": "album-a"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "source_id is required for album details"
