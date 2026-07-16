import aiosqlite
import os

DB_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")

async def init_db(db_path: str = DB_PATH):
    """Initializes the database and creates the play_history table."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT,
                username TEXT,
                client_name TEXT,
                track_id TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                is_transcoding INTEGER,
                listen_duration_sec INTEGER
            )
        """)
        await db.commit()

async def save_play_session(session: dict, db_path: str = DB_PATH):
    """Saves a completed playback session to the database."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO play_history (
                played_at, username, client_name, track_id,
                title, artist, album, is_transcoding, listen_duration_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("last_seen_at"),
            session.get("username"),
            session.get("client_name"),
            session.get("track_id"),
            session.get("title"),
            session.get("artist"),
            session.get("album"),
            session.get("is_transcoding"),
            session.get("duration_sec")
        ))
        await db.commit()

async def get_player_stats(db_path: str = DB_PATH):
    """Returns the distribution of client usage based on play counts."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT client_name, COUNT(*) as count
            FROM play_history
            GROUP BY client_name
            ORDER BY count DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_transcoding_stats(db_path: str = DB_PATH):
    """Returns the ratio of transcoded vs direct play counts."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT is_transcoding, COUNT(*) as count
            FROM play_history
            GROUP BY is_transcoding
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_playback_history(limit: int = 10, db_path: str = DB_PATH):
    """Returns top tracks and play counts."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT username, title, artist, album, COUNT(*) as play_count
            FROM play_history
            GROUP BY username, track_id
            ORDER BY MAX(played_at) DESC, play_count DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
