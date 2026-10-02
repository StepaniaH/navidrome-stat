import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

from src.artist_backfill import apply_artist_backfill, preview_artist_backfill
from src.database import init_db, save_play_attempt, save_play_session
from src.persistence import save_imported_events
from src.server_registry import save_server
from src.stats_query_rankings import get_top_artists

CREDITS = [{"name": "Alpha", "id": "a"}, {"name": "Beta", "id": "b"}]


def play(session_id, **kwargs):
    return {
        "session_id": session_id, "last_seen_at": "2026-08-15T12:00:00Z",
        "username": "listener", "source_id": "source-a", "track_id": "duet",
        "artist": "Alpha with Beta and Band", "duration_sec": 60, "finalized": True,
        **kwargs,
    }


@pytest.mark.asyncio
async def test_backfill_preview_is_read_only_and_apply_preserves_all_other_fields(db_path):
    await init_db(db_path)
    await save_play_session(play("first"), db_path)
    await save_play_session(play("repeat"), db_path)
    await save_play_session(play("other-source", source_id="source-b"), db_path)
    await save_play_session(play("explicit", artists=[{"name": "Band", "id": "band"}]), db_path)
    await save_play_attempt(play("short", duration_sec=5), db_path)
    await save_imported_events([{
        **play("push"), "external_event_key": "push-event", "source": "listenbrainz",
        "played_at": "2026-08-15T12:00:00Z",
    }], db_path)
    with sqlite3.connect(db_path) as db:
        before = {
            table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            for table in ("play_history", "play_attempts")
        }
    resolver = AsyncMock()
    resolver.get_artists.return_value = CREDITS
    preview = await preview_artist_backfill(db_path, "source-a", resolver)
    assert preview["tracks_checked"] == preview["tracks_resolved"] == 1
    assert (preview["history_rows"], preview["attempt_rows"]) == (2, 1)
    resolver.get_artists.assert_awaited_once_with("duet")
    with sqlite3.connect(db_path) as db:
        for table, rows in before.items():
            assert db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() == rows
    assert await apply_artist_backfill(db_path, preview) == {"history_rows": 2, "attempt_rows": 1}
    assert await apply_artist_backfill(db_path, preview) == {"history_rows": 0, "attempt_rows": 0}
    with sqlite3.connect(db_path) as db:
        for table, rows in before.items():
            cursor = db.execute(f"SELECT * FROM {table} ORDER BY id")
            artists_index = [column[0] for column in cursor.description].index("artists")
            after = cursor.fetchall()
            assert len(after) == len(rows)
            for old, new in zip(rows, after):
                assert old[:artists_index] + old[artists_index + 1:] == (
                    new[:artists_index] + new[artists_index + 1:]
                )
        stored = db.execute(
            "SELECT session_id, artists FROM play_history WHERE session_id IS NOT NULL"
        ).fetchall()
    assert dict(stored)["other-source"] is None
    assert json.loads(dict(stored)["explicit"]) == [{"name": "Band", "id": "band"}]
    artists = await get_top_artists(db_path=db_path, source_id="source-a", artist_mode="separate")
    counts = {row["artist"]: row["count"] for row in artists}
    assert counts["Alpha"] == counts["Beta"] == 2
    assert counts["Alpha with Beta and Band"] == 1  # Unchanged ListenBrainz row.


@pytest.mark.asyncio
async def test_backfill_pages_past_unresolvable_tracks_and_preserves_newer_metadata(db_path):
    await init_db(db_path)
    for track in ["a", "b", "c"]:
        await save_play_session(play(track, track_id=track), db_path)
    resolver = AsyncMock()
    resolver.get_artists.side_effect = [[], CREDITS]
    first = await preview_artist_backfill(db_path, "source-a", resolver, limit=1)
    assert first["unresolved_tracks"] == 1
    assert first["next_after_track_id"] == "a"
    assert await apply_artist_backfill(db_path, first) == {"history_rows": 0, "attempt_rows": 0}
    second = await preview_artist_backfill(
        db_path, "source-a", resolver, limit=1, after_track_id=first["next_after_track_id"],
    )
    assert second["changes"][0]["track_id"] == "b"
    assert second["next_after_track_id"] == "b"
    await save_play_session(play("b", track_id="b", artists=[{"name": "Newer", "id": "new"}]), db_path)
    assert await apply_artist_backfill(db_path, second) == {"history_rows": 0, "attempt_rows": 0}


@pytest.mark.parametrize("source_id", ["source-a", "legacy"])
def test_cli_previews_by_default_and_uses_only_the_selected_connection(
    db_path, source_id, monkeypatch, capsys,
):
    from src.artist_backfill import main

    asyncio.run(init_db(db_path))
    asyncio.run(save_play_session(play("first", source_id=source_id), db_path))
    asyncio.run(save_server({
        "id": "source-a", "display_name": "Synthetic source",
        "url": "http://navidrome.example.invalid", "username": "listener",
        "password": "synthetic-password", "enabled": True,
    }, db_path))
    client = AsyncMock()
    client.get_song.return_value = {"subsonic-response": {
        "status": "ok", "song": {"id": "duet", "artists": CREDITS},
    }}
    factory = Mock(return_value=client)
    monkeypatch.setattr("src.artist_backfill.NavidromeClient", factory)
    command = ["artist-backfill", "--source-id", source_id, "--database", db_path]
    monkeypatch.setattr("sys.argv", command)
    assert main() == 0
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == "preview"
    assert json.loads(output)["history_rows"] == 1
    assert "synthetic-password" not in output and "example.invalid" not in output
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT artists FROM play_history").fetchone() == (None,)
    if source_id == "legacy":
        factory.assert_called_once_with()
    else:
        factory.assert_called_once_with(
            "http://navidrome.example.invalid", "listener", "synthetic-password",
        )
    client.close.assert_awaited_once()

    monkeypatch.setattr("sys.argv", [*command, "--apply"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["updated"] == {"history_rows": 1, "attempt_rows": 0}
    with sqlite3.connect(db_path) as db:
        assert json.loads(db.execute("SELECT artists FROM play_history").fetchone()[0]) == CREDITS
    assert client.close.await_count == 2


def test_cli_does_not_create_a_missing_database(tmp_path, monkeypatch, capsys):
    from src.artist_backfill import main

    missing = tmp_path / "missing.db"
    factory = Mock()
    monkeypatch.setattr("src.artist_backfill.NavidromeClient", factory)
    monkeypatch.setattr("sys.argv", [
        "artist-backfill", "--source-id", "legacy", "--database", str(missing), "--apply",
    ])
    assert main() == 1
    assert not missing.exists()
    assert json.loads(capsys.readouterr().out) == {"error": "ValueError"}
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_rolls_back_history_if_attempt_update_fails(db_path):
    await init_db(db_path)
    await save_play_session(play("first"), db_path)
    await save_play_attempt(play("short", duration_sec=5), db_path)
    resolver = AsyncMock()
    resolver.get_artists.return_value = CREDITS
    preview = await preview_artist_backfill(db_path, "source-a", resolver)
    with sqlite3.connect(db_path) as db:
        db.execute("""
            CREATE TRIGGER reject_attempt_update BEFORE UPDATE ON play_attempts
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END
        """)
    with pytest.raises(sqlite3.IntegrityError):
        await apply_artist_backfill(db_path, preview)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT artists FROM play_history").fetchone() == (None,)
        assert db.execute("SELECT artists FROM play_attempts").fetchone() == (None,)
