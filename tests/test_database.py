import asyncio
import sqlite3

from src.database import init_db, save_play_session, get_playback_history, get_summary, ping_db


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
    assert cursor.fetchone()[0] == "2"
    cursor.execute("SELECT value FROM schema_meta WHERE key = 'retention_days'")
    assert cursor.fetchone()[0] == "permanent"
    cursor.execute("PRAGMA index_list(play_history)")
    index_names = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "idx_play_history_user_track" in index_names
    assert "idx_play_history_played_at" in index_names


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
