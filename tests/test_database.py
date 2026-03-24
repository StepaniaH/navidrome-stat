import asyncio
import os
import sqlite3
import pytest
from src.database import init_db, save_play_session

DB_FILE = "test.db"

def teardown_module(module):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

def test_save_play_session():
    # Setup
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    # Init DB
    asyncio.run(init_db(DB_FILE))
    
    # Session to save
    session = {
        "last_seen_at": "2024-03-24T12:00:00Z",
        "username": "testuser",
        "client_name": "Web Player",
        "track_id": "t1",
        "title": "Song 1",
        "artist": "Artist A",
        "album": "Album X",
        "is_transcoding": 0,
        "duration_sec": 120
    }
    
    # Save session
    asyncio.run(save_play_session(session, db_path=DB_FILE))
    
    # Verify
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM play_history")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) == 1
    # Check fields
    # id, played_at, username, client_name, track_id, title, artist, album, is_transcoding, listen_duration_sec
    assert rows[0][2] == "testuser"
    assert rows[0][3] == "Web Player"
    assert rows[0][5] == "Song 1"
    assert rows[0][9] == 120
