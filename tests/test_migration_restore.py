"""Schema-migration and backup/restore regression checks.

The migration cases replay real pre-upgrade layouts built by
``tests.migration_fixtures``; the restore case performs the documented
export -> fresh database -> import round trip and compares aggregates.
"""

import asyncio
import sqlite3

import pytest

from src.database import (
    get_playback_history,
    get_summary,
    init_db,
    save_play_session,
)
from src.privacy_ops import export_user_data, import_user_data
from tests.migration_fixtures import build_legacy_db

CURRENT_SCHEMA_VERSION = 13


@pytest.mark.parametrize("from_version", [0, 2, 4])
def test_legacy_databases_upgrade_with_row_and_metadata_preserved(db_path, from_version):
    asyncio.run(_assert_legacy_upgrade(db_path, from_version))


async def _assert_legacy_upgrade(db_path: str, from_version: int):
    version = await build_legacy_db(db_path, from_version=from_version)
    assert version == CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(play_history)")}
    rows = conn.execute(
        "SELECT played_at, username, artist, listen_duration_sec FROM play_history"
    ).fetchall()
    source_ids = conn.execute(
        "SELECT DISTINCT COALESCE(source_id, 'x'), COALESCE(source_name, 'y') FROM play_history"
    ).fetchall()
    record_ids = conn.execute("SELECT record_id FROM play_history").fetchall()
    meta = dict(conn.execute("SELECT key, value FROM schema_meta").fetchall())
    conn.close()

    assert rows == [("2024-03-24T01:00:00+00:00", "legacy_user", "Artist A", 45)]
    # Provenance columns and their legacy backfill exist on every start point.
    assert {
        "source",
        "source_id",
        "source_name",
        "session_id",
        "artist_id",
        "album_id",
        "record_id",
    } <= columns
    assert len(record_ids[0][0]) == 32
    assert source_ids == [("legacy", "Legacy environment source")]
    if from_version < 2:
        # Only upgrades from pre-v2 databases backfill the retention key;
        # later releases treat a missing key as permanent at read time.
        assert meta["retention_days"] == "permanent"


def test_repeated_init_is_idempotent_after_legacy_migration(db_path):
    first = asyncio.run(build_legacy_db(db_path, from_version=0))
    second = asyncio.run(init_db(db_path))

    conn = sqlite3.connect(db_path)
    version = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[
        0
    ]
    count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
    conn.close()

    assert first == CURRENT_SCHEMA_VERSION
    assert second is None
    assert version == str(CURRENT_SCHEMA_VERSION)
    assert count == 1


def test_export_import_roundtrip_restores_user_aggregates(isolated_db):
    asyncio.run(_roundtrip(isolated_db))


async def _seed(source_db: str):
    for index, duration in enumerate((30, 75), start=1):
        await save_play_session(
            {
                "last_seen_at": f"2024-03-2{index}T12:00:00Z",
                "username": "roundtrip_user",
                "client_name": "Web Player",
                "track_id": f"t{index}",
                "title": f"Song {index}",
                "artist": "Artist A",
                "album": "Album X",
                "is_transcoding": 0,
                "duration_sec": duration,
            },
            db_path=source_db,
        )


async def _roundtrip(db_path: str):
    await init_db(db_path)
    await _seed(db_path)

    payload = await export_user_data("roundtrip_user", db_path=db_path)
    assert payload["record_count"] == 2

    restored = f"{db_path}.restored"
    await init_db(restored)
    result = await import_user_data("roundtrip_user", payload, merge=False, db_path=restored)
    assert result["imported"] == 2

    original_summary = await get_summary(days=0, db_path=db_path)
    restored_summary = await get_summary(days=0, db_path=restored)
    for key in ("total_plays", "total_listen_sec"):
        assert restored_summary[key] == original_summary[key], key

    original_history = await get_playback_history(username="roundtrip_user", db_path=db_path)
    restored_history = await get_playback_history(username="roundtrip_user", db_path=restored)
    assert len(restored_history) == len(original_history)

    conn = sqlite3.connect(restored)
    imported_count = conn.execute(
        "SELECT COUNT(*) FROM play_history WHERE username = 'roundtrip_user'"
    ).fetchone()[0]
    conn.close()
    assert imported_count == 2
