import aiosqlite
import os

DB_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")
SCHEMA_VERSION = 1


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    async with db.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


async def _set_schema_version(db: aiosqlite.Connection, version: int) -> None:
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


async def _apply_migrations(db: aiosqlite.Connection) -> None:
    version = await _get_schema_version(db)

    if version < 1:
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_user_track
            ON play_history(username, track_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_played_at
            ON play_history(played_at DESC)
        """)
        await _set_schema_version(db, 1)


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
        await _apply_migrations(db)
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


async def ping_db(db_path: str = DB_PATH) -> bool:
    """Returns True when the SQLite database is reachable."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        return True
    except Exception:
        return False


async def get_summary(db_path: str = DB_PATH):
    """Returns aggregate listening statistics."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                COUNT(*) AS total_plays,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec,
                COUNT(DISTINCT track_id) AS unique_tracks,
                COUNT(DISTINCT client_name) AS client_count
            FROM play_history
        """) as cursor:
            row = await cursor.fetchone()
            return dict(row)


async def get_playback_history(limit: int = 10, db_path: str = DB_PATH):
    """Returns recent tracks with aggregated play counts."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                ph.username,
                ph.title,
                ph.artist,
                ph.album,
                ph.played_at AS last_played_at,
                agg.play_count,
                agg.total_listen_sec
            FROM (
                SELECT
                    username,
                    track_id,
                    COUNT(*) AS play_count,
                    SUM(listen_duration_sec) AS total_listen_sec,
                    MAX(id) AS latest_id
                FROM play_history
                GROUP BY username, track_id
            ) agg
            JOIN play_history ph ON ph.id = agg.latest_id
            ORDER BY ph.played_at DESC, agg.play_count DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
