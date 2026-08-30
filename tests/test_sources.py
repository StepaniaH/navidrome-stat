import asyncio
import sqlite3

from src.database import (
    get_playback_history,
    get_source_stats,
    get_summary,
    init_db,
    save_play_session,
)


def test_source_defaults_to_poller_and_can_be_aggregated(db_path):
    asyncio.run(init_db(db_path))
    session = {
        "last_seen_at": "2024-03-24T12:00:00Z",
        "username": "u",
        "client_name": "client",
        "track_id": "t",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "is_transcoding": 0,
        "duration_sec": 30,
    }
    asyncio.run(save_play_session(session, db_path=db_path))
    session["track_id"] = "imported"
    session["source"] = "import"
    asyncio.run(save_play_session(session, db_path=db_path))
    assert asyncio.run(get_source_stats(db_path=db_path)) == [
        {"source": "import", "count": 1, "total_listen_sec": 30},
        {"source": "poller", "count": 1, "total_listen_sec": 30},
    ]


def test_schema_v4_adds_source_column_to_existing_database(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO schema_meta VALUES ('schema_version', '3')")
    conn.execute("""CREATE TABLE play_history (
        id INTEGER PRIMARY KEY, played_at TEXT, username TEXT, client_name TEXT,
        track_id TEXT, title TEXT, artist TEXT, album TEXT,
        is_transcoding INTEGER, listen_duration_sec INTEGER
    )""")
    conn.commit()
    conn.close()
    asyncio.run(init_db(db_path))
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(play_history)")}
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    conn.close()
    assert "source" in columns
    assert version == "13"


def test_same_track_id_on_two_servers_remains_distinct(db_path):
    asyncio.run(init_db(db_path))
    base = {
        "last_seen_at": "2024-03-24T12:00:00+00:00",
        "username": "synthetic-user",
        "client_name": "Synthetic Player",
        "track_id": "shared-track-id",
        "artist": "Synthetic Artist",
        "album": "Synthetic Album",
        "is_transcoding": 0,
        "duration_sec": 40,
    }
    asyncio.run(
        save_play_session(
            {
                **base,
                "title": "Server A Song",
                "source_id": "server-a",
                "source_name": "Server A",
            },
            db_path=db_path,
        )
    )
    asyncio.run(
        save_play_session(
            {
                **base,
                "title": "Server B Song",
                "source_id": "server-b",
                "source_name": "Server B",
            },
            db_path=db_path,
        )
    )

    history = asyncio.run(get_playback_history(db_path=db_path))
    assert len(history) == 2
    assert {item["source_id"] for item in history} == {"server-a", "server-b"}
    assert asyncio.run(get_summary(db_path=db_path))["unique_tracks"] == 2
    filtered = asyncio.run(get_playback_history(db_path=db_path, source_id="server-a"))
    assert [item["title"] for item in filtered] == ["Server A Song"]
