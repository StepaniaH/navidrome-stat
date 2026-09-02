import asyncio
import sqlite3

from src.database import (
    get_playback_history,
    get_summary,
    init_db,
    ping_db,
    save_play_session,
)


def test_init_db_creates_missing_data_directory(tmp_path):
    db_path = tmp_path / ".data" / "navidrome_stats.db"
    asyncio.run(init_db(str(db_path)))
    assert db_path.is_file()


def test_save_play_session(db_path):
    asyncio.run(init_db(db_path))

    session = {
        "last_seen_at": "2024-03-24T12:00:00Z",
        "username": "testuser",
        "client_name": "Web Player",
        "track_id": "t1",
        "title": "Song 1",
        "artist": "Artist A",
        "album": "Album X",
        "is_transcoding": 0,
        "duration_sec": 120,
    }

    asyncio.run(save_play_session(session, db_path=db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM play_history")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][2] == "testuser"
    assert rows[0][3] == "Web Player"
    assert rows[0][5] == "Song 1"
    assert rows[0][9] == 120


def test_schema_migration_is_idempotent(db_path):
    asyncio.run(init_db(db_path))
    asyncio.run(init_db(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'")
    assert cursor.fetchone()[0] == "14"
    cursor.execute("SELECT value FROM schema_meta WHERE key = 'retention_days'")
    assert cursor.fetchone()[0] == "permanent"
    cursor.execute("PRAGMA index_list(play_history)")
    index_names = {row[1] for row in cursor.fetchall()}
    cursor.execute("PRAGMA index_list(play_attempts)")
    attempt_index_names = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "idx_play_history_user_track" in index_names
    assert "idx_play_history_played_at" in index_names
    assert "idx_play_history_played_at_epoch" in index_names
    assert "idx_play_history_source_user_epoch" in index_names
    assert "idx_play_history_user_epoch" in index_names
    assert "idx_play_attempts_played_at_epoch" in attempt_index_names
    assert "idx_play_attempts_source_user_epoch" in attempt_index_names


def test_schema_migration_adds_artist_id_columns(db_path):
    asyncio.run(init_db(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(play_history)")
    history_columns = {row[1] for row in cursor.fetchall()}
    cursor.execute("PRAGMA table_info(play_attempts)")
    attempt_columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "artist_id" in history_columns
    assert "artist_id" in attempt_columns


def test_schema_maintains_sortable_played_at_epoch(db_path):
    asyncio.run(init_db(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO play_history (played_at) VALUES (?)",
        ("2024-03-24T12:00:00+00:00",),
    )
    row_id, epoch = conn.execute("SELECT id, played_at_epoch FROM play_history").fetchone()
    assert epoch == 1711281600

    conn.execute(
        "UPDATE play_history SET played_at = ? WHERE id = ?",
        ("2024-03-24T13:00:00+00:00", row_id),
    )
    updated = conn.execute(
        "SELECT played_at_epoch FROM play_history WHERE id = ?", (row_id,)
    ).fetchone()[0]
    conn.close()
    assert updated == 1711285200


def test_startup_recovers_incomplete_checkpoint_without_duplicate(db_path):
    asyncio.run(init_db(db_path))
    checkpoint = {
        "session_id": "synthetic-interrupted-session",
        "last_seen_at": "2024-03-24T12:01:00+00:00",
        "username": "synthetic-user",
        "client_name": "Synthetic Player",
        "track_id": "track-1",
        "title": "Synthetic Song",
        "artist": "Synthetic Artist",
        "album": "Synthetic Album",
        "is_transcoding": 0,
        "duration_sec": 60,
        "finalized": False,
    }
    asyncio.run(save_play_session(checkpoint, db_path=db_path))

    # A later process startup finalizes the last durable observation without
    # inventing extra time or inserting another play.
    asyncio.run(init_db(db_path))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT COUNT(*), listen_duration_sec, finalized, finalized_at,
               checkpointed_at, duration_confidence
        FROM play_history WHERE session_id = ?
        """,
        ("synthetic-interrupted-session",),
    ).fetchone()
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()

    assert row == (
        1,
        60,
        1,
        "2024-03-24T12:01:00+00:00",
        "2024-03-24T12:01:00+00:00",
        "lower_bound",
    )
    assert journal_mode == "wal"
    # Foreign keys are connection-local; direct sqlite3 callers remain off.
    assert foreign_keys == 0


def test_get_playback_history_aggregates_and_uses_latest_metadata(db_path):
    asyncio.run(init_db(db_path))

    sessions = [
        {
            "last_seen_at": "2024-03-24T12:00:00Z",
            "username": "testuser",
            "client_name": "Web Player",
            "track_id": "t1",
            "title": "Old Title",
            "artist": "Artist A",
            "album": "Album X",
            "is_transcoding": 0,
            "duration_sec": 30,
        },
        {
            "last_seen_at": "2024-03-24T13:00:00Z",
            "username": "testuser",
            "client_name": "Web Player",
            "track_id": "t1",
            "title": "New Title",
            "artist": "Artist A",
            "album": "Album X",
            "is_transcoding": 0,
            "duration_sec": 45,
        },
    ]

    for session in sessions:
        asyncio.run(save_play_session(session, db_path=db_path))

    history = asyncio.run(get_playback_history(limit=10, db_path=db_path))

    assert len(history) == 1
    assert history[0]["play_count"] == 2
    assert history[0]["title"] == "New Title"
    assert history[0]["total_listen_sec"] == 75
    assert history[0]["last_played_at"] == "2024-03-24T13:00:00Z"


def test_get_summary_aggregates_totals(db_path):
    asyncio.run(init_db(db_path))

    sessions = [
        {
            "last_seen_at": "2024-03-24T12:00:00Z",
            "username": "testuser",
            "client_name": "Web Player",
            "track_id": "t1",
            "title": "Song 1",
            "artist": "Artist A",
            "album": "Album X",
            "is_transcoding": 0,
            "duration_sec": 30,
        },
        {
            "last_seen_at": "2024-03-24T13:00:00Z",
            "username": "testuser",
            "client_name": "Mobile",
            "track_id": "t2",
            "title": "Song 2",
            "artist": "Artist B",
            "album": "Album Y",
            "is_transcoding": 1,
            "duration_sec": 45,
        },
    ]
    for session in sessions:
        asyncio.run(save_play_session(session, db_path=db_path))

    summary = asyncio.run(get_summary(db_path=db_path))

    assert summary["total_plays"] == 2
    assert summary["total_listen_sec"] == 75
    assert summary["unique_tracks"] == 2
    assert summary["client_count"] == 2


def test_ping_db_returns_true_for_initialized_database(db_path):
    asyncio.run(init_db(db_path))
    assert asyncio.run(ping_db(db_path)) is True


def test_session_checkpoint_upserts_final_duration_without_duplicate(db_path):
    asyncio.run(init_db(db_path))
    checkpoint = {
        "session_id": "synthetic-session-id",
        "last_seen_at": "2024-03-24T12:00:30+00:00",
        "username": "synthetic-user",
        "client_name": "Synthetic Player",
        "track_id": "track-1",
        "title": "Synthetic Song",
        "artist": "Synthetic Artist",
        "album": "Synthetic Album",
        "is_transcoding": 0,
        "duration_sec": 30,
        "duration_confidence": "reported",
        "finalized": False,
    }
    asyncio.run(save_play_session(checkpoint, db_path=db_path))
    asyncio.run(
        save_play_session(
            {
                **checkpoint,
                "last_seen_at": "2024-03-24T12:02:00+00:00",
                "duration_sec": 120,
                "finalized": True,
                "finalized_at": "2024-03-24T12:02:00+00:00",
            },
            db_path=db_path,
        )
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT COUNT(*), listen_duration_sec, finalized, duration_confidence
        FROM play_history WHERE session_id = ?
        """,
        ("synthetic-session-id",),
    ).fetchone()
    conn.close()
    assert row == (1, 120, 1, "reported")


def test_stale_checkpoint_cannot_regress_final_session(db_path):
    asyncio.run(init_db(db_path))
    final = {
        "session_id": "synthetic-monotonic-session",
        "last_seen_at": "2024-03-24T12:02:00.900000+00:00",
        "username": "synthetic-user",
        "client_name": "Synthetic Player",
        "track_id": "track-1",
        "title": "Synthetic Song",
        "artist": "Synthetic Artist",
        "album": "Synthetic Album",
        "is_transcoding": 0,
        "duration_sec": 120,
        "duration_confidence": "reported",
        "finalized": True,
        "finalized_at": "2024-03-24T12:02:00.900000+00:00",
        "checkpointed_at": "2024-03-24T12:02:00.900000+00:00",
    }
    stale_checkpoint = {
        **final,
        "last_seen_at": "2024-03-24T12:02:00.100000+00:00",
        "duration_sec": 30,
        "duration_confidence": "estimated",
        "finalized": False,
        "finalized_at": "2024-03-24T12:02:00.100000+00:00",
        "checkpointed_at": "2024-03-24T12:02:00.100000+00:00",
    }

    asyncio.run(save_play_session(final, db_path=db_path))
    asyncio.run(save_play_session(stale_checkpoint, db_path=db_path))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT played_at, listen_duration_sec, finalized, finalized_at,
               checkpointed_at, duration_confidence
        FROM play_history WHERE session_id = ?
        """,
        ("synthetic-monotonic-session",),
    ).fetchone()
    conn.close()
    assert row == (
        "2024-03-24T12:02:00.900000+00:00",
        120,
        1,
        "2024-03-24T12:02:00.900000+00:00",
        "2024-03-24T12:02:00.900000+00:00",
        "reported",
    )
