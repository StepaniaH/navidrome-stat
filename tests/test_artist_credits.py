"""Shared artist attribution must never multiply underlying listening events."""

import json
from dataclasses import replace
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from src.artist_credits import artist_credits
from src.dashboard_cache import DashboardSnapshotCache
from src.database import get_summary, init_db, save_play_attempt, save_play_session
from src.main import app
from src.persistence import save_imported_events
from src.privacy_archive import _record_fingerprint, export_user_data, import_user_data
from src.privacy_ops import delete_user_data
from src.review_queries import get_review_summary
from src.sqlite import connect_db
from src.stats_query_entities import EntityIdentity, get_entity_detail
from src.stats_query_rankings import get_top_albums, get_top_artists
from src.stats_query_relations import get_data_relations
from src.stats_read_repository import StatsReadRepository
from src.stats_scope import StatsScope
from src.stats_service import StatsService

CREDITS = [{"name": "Alpha", "id": "a"}, {"name": "Beta", "id": "b"}]


def play(**kwargs):
    return {
        "session_id": "duet-session",
        "last_seen_at": "2026-08-15T12:00:00Z",
        "username": "listener",
        "source_id": "source-a",
        "source_name": "Demo server",
        "client_name": "Web",
        "track_id": "duet",
        "title": "Duet",
        "artist": "Alpha & Beta",
        "artist_id": "a",
        "artists": [*CREDITS, CREDITS[0]],
        "album": "Duets",
        "album_id": "album-a",
        "duration_sec": 120,
        "is_transcoding": 0,
        "finalized": True,
        **kwargs,
    }


def scope(mode="separate", metric="plays"):
    return StatsScope.create(
        days=0,
        timezone_name="UTC",
        artist_mode=mode,
        metric=metric,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        source_id="source-a",
        username="listener",
    )


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Alpha; Beta; Alpha", ["Alpha", "Beta"]),
        ("Alpha / Beta", ["Alpha", "Beta"]),
        ("Alpha feat. Beta", ["Alpha", "Beta"]),
        ("AC/DC", ["AC/DC"]),
        ("Earth, Wind & Fire", ["Earth, Wind & Fire"]),
        ("Simon & Garfunkel", ["Simon & Garfunkel"]),
    ],
)
def test_legacy_artist_names(name, expected):
    assert [item["name"] for item in json.loads(artist_credits(name, None))] == expected


def test_explicit_artist_metadata_wins_over_punctuation():
    raw = json.dumps([{"name": "A / B", "id": "band"}])
    assert json.loads(artist_credits("A / B", raw)) == [{"name": "A / B", "id": "band"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["plays", "listen_time"])
async def test_separate_artists_keep_recording_totals_and_details(db_path, metric):
    await init_db(db_path)
    await save_play_session(play(), db_path)
    # Retried checkpoints and duplicate credit entries must not add plays.
    await save_play_session(play(), db_path)
    await save_play_session(play(session_id="other-user", username="other"), db_path)
    await save_play_session(play(session_id="other-source", source_id="source-b"), db_path)
    combined = await StatsReadRepository(db_path).dashboard(scope("combined", metric))
    separate = await StatsReadRepository(db_path).dashboard(scope("separate", metric))
    for key in combined:
        if key != "top_artists":
            assert separate[key] == combined[key], key
    assert combined["top_artists"][0]["artist"] == "Alpha & Beta"
    assert len(combined["history"]) == len(separate["history"]) == 1
    assert [row["artist"] for row in separate["top_artists"]] == ["Alpha", "Beta"]
    assert [row["count"] for row in separate["top_artists"]] == [1, 1]
    assert [row["total_listen_sec"] for row in separate["top_artists"]] == [120, 120]
    for rank, artist in enumerate(CREDITS, 1):
        detail = await get_entity_detail(
            scope("separate", metric),
            EntityIdentity.create(entity_type="artist", name=artist["name"]),
            db_path=db_path,
        )
        assert detail["entity_id"] == artist["id"]
        assert detail["current_rank"] == rank
        assert detail["total_plays"] == detail["unique_tracks"] == 1
        assert detail["total_listen_sec"] == 120
        assert len(detail["top_tracks"]) == len(detail["recent_plays"]) == 1
        assert detail["top_tracks"][0]["play_count"] == 1
        assert sum(point["play_count"] for point in detail["trend"]) == 1
    before = await get_review_summary(
        2026, db_path=db_path, source_id="source-a", username="listener"
    )
    after = await get_review_summary(
        2026, db_path=db_path, source_id="source-a", username="listener", artist_mode="separate"
    )
    assert [r["name"] for r in after["top_artists"]] == ["Alpha", "Beta"]
    assert {k: v for k, v in before.items() if k != "top_artists"} == {
        k: v for k, v in after.items() if k != "top_artists"
    }


@pytest.mark.asyncio
async def test_relations_deduplicate_other_and_measure_recording_coverage(db_path):
    await init_db(db_path)
    for index in range(5):
        for repeat in range(2):
            await save_play_session(
                play(
                    session_id=f"solo-{index}-{repeat}",
                    artist=f"Top {index}",
                    artists=None,
                    track_id=f"solo-{index}",
                    duration_sec=None,
                ),
                db_path,
            )
    await save_play_session(play(), db_path)
    await save_play_session(
        play(session_id="previous", last_seen_at="2026-07-15T12:00:00Z"), db_path
    )
    result = await get_data_relations(scope(), "artist", db_path=db_path)
    other = next(series for series in result["trend"] if series["key"] == "__other__")
    assert sum(point["play_count"] for point in other["points"]) == 1
    assert sum(point["total_listen_sec"] for point in other["points"]) == 120
    assert result["duration_coverage_pct"] == 9.1  # one recording out of eleven
    for name in ["Alpha", "Beta"]:
        comparison = next(row for row in result["comparison"] if row["label"] == name)
        assert comparison["current_play_count"] == comparison["previous_play_count"] == 1
        row = next(row for row in result["matrix"] if row["label"] == name)
        assert sum(p["play_count"] for p in row["points"]) == 1
    for dimension in ["album", "client"]:
        assert await get_data_relations(
            scope(), dimension, db_path=db_path
        ) == await get_data_relations(scope("combined"), dimension, db_path=db_path)


@pytest.mark.asyncio
async def test_archive_preserves_artists_and_legacy_fingerprints(db_path):
    await init_db(db_path)
    await save_play_session(play(), db_path)
    await save_play_attempt(play(duration_sec=7), db_path)
    exported = await export_user_data("listener", db_path)
    assert exported["format_version"] == 5
    assert exported["records"][0]["artists"] == CREDITS
    assert exported["attempts"][0]["artists"] == CREDITS
    # Older archives compare only fields that were part of their original format.
    legacy = json.loads(json.dumps(exported))
    legacy["format_version"] = 4
    for kind, key in [("history", "records"), ("attempt", "attempts")]:
        for record in legacy[key]:
            record.pop("artists")
            record["fingerprint"] = _record_fingerprint("listener", kind, record)
    result = await import_user_data("listener", legacy, db_path=db_path)
    assert result["skipped"] == 2 and result["conflicts"] == 0
    await delete_user_data("listener", db_path=db_path)
    result = await import_user_data("listener", exported, db_path=db_path)
    assert result["inserted"] == 2
    repeated = await import_user_data("listener", exported, db_path=db_path)
    assert repeated["skipped"] == 2 and repeated["conflicts"] == 0
    restored = await export_user_data("listener", db_path)
    for key in ("records", "attempts"):
        assert restored[key][0]["artists"] == CREDITS
        assert restored[key][0]["fingerprint"] == exported[key][0]["fingerprint"]
    artists = await get_top_artists(db_path=db_path, artist_mode="separate")
    assert [row["count"] for row in artists] == [1, 1]
    assert (await get_summary(db_path=db_path))["total_plays"] == 1
    tampered = json.loads(json.dumps(exported))
    tampered["records"][0]["artists"][1]["name"] = "Gamma"
    assert (await import_user_data("listener", tampered, db_path=db_path))["conflicts"] == 1


@pytest.mark.asyncio
async def test_imported_events_keep_credits_without_duplicate_events(db_path):
    await init_db(db_path)
    event = {
        **play(),
        "played_at": "2026-08-15T12:00:00Z",
        "external_event_key": "event-1",
        "listen_duration_sec": 120,
    }
    assert await save_imported_events([event, event], db_path) == 1
    assert await save_imported_events([event], db_path) == 0
    assert [
        row["count"] for row in await get_top_artists(db_path=db_path, artist_mode="separate")
    ] == [1, 1]


@pytest.mark.asyncio
async def test_api_and_cache_keep_artist_modes_separate(isolated_db, monkeypatch):
    await init_db(isolated_db)
    await save_play_session(play(), isolated_db)
    service = StatsService(cache=DashboardSnapshotCache())
    monkeypatch.setattr("src.routes.stats.stats_service", service)
    common = {"days": 0, "timezone": "UTC", "source_id": "source-a", "username": "listener"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        combined = await client.get("/api/stats/dashboard", params=common)
        separate = await client.get(
            "/api/stats/dashboard", params={**common, "artist_mode": "separate"}
        )
        assert combined.status_code == separate.status_code == 200
        assert len(combined.json()["top_artists"]) == 1
        assert len(separate.json()["top_artists"]) == 2
        assert combined.json()["summary"] == separate.json()["summary"]
        assert (await client.get("/api/stats/dashboard", params=common)).json() == combined.json()
        for endpoint, extra in [
            ("top-artists", {}),
            ("entity-detail", {"entity_type": "artist", "name": "Beta"}),
            ("relations", {"dimension": "artist"}),
            ("review", {"year": 2026}),
        ]:
            response = await client.get(
                "/api/stats/" + endpoint, params={**common, **extra, "artist_mode": "separate"}
            )
            assert response.status_code == 200, response.text
            if endpoint == "entity-detail":
                assert response.json()["total_plays"] == 1
            if endpoint == "review":
                assert response.json()["total_plays"] == 1
                assert len(response.json()["top_artists"]) == 2
        for endpoint in ["dashboard", "top-artists", "entity-detail", "relations", "review"]:
            assert (
                await client.get("/api/stats/" + endpoint, params={"artist_mode": "invalid"})
            ).status_code == 422
    assert scope() != replace(scope(), artist_mode="combined")


@pytest.mark.asyncio
async def test_schema_upgrade_preserves_old_history(db_path):
    await init_db(db_path)
    await save_play_session(play(artists=None), db_path)
    async with connect_db(db_path) as db:
        await db.execute("ALTER TABLE play_history DROP COLUMN artists")
        await db.execute("ALTER TABLE play_attempts DROP COLUMN artists")
        await db.execute("UPDATE schema_meta SET value='13' WHERE key='schema_version'")
        await db.commit()
    await init_db(db_path)
    await init_db(db_path)
    assert (await get_summary(db_path=db_path))["total_plays"] == 1
    assert (await get_top_albums(db_path=db_path))[0]["count"] == 1


def test_single_artist_ids_and_duplicate_artist_ids():
    assert json.loads(artist_credits("Solo", None, "solo-id")) == [
        {"name": "Solo", "id": "solo-id"}
    ]
    duplicate_id = json.dumps([{"name": "Alpha", "id": "a"}, {"name": "Alias", "id": "a"}])
    assert json.loads(artist_credits("Alpha", duplicate_id)) == [{"name": "Alpha", "id": "a"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("artists", [[], "Alpha", [{"name": ""}], [*CREDITS, CREDITS[0]]])
async def test_invalid_archive_artist_metadata_does_not_change_history(db_path, artists):
    await init_db(db_path)
    await save_play_session(play(), db_path)
    exported = await export_user_data("listener", db_path)
    exported["records"][0]["artists"] = artists
    with pytest.raises(ValueError):
        await import_user_data("listener", exported, merge=False, db_path=db_path)
    assert (await get_summary(db_path=db_path))["total_plays"] == 1
