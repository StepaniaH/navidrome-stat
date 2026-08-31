"""Cross-dimensional relation query and API tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import init_db, save_play_session
from src.main import app
from src.stats_query_relations import get_data_relations
from src.stats_scope import StatsScope


def _play(
    moment: datetime,
    *,
    track_id: str,
    artist: str = "Artist A",
    album: str = "Album A",
    client: str | None = "Web Player",
    duration: int | None = 60,
    source_id: str = "source-a",
    source_name: str = "Source A",
    album_id: str | None = None,
) -> dict:
    return {
        "last_seen_at": moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "username": "listener",
        "client_name": client,
        "track_id": track_id,
        "title": track_id,
        "artist": artist,
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


def test_artist_relations_return_values_without_interpretation(db_path):
    asyncio.run(init_db(db_path))
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    _save(db_path, _play(today + timedelta(hours=1), track_id="a-night", duration=120))
    _save(db_path, _play(today + timedelta(hours=8), track_id="a-morning", duration=60))
    _save(db_path, _play(
        today - timedelta(days=1) + timedelta(hours=13),
        track_id="b-afternoon",
        artist="Artist B",
        duration=30,
    ))
    for index, artist in enumerate(("Artist C", "Artist D", "Artist E", "Artist F")):
        _save(db_path, _play(
            today - timedelta(days=index % 2) + timedelta(hours=19),
            track_id=f"{artist}-evening",
            artist=artist,
            duration=None if artist == "Artist F" else 45,
        ))

    # The immediately preceding seven local dates.
    for index in range(3):
        _save(db_path, _play(
            today - timedelta(days=7) + timedelta(hours=index + 1),
            track_id=f"b-previous-{index}",
            artist="Artist B",
            duration=90,
        ))

    result = asyncio.run(get_data_relations(
        StatsScope.create(days=7, timezone_name="UTC", metric="plays"),
        "artist",
        db_path=db_path,
    ))

    assert result["dimension"] == "artist"
    assert result["grain"] == "day"
    assert result["comparison_available"] is True
    assert result["duration_coverage_pct"] == pytest.approx(85.7)
    assert result["reported_duration_pct"] == 0.0

    assert [series["label"] for series in result["trend"][:-1]] == [
        "Artist A", "Artist B", "Artist C", "Artist D", "Artist E",
    ]
    assert result["trend"][-1]["key"] == "__other__"
    assert all(len(series["points"]) == 7 for series in result["trend"])
    assert sum(point["play_count"] for point in result["trend"][0]["points"]) == 2
    assert sum(point["play_count"] for point in result["trend"][-1]["points"]) == 1

    artist_a = next(row for row in result["matrix"] if row["label"] == "Artist A")
    by_daypart = {point["daypart"]: point for point in artist_a["points"]}
    assert by_daypart["night"]["play_count"] == 1
    assert by_daypart["morning"]["play_count"] == 1
    assert by_daypart["afternoon"]["play_count"] == 0

    comparison = {row["label"]: row for row in result["comparison"]}
    assert comparison["Artist A"]["current_play_count"] == 2
    assert comparison["Artist A"]["previous_play_count"] == 0
    assert comparison["Artist B"]["current_play_count"] == 1
    assert comparison["Artist B"]["previous_play_count"] == 3


def test_album_relations_keep_source_scoped_identity(db_path):
    asyncio.run(init_db(db_path))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _save(db_path, _play(
        now,
        track_id="source-a-album",
        artist="Artist A",
        album="Live",
        album_id="album-a",
        source_id="source-a",
        source_name="Source A",
    ))
    _save(db_path, _play(
        now + timedelta(seconds=1),
        track_id="source-b-album",
        artist="Artist B",
        album="Live",
        album_id="album-b",
        source_id="source-b",
        source_name="Source B",
    ))

    result = asyncio.run(get_data_relations(
        StatsScope.create(days=0, timezone_name="UTC", metric="listen_time"),
        "album",
        db_path=db_path,
    ))

    assert len(result["trend"]) == 2
    assert {row["source_id"] for row in result["trend"]} == {"source-a", "source-b"}
    assert {row["entity_id"] for row in result["trend"]} == {"album-a", "album-b"}
    assert result["comparison_available"] is False
    assert result["comparison"] == []


@pytest.mark.asyncio
async def test_relations_api_forwards_scope_and_dimension():
    payload = {
        "dimension": "client",
        "metric": "listen_time",
        "grain": "day",
        "comparison_available": True,
        "duration_coverage_pct": 100.0,
        "reported_duration_pct": 100.0,
        "trend": [],
        "matrix": [],
        "comparison": [],
    }
    with patch(
        "src.routes.stats.stats_service.data_relations",
        new_callable=AsyncMock,
        return_value=payload,
    ) as query:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/stats/relations",
                params={
                    "dimension": "client",
                    "days": 30,
                    "timezone": "Asia/Shanghai",
                    "metric": "listen_time",
                    "source_id": "source-a",
                    "username": "listener",
                },
            )

    assert response.status_code == 200
    query.assert_awaited_once_with(
        StatsScope.create(
            days=30,
            timezone_name="Asia/Shanghai",
            metric="listen_time",
            source_id="source-a",
            username="listener",
        ),
        "client",
    )


@pytest.mark.asyncio
async def test_relations_api_rejects_unknown_dimension():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/stats/relations?dimension=track&days=30",
        )

    assert response.status_code == 422
