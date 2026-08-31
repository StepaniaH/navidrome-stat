"""Artist and album drill-down query and API tests."""

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
    duration: int = 60,
    source_id: str = "source-a",
    source_name: str = "Source A",
    username: str = "listener",
    artist_id: str | None = None,
    album_id: str | None = None,
) -> dict:
    return {
        "last_seen_at": _iso(moment),
        "username": username,
        "client_name": "Test Player",
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "artist_id": artist_id,
        "album": album,
        "album_id": album_id,
        "is_transcoding": 0,
        "duration_sec": duration,
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


@pytest.mark.asyncio
@patch("src.routes.stats.stats_service.entity_detail", new_callable=AsyncMock)
async def test_entity_detail_api_builds_stats_scope(mock_detail):
    mock_detail.return_value = {
        "entity_type": "artist",
        "name": "Artist A",
        "artist": None,
        "entity_id": "artist-a",
        "entity_source_id": None,
        "metric": "listen_time",
        "total_plays": 0,
        "total_listen_sec": 0,
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
async def test_entity_detail_api_rejects_unknown_entity_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stats/entity-detail",
            params={"entity_type": "track", "name": "Song"},
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
