import asyncio
import os
import sqlite3
import pytest
from src.database import init_db, save_snapshot

DB_FILE = "test.db"

def teardown_module(module):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

def test_save_snapshot():
    # Setup
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    # Init DB
    asyncio.run(init_db(DB_FILE))
    
    # Snapshot to save
    snapshot = {
        "timestamp": "2024-03-24T12:00:00Z",
        "username": "testuser",
        "player_id": "p1",
        "client_name": "Web Player",
        "track_id": "t1",
        "title": "Song 1",
        "artist": "Artist A",
        "album": "Album X",
        "is_transcoding": 0,
        "original_bitrate": 320,
        "current_bitrate": 320,
        "position_ms": 1000,
        "player_state": "playing"
    }
    
    # Save snapshot
    asyncio.run(save_snapshot(snapshot, db_path=DB_FILE))
    
    # Verify
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM playback_snapshots")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) == 1
    # Check a few fields
    # id, timestamp, username, player_id, client_name, track_id, title, artist, album, is_transcoding, original_bitrate, current_bitrate, position_ms, player_state
    assert rows[0][2] == "testuser"
    assert rows[0][4] == "Web Player"
    assert rows[0][6] == "Song 1"
