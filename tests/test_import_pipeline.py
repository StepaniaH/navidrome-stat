"""Import-pipeline schema guarantees introduced by schema v11.

Covers the dedup key column on ``play_history``, the per-server backfill
playlist column, and the partial unique index that makes importer re-runs
idempotent at the storage layer.
"""

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

from src.database import init_db
from src.persistence import save_imported_events
from src.stats_service import StatsService


def _open(path):
    conn = sqlite3.connect(path)
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_v11_adds_external_event_key_and_backfill_playlist_id(db_path):
    asyncio.run(init_db(db_path))
    conn = _open(db_path)
    try:
        assert {"external_event_key"} <= _columns(conn, "play_history")
        assert {"backfill_playlist_id"} <= _columns(conn, "servers")
    finally:
        conn.close()


def test_external_event_key_is_unique_when_present(db_path):
    asyncio.run(init_db(db_path))
    conn = _open(db_path)
    try:
        row = (
            "2024-03-24T01:00:00+00:00",
            "import_user",
            None,
            "trk1",
            "Song",
            None,
            None,
            0,
            None,
        )
        columns = (
            "played_at, username, client_name, track_id, title, artist, album, "
            "is_transcoding, listen_duration_sec, source"
        )
        conn.execute(
            f"INSERT INTO play_history ({columns}, external_event_key) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'backfill', ?)",
            (*row, "backfill:test-source:trk1:2024-03-24T01:00:00+00:00"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO play_history ({columns}, external_event_key) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'backfill', ?)",
                (*row, "backfill:test-source:trk1:2024-03-24T01:00:00+00:00"),
            )
    finally:
        conn.close()


def test_rows_without_external_event_key_are_unconstrained(db_path):
    asyncio.run(init_db(db_path))
    conn = _open(db_path)
    try:
        base = (
            "played_at, username, client_name, track_id, title, artist, album, "
            "is_transcoding, listen_duration_sec, source"
        )
        conn.execute(
            f"INSERT INTO play_history ({base}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'poller')",
            ("2024-03-24T01:00:00+00:00", "u", None, "t", "s", None, None, 0, 30),
        )
        conn.execute(
            f"INSERT INTO play_history ({base}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'poller')",
            ("2024-03-25T02:00:00+00:00", "u", None, "t2", "s2", None, None, 0, 30),
        )
        conn.commit()
    finally:
        conn.close()


def _event(track_id: str, played_at: str, source_id: str = "srv-1") -> dict:
    return {
        "external_event_key": f"backfill:{source_id}:{track_id}:{played_at}",
        "played_at": played_at,
        "username": "alice",
        "client_name": None,
        "track_id": track_id,
        "title": f"Song {track_id}",
        "artist": "Artist A",
        "artist_id": None,
        "album": "Album X",
        "is_transcoding": 0,
        "listen_duration_sec": None,
        "duration_confidence": "estimated",
        "source": "backfill",
        "source_id": source_id,
        "source_name": "Home",
    }


def test_save_imported_events_is_idempotent(db_path):
    asyncio.run(init_db(db_path))
    events = [_event("trk-1", "2024-03-24T01:00:00+00:00")]

    first = asyncio.run(save_imported_events(events, db_path=db_path))
    second = asyncio.run(save_imported_events(events, db_path=db_path))
    mixed = asyncio.run(
        save_imported_events(
            [
                _event("trk-1", "2024-03-24T01:00:00+00:00"),
            ],
            db_path=db_path,
        )
    )
    new_only = asyncio.run(
        save_imported_events(
            [
                _event("trk-1", "2024-03-24T01:00:00+00:00"),
                _event("trk-2", "2024-03-25T01:00:00+00:00"),
            ],
            db_path=db_path,
        )
    )

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
        stored = conn.execute(
            "SELECT source, username, track_id FROM play_history "
            "WHERE external_event_key IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    assert (first, second, mixed, new_only) == (1, 0, 0, 1)
    assert count == 2
    assert stored == [("backfill", "alice", "trk-1"), ("backfill", "alice", "trk-2")]


class FakeCache:
    def __init__(self):
        self.invalidations = 0

    async def invalidate(self):
        self.invalidations += 1


def test_record_imported_events_invalidates_only_on_new_rows(monkeypatch):
    import src.stats_service as stats_module

    cache = FakeCache()
    service = StatsService(cache=cache, retry_attempts=1)

    monkeypatch.setattr(stats_module, "save_imported_events", AsyncMock(return_value=0))
    asyncio.run(service.record_imported_events([_event("t1", "2024-03-24T01:00:00+00:00")]))
    assert cache.invalidations == 0

    monkeypatch.setattr(stats_module, "save_imported_events", AsyncMock(return_value=3))
    asyncio.run(service.record_imported_events([_event("t2", "2024-03-25T01:00:00+00:00")]))
    assert cache.invalidations == 1
