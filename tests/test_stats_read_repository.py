"""StatsReadRepository keeps one connection and one dashboard read snapshot."""

import sqlite3

import pytest

import src.sqlite as sqlite_module
import src.stats_read_repository as repository_module
from src.schema import init_db
from src.stats_query_entities import EntityIdentity
from src.stats_read_repository import StatsReadRepository
from src.stats_scope import StatsScope


def _insert_history(path: str, track_id: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """
            INSERT INTO play_history (
                played_at, username, client_name, track_id, title, artist,
                album, is_transcoding, listen_duration_sec, source,
                source_id, source_name, finalized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "2026-08-30T00:00:00+00:00",
                "synthetic-user",
                "Synthetic Client",
                track_id,
                track_id,
                "Synthetic Artist",
                "Synthetic Album",
                0,
                60,
                "poller",
                "synthetic-source",
                "Synthetic Source",
            ),
        )


@pytest.mark.asyncio
async def test_dashboard_reuses_one_connection_and_read_snapshot(tmp_path, monkeypatch):
    db_path = str(tmp_path / "stats.db")
    await init_db(db_path)
    _insert_history(db_path, "before-snapshot")

    connect_calls = 0
    original_connect = sqlite_module.aiosqlite.connect

    def counting_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        return original_connect(*args, **kwargs)

    original_summary = repository_module.get_summary

    async def summary_then_write(**kwargs):
        summary = await original_summary(**kwargs)
        _insert_history(db_path, "after-snapshot")
        return summary

    monkeypatch.setattr(sqlite_module.aiosqlite, "connect", counting_connect)
    monkeypatch.setattr(repository_module, "get_summary", summary_then_write)

    snapshot = await StatsReadRepository(db_path).dashboard(StatsScope.create(
        days=0,
        timezone_name="UTC",
        metric="plays",
        source_id=None,
        start_date=None,
        end_date=None,
    ))

    assert connect_calls == 1
    assert snapshot["summary"]["total_plays"] == 1
    assert sum(player["count"] for player in snapshot["players"]) == 1
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM play_history").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_dashboard_records_each_fixed_query_timing(tmp_path, monkeypatch):
    from src.runtime_state import RuntimeState

    db_path = str(tmp_path / "stats.db")
    await init_db(db_path)
    state = RuntimeState()
    monkeypatch.setattr(repository_module, "runtime_state", state)

    await StatsReadRepository(db_path).dashboard(StatsScope.create(days=30))

    assert set(state.stats_query_timings) == {
        "summary",
        "players",
        "transcoding",
        "time_buckets",
        "history",
        "servers",
        "available_servers",
        "top_artists",
        "top_albums",
    }
    assert all(timing.count == 1 for timing in state.stats_query_timings.values())


@pytest.mark.asyncio
async def test_entity_detail_uses_one_snapshot_and_fixed_query_timing(tmp_path, monkeypatch):
    from src.runtime_state import RuntimeState

    db_path = str(tmp_path / "stats.db")
    await init_db(db_path)
    _insert_history(db_path, "entity-track")
    state = RuntimeState()
    monkeypatch.setattr(repository_module, "runtime_state", state)

    connect_calls = 0
    original_connect = sqlite_module.aiosqlite.connect

    def counting_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite_module.aiosqlite, "connect", counting_connect)
    detail = await StatsReadRepository(db_path).entity_detail(
        StatsScope.create(days=0, timezone_name="UTC", metric="plays"),
        EntityIdentity.create(entity_type="artist", name="Synthetic Artist"),
    )

    assert connect_calls == 1
    assert detail["total_plays"] == 1
    assert set(state.stats_query_timings) == {"entity_detail"}
    assert state.stats_query_timings["entity_detail"].count == 1
