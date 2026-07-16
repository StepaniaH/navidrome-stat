import pytest
from datetime import datetime, timedelta, timezone

from src.database import init_db, save_play_session
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
async def test_retention_preview_and_purge(db_path):
    await init_db(db_path)
    old_at = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    recent_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await save_play_session(_session("alice", old_at), db_path=db_path)
    await save_play_session(_session("alice", recent_at, "t2"), db_path=db_path)

    await set_retention_days(30, db_path)
    preview = await preview_retention_purge(db_path=db_path)
    assert preview["records_to_delete"] == 1

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
    await delete_user_data("carol", db_path=db_path)
    assert (await preview_delete_user("carol", db_path))["records_to_delete"] == 0

    imported = await import_user_data("carol", payload, merge=True, db_path=db_path)
    assert imported["imported"] == 1
    restored = await export_user_data("carol", db_path=db_path)
    assert restored["record_count"] == 1


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
async def test_delete_user_preview_and_apply(db_path):
    await init_db(db_path)
    await save_play_session(_session("dave", "2025-01-01T00:00:00+00:00"), db_path=db_path)
    await save_play_session(_session("dave", "2025-02-01T00:00:00+00:00", "t2"), db_path=db_path)

    preview = await preview_delete_user("dave", db_path=db_path)
    assert preview["records_to_delete"] == 2

    deleted = await delete_user_data("dave", db_path=db_path)
    assert deleted["deleted"] == 2
