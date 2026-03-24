import aiosqlite
import os

DB_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")

async def init_db(db_path: str = DB_PATH):
    """Initializes the database and creates the playback_snapshots table."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS playback_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                username TEXT,
                player_id TEXT,
                client_name TEXT,
                track_id TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                is_transcoding INTEGER,
                original_bitrate INTEGER,
                current_bitrate INTEGER,
                position_ms INTEGER,
                player_state TEXT
            )
        """)
        await db.commit()

async def save_snapshot(snapshot: dict, db_path: str = DB_PATH):
    """Saves a single playback snapshot to the database."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO playback_snapshots (
                timestamp, username, player_id, client_name, track_id,
                title, artist, album, is_transcoding, original_bitrate,
                current_bitrate, position_ms, player_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot.get("timestamp"),
            snapshot.get("username"),
            snapshot.get("player_id"),
            snapshot.get("client_name"),
            snapshot.get("track_id"),
            snapshot.get("title"),
            snapshot.get("artist"),
            snapshot.get("album"),
            snapshot.get("is_transcoding"),
            snapshot.get("original_bitrate"),
            snapshot.get("current_bitrate"),
            snapshot.get("position_ms"),
            snapshot.get("player_state")
        ))
        await db.commit()

async def get_player_stats(db_path: str = DB_PATH):
    """Returns the distribution of client usage."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT client_name, COUNT(*) as count
            FROM playback_snapshots
            GROUP BY client_name
            ORDER BY count DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_transcoding_stats(db_path: str = DB_PATH):
    """Returns the ratio of transcoded vs direct play."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT is_transcoding, COUNT(*) as count
            FROM playback_snapshots
            GROUP BY is_transcoding
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_playback_history(limit: int = 10, db_path: str = DB_PATH):
    """Returns top tracks and listening statistics."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT username, title, artist, album, COUNT(*) as snapshot_count
            FROM playback_snapshots
            GROUP BY username, track_id
            ORDER BY snapshot_count DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
