import json
from datetime import datetime, timedelta, timezone

import pytest

from src.database import init_db, save_play_attempt, save_play_session
from src.importers.cursor_store import (
    load_song_history_cursor,
    save_song_history_cursor,
)
from src.privacy_ops import (
    apply_retention_purge,
    delete_user_data,
    export_user_data,
    get_retention_days,
    import_user_data,
    preview_delete_user,
    preview_retention_purge,
    set_retention_days,
)


def _session(username: str, played_at: str, track_id: str = "t1"):
    return {
        "last_seen_at": played_at,
        "username": username,
        "client_name": "Web",
        "track_id": track_id,
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "is_transcoding": 0,
        "duration_sec": 45,
    }


@pytest.mark.asyncio
async def test_retention_defaults_to_permanent(db_path):
    await init_db(db_path)
    assert await get_retention_days(db_path) is None


@pytest.mark.asyncio
async def test_get_storage_stats_reports_file_size(db_path):
    await init_db(db_path)
    await save_play_session(_session("alice", "2025-01-01T00:00:00+00:00"), db_path=db_path)

    from src.privacy_ops import get_storage_stats

    stats = await get_storage_stats(db_path)
    assert stats["total_records"] == 1
    assert stats["database_bytes"] > 0
    assert stats["estimated_data_bytes"] > 0


@pytest.mark.asyncio
async def test_retention_preview_includes_size_estimates(db_path):
    await init_db(db_path)
    old_at = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    recent_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await save_play_session(_session("alice", old_at), db_path=db_path)
    await save_play_session(_session("alice", recent_at, "t2"), db_path=db_path)

    await set_retention_days(30, db_path)
    preview = await preview_retention_purge(db_path=db_path)
    assert preview["records_to_delete"] == 1
    assert preview["bytes_to_delete"] > 0
    assert preview["estimated_database_bytes_after"] <= preview["database_bytes"]

    result = await apply_retention_purge(db_path=db_path)
    assert result["deleted"] == 1

    export = await export_user_data("alice", db_path=db_path)
    assert export["record_count"] == 1
    assert export["records"][0]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_permanent_retention_does_not_purge(db_path):
    await init_db(db_path)
    await save_play_session(_session("bob", "2020-01-01T00:00:00+00:00"), db_path=db_path)
    await set_retention_days(None, db_path)

    preview = await preview_retention_purge(db_path=db_path)
    assert preview["records_to_delete"] == 0
    result = await apply_retention_purge(db_path=db_path)
    assert result["deleted"] == 0


@pytest.mark.asyncio
async def test_export_import_roundtrip(db_path):
    await init_db(db_path)
    await save_play_session(_session("carol", "2025-06-01T12:00:00+00:00"), db_path=db_path)

    payload = await export_user_data("carol", db_path=db_path)
    assert payload["format_version"] == 3
    assert payload["records"][0]["record_id"]
    assert payload["records"][0]["fingerprint"]
    await delete_user_data("carol", db_path=db_path)
    assert (await preview_delete_user("carol", db_path))["records_to_delete"] == 0

    imported = await import_user_data("carol", payload, merge=True, db_path=db_path)
    assert imported["imported"] == 1
    restored = await export_user_data("carol", db_path=db_path)
    assert restored["record_count"] == 1

    repeated = await import_user_data("carol", payload, merge=True, db_path=db_path)
    assert repeated["inserted"] == 0
    assert repeated["skipped"] == 1
    assert repeated["conflicts"] == 0
    assert (await export_user_data("carol", db_path=db_path))["record_count"] == 1

    conflicting = json.loads(json.dumps(payload))
    conflicting["records"][0]["title"] = "Conflicting title"
    conflicting["records"][0]["fingerprint"] = "0" * 64
    conflict_result = await import_user_data(
        "carol", conflicting, merge=True, db_path=db_path
    )
    assert conflict_result["inserted"] == 0
    assert conflict_result["skipped"] == 0
    assert conflict_result["conflicts"] == 1


@pytest.mark.asyncio
async def test_import_rejects_username_mismatch(db_path):
    await init_db(db_path)
    payload = {
        "format_version": 1,
        "username": "other",
        "records": [
            {
                "played_at": "2025-01-01T00:00:00+00:00",
                "track_id": "t1",
            }
        ],
    }
    with pytest.raises(ValueError, match="username"):
        await import_user_data("carol", payload, db_path=db_path)


@pytest.mark.asyncio
async def test_legacy_v2_merge_is_idempotent(db_path):
    await init_db(db_path)
    payload = {
        "format_version": 2,
        "username": "legacy-user",
        "records": [
            {
                "played_at": "2025-01-01T00:00:00+00:00",
                "track_id": "legacy-track",
                "listen_duration_sec": 30,
            }
        ],
    }

    first = await import_user_data("legacy-user", payload, merge=True, db_path=db_path)
    second = await import_user_data("legacy-user", payload, merge=True, db_path=db_path)

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped"] == 1
    assert (await export_user_data("legacy-user", db_path=db_path))["record_count"] == 1


@pytest.mark.asyncio
async def test_replace_import_conflict_does_not_delete_existing_rows(db_path):
    await init_db(db_path)
    await save_play_session(
        _session("protected-user", "2025-01-01T00:00:00+00:00"),
        db_path=db_path,
    )
    payload = await export_user_data("protected-user", db_path=db_path)
    payload["records"][0]["title"] = "Corrupted"

    result = await import_user_data(
        "protected-user",
        payload,
        merge=False,
        db_path=db_path,
    )

    assert result["conflicts"] == 1
    restored = await export_user_data("protected-user", db_path=db_path)
    assert restored["record_count"] == 1
    assert restored["records"][0]["title"] == "Song"


@pytest.mark.asyncio
async def test_replace_import_cross_user_id_conflict_rolls_back(db_path):
    await init_db(db_path)
    await save_play_session(
        _session("alice", "2025-01-01T00:00:00+00:00", "alice-track"),
        db_path=db_path,
    )
    await save_play_session(
        _session("bob", "2025-02-01T00:00:00+00:00", "bob-track"),
        db_path=db_path,
    )
    alice_export = await export_user_data("alice", db_path=db_path)
    bob_export = await export_user_data("bob", db_path=db_path)
    original_bob_id = bob_export["records"][0]["record_id"]
    bob_export["records"][0]["record_id"] = alice_export["records"][0]["record_id"]

    result = await import_user_data("bob", bob_export, merge=False, db_path=db_path)

    assert result == {
        "imported": 0,
        "attempts_imported": 0,
        "inserted": 0,
        "skipped": 0,
        "conflicts": 1,
        "merge": 0,
    }
    restored = await export_user_data("bob", db_path=db_path)
    assert restored["record_count"] == 1
    assert restored["records"][0]["record_id"] == original_bob_id
    assert restored["records"][0]["track_id"] == "bob-track"


@pytest.mark.asyncio
async def test_delete_user_preview_and_apply(db_path):
    await init_db(db_path)
    await save_play_session(_session("dave", "2025-01-01T00:00:00+00:00"), db_path=db_path)
    await save_play_session(_session("dave", "2025-02-01T00:00:00+00:00", "t2"), db_path=db_path)

    preview = await preview_delete_user("dave", db_path=db_path)
    assert preview["records_to_delete"] == 2

    deleted = await delete_user_data("dave", db_path=db_path)
    assert deleted["deleted"] == 2


@pytest.mark.asyncio
async def test_delete_user_seals_history_import_cursor(db_path):
    await init_db(db_path)
    await save_play_session(
        {
            **_session("dave", "2025-01-01T00:00:00+00:00"),
            "source_id": "server-a",
        },
        db_path=db_path,
    )
    await save_song_history_cursor(
        "server-a",
        "dave",
        {
            "next_offset": 37,
            "complete": False,
            "failure_count": 2,
            "retry_at": "2026-08-30T03:00:00+00:00",
        },
        db_path=db_path,
    )

    await delete_user_data("dave", db_path=db_path)

    cursor = await load_song_history_cursor("server-a", "dave", db_path=db_path)
    assert cursor == {
        "next_offset": 37,
        "complete": True,
        "failure_count": 0,
        "retry_at": None,
    }


@pytest.mark.asyncio
async def test_retention_preview_matches_history_and_attempt_deletion(db_path):
    await init_db(db_path)
    old_at = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    await save_play_session(_session("synthetic-user", old_at), db_path=db_path)
    await save_play_attempt(
        {
            **_session("synthetic-user", old_at, "short-track"),
            "last_seen_at": old_at,
            "duration_sec": 5,
            "outcome": "short_play",
        },
        db_path=db_path,
    )
    await set_retention_days(30, db_path)

    preview = await preview_retention_purge(db_path=db_path)
    assert preview["records_to_delete"] == 2
    assert preview["history_records_to_delete"] == 1
    assert preview["attempt_records_to_delete"] == 1

    result = await apply_retention_purge(db_path=db_path)
    assert result == {
        "deleted": 2,
        "history_deleted": 1,
        "attempts_deleted": 1,
        "retention_days": 30,
    }


@pytest.mark.asyncio
async def test_retention_compares_offset_timestamps_by_instant(db_path, monkeypatch):
    await init_db(db_path)

    frozen = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    monkeypatch.setattr("src.privacy_ops.datetime", FrozenDateTime)

    # 2026-07-22 09:00 UTC, encoded as +14:00 so a string compare against a
    # space-separated UTC cutoff would keep the row.
    old_at = "2026-07-22T23:00:00+14:00"
    recent_at = "2026-08-20T10:00:00+00:00"
    await save_play_session(
        _session("synthetic-user", old_at, "old-offset"),
        db_path=db_path,
    )
    await save_play_session(
        _session("synthetic-user", recent_at, "recent"),
        db_path=db_path,
    )
    await set_retention_days(30, db_path)

    preview = await preview_retention_purge(db_path=db_path)
    assert preview["records_to_delete"] == 1
    result = await apply_retention_purge(db_path=db_path)
    assert result["deleted"] == 1

    export = await export_user_data("synthetic-user", db_path=db_path)
    assert export["record_count"] == 1
    assert export["records"][0]["track_id"] == "recent"


@pytest.mark.asyncio
async def test_export_v3_roundtrips_short_attempts(db_path):
    await init_db(db_path)
    played_at = "2025-01-01T00:00:00+00:00"
    await save_play_attempt(
        {
            **_session("synthetic-user", played_at, "short-track"),
            "last_seen_at": played_at,
            "duration_sec": 7,
            "outcome": "short_play",
            "duration_confidence": "reported",
        },
        db_path=db_path,
    )
    payload = await export_user_data("synthetic-user", db_path=db_path)
    assert payload["format_version"] == 3
    assert payload["attempt_count"] == 1
    assert payload["attempts"][0]["record_id"]
    assert payload["attempts"][0]["fingerprint"]

    await delete_user_data("synthetic-user", db_path=db_path)
    imported = await import_user_data(
        "synthetic-user",
        payload,
        db_path=db_path,
    )
    assert imported["attempts_imported"] == 1
    repeated = await import_user_data(
        "synthetic-user",
        payload,
        db_path=db_path,
    )
    assert repeated["attempts_imported"] == 0
    assert repeated["skipped"] == 1
    restored = await export_user_data("synthetic-user", db_path=db_path)
    assert restored["attempts"][0]["duration_sec"] == 7


@pytest.mark.asyncio
async def test_import_rejects_naive_timestamp_and_excessive_duration(db_path):
    await init_db(db_path)
    base = {
        "format_version": 2,
        "username": "synthetic-user",
        "records": [{"played_at": "2025-01-01T00:00:00", "track_id": "track"}],
    }
    with pytest.raises(ValueError, match="timezone"):
        await import_user_data("synthetic-user", base, db_path=db_path)

    base["records"][0]["played_at"] = "2025-01-01T00:00:00+00:00"
    base["records"][0]["listen_duration_sec"] = 9_999_999
    with pytest.raises(ValueError, match="between"):
        await import_user_data("synthetic-user", base, db_path=db_path)
