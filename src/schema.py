"""SQLite schema, migrations, and the shared metadata key/value store."""

from pathlib import Path

import aiosqlite

from src import config
from src.sqlite import connect_db

SCHEMA_VERSION = 13
LEGACY_SOURCE_ID = "legacy"
LEGACY_SOURCE_NAME = "Legacy environment source"


class UnsupportedSchemaVersionError(RuntimeError):
    """Raised when this application is older than the database schema."""

# Text columns shared by play_history and play_attempts; storage-size estimates
# sum these lengths plus a fixed 16-byte per-row overhead.
TEXT_COLUMNS = (
    "played_at",
    "username",
    "client_name",
    "track_id",
    "title",
    "artist",
    "album",
    "artist_id",
    "album_id",
    "record_id",
)
PAYLOAD_BYTES_SQL = (
    " + ".join(f"COALESCE(LENGTH({column}), 0)" for column in TEXT_COLUMNS) + " + 16"
)


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


async def get_meta_value(db: aiosqlite.Connection, key: str) -> str | None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    async with db.execute("SELECT value FROM schema_meta WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def set_meta_value(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    value = await get_meta_value(db, "schema_version")
    return int(value) if value is not None else 0


async def _peek_schema_version(db: aiosqlite.Connection) -> int:
    """Read an existing version without creating or altering schema objects."""
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    ) as cursor:
        if await cursor.fetchone() is None:
            return 0
    async with db.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _ensure_supported_schema_version(version: int) -> None:
    if version > SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Database schema version {version} is newer than this application supports "
            f"({SCHEMA_VERSION}). Start a compatible newer Navidrome Stat version or restore "
            "a backup created before the downgrade."
        )


async def _set_schema_version(db: aiosqlite.Connection, version: int) -> None:
    await set_meta_value(db, "schema_version", str(version))


async def _apply_migrations(db: aiosqlite.Connection, db_path: str) -> None:
    version = await _get_schema_version(db)
    _ensure_supported_schema_version(version)

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

    if version < 2:
        existing = await get_meta_value(db, "retention_days")
        if existing is None:
            await set_meta_value(db, "retention_days", "permanent")
        await _set_schema_version(db, 2)

    if version < 3:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT,
                username TEXT,
                client_name TEXT,
                track_id TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                is_transcoding INTEGER,
                duration_sec INTEGER NOT NULL,
                outcome TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_played_at
            ON play_attempts(played_at DESC)
        """)
        await _set_schema_version(db, 3)

    if version < 4:
        await db.execute(
            "ALTER TABLE play_history ADD COLUMN source TEXT NOT NULL DEFAULT 'poller'"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_play_history_source ON play_history(source)"
        )
        await _set_schema_version(db, 4)

    if version < 5:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "source_id" not in columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN source_id TEXT")
        if "source_name" not in columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN source_name TEXT")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT, username TEXT, client_name TEXT, track_id TEXT,
                title TEXT, artist TEXT, album TEXT, is_transcoding INTEGER,
                duration_sec INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL DEFAULT 'short_play'
            )
        """)
        async with db.execute("PRAGMA table_info(play_attempts)") as cursor:
            attempt_columns = {row[1] for row in await cursor.fetchall()}
        if "source_id" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN source_id TEXT")
        if "source_name" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN source_name TEXT")
        await db.execute(
            "UPDATE play_history SET source_id = ?, source_name = ? "
            "WHERE source_id IS NULL OR source_id = ''",
            (LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME),
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_play_history_source_id ON play_history(source_id)"
        )
        await _set_schema_version(db, 5)

    if version < 6:
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            history_columns = {row[1] for row in await cursor.fetchall()}
        if "session_id" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN session_id TEXT")
        if "duration_confidence" not in history_columns:
            await db.execute(
                "ALTER TABLE play_history ADD COLUMN "
                "duration_confidence TEXT NOT NULL DEFAULT 'estimated'"
            )
        if "finalized" not in history_columns:
            await db.execute(
                "ALTER TABLE play_history ADD COLUMN finalized INTEGER NOT NULL DEFAULT 1"
            )
        if "finalized_at" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN finalized_at TEXT")

        async with db.execute("PRAGMA table_info(play_attempts)") as cursor:
            attempt_columns = {row[1] for row in await cursor.fetchall()}
        if "attempt_id" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN attempt_id TEXT")
        if "duration_confidence" not in attempt_columns:
            await db.execute(
                "ALTER TABLE play_attempts ADD COLUMN "
                "duration_confidence TEXT NOT NULL DEFAULT 'estimated'"
            )

        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_history_session_id
            ON play_history(session_id)
            WHERE session_id IS NOT NULL
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_attempts_attempt_id
            ON play_attempts(attempt_id)
            WHERE attempt_id IS NOT NULL
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_source_user_track
            ON play_history(source_id, username, track_id)
        """)
        await _set_schema_version(db, 6)

    if version < 7:
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            history_columns = {row[1] for row in await cursor.fetchall()}
        if "checkpointed_at" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN checkpointed_at TEXT")
        await _set_schema_version(db, 7)

    if version < 8:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS album_art_map (
                source_id TEXT NOT NULL,
                album_key TEXT NOT NULL,
                album_id TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                PRIMARY KEY (source_id, album_key)
            )
        """)
        await _set_schema_version(db, 8)

    if version < 9:
        for table in ("play_history", "play_attempts"):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if "artist_id" not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN artist_id TEXT")
        await _set_schema_version(db, 9)

    if version < 10:
        await _encrypt_saved_credentials(db, db_path)
        await _set_schema_version(db, 10)

    if version < 11:
        for table in ("play_history",):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if "external_event_key" not in columns:
                await db.execute("ALTER TABLE play_history ADD COLUMN external_event_key TEXT")
        async with db.execute("PRAGMA table_info(servers)") as cursor:
            server_columns = {row[1] for row in await cursor.fetchall()}
        if "backfill_playlist_id" not in server_columns:
            await db.execute("ALTER TABLE servers ADD COLUMN backfill_playlist_id TEXT")
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_history_external_event_key
            ON play_history(external_event_key)
            WHERE external_event_key IS NOT NULL
        """)
        await _set_schema_version(db, 11)

    if version < 12:
        for table in ("play_history", "play_attempts"):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if "album_id" not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN album_id TEXT")
            if "record_id" not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN record_id TEXT")
            await db.execute(
                f"UPDATE {table} SET record_id = lower(hex(randomblob(16))) "
                "WHERE record_id IS NULL OR record_id = ''"
            )
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_history_record_id
            ON play_history(record_id)
            WHERE record_id IS NOT NULL
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_attempts_record_id
            ON play_attempts(record_id)
            WHERE record_id IS NOT NULL
        """)
        await _set_schema_version(db, 12)

    if version < 13:
        for table in ("play_history", "play_attempts"):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if "played_at_epoch" not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN played_at_epoch INTEGER")
            await db.execute(f"UPDATE {table} SET played_at_epoch = unixepoch(played_at)")
            await db.execute(f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_played_at_epoch_insert
                AFTER INSERT ON {table}
                FOR EACH ROW
                WHEN NEW.played_at_epoch IS NOT unixepoch(NEW.played_at)
                BEGIN
                    UPDATE {table}
                    SET played_at_epoch = unixepoch(NEW.played_at)
                    WHERE id = NEW.id;
                END
            """)
            await db.execute(f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_played_at_epoch_update
                AFTER UPDATE OF played_at ON {table}
                FOR EACH ROW
                WHEN NEW.played_at_epoch IS NOT unixepoch(NEW.played_at)
                BEGIN
                    UPDATE {table}
                    SET played_at_epoch = unixepoch(NEW.played_at)
                    WHERE id = NEW.id;
                END
            """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_played_at_epoch
            ON play_history(played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_source_epoch
            ON play_history(source_id, played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_source_user_epoch
            ON play_history(source_id, username, played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_user_epoch
            ON play_history(username, played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_played_at_epoch
            ON play_attempts(played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_source_epoch
            ON play_attempts(source_id, played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_source_user_epoch
            ON play_attempts(source_id, username, played_at_epoch DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_user_epoch
            ON play_attempts(username, played_at_epoch DESC)
        """)
        await _set_schema_version(db, 13)


async def _encrypt_saved_credentials(db: aiosqlite.Connection, db_path: str) -> None:
    """Re-wrap legacy plaintext credentials as enc:v1 AES-GCM payloads."""
    from src.secretbox import encrypt, is_encrypted, load_or_create_key

    key = load_or_create_key(db_path)

    async with db.execute(
        "SELECT id, password FROM servers WHERE password IS NOT NULL AND password != ''"
    ) as cursor:
        rows = await cursor.fetchall()
    for server_id, password in rows:
        if is_encrypted(password):
            continue
        await db.execute(
            "UPDATE servers SET password = ? WHERE id = ?",
            (encrypt(password, key), server_id),
        )

    fallback = await get_meta_value(db, "source_password")
    if fallback and not is_encrypted(fallback):
        await set_meta_value(db, "source_password", encrypt(fallback, key))


async def init_db(db_path: str | None = None):
    """Initialize the schema and recover durable playback checkpoints."""
    path = _path(db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if Path(path).exists():
        async with connect_db(path) as existing_db:
            _ensure_supported_schema_version(await _peek_schema_version(existing_db))
    async with connect_db(path, initialize=True) as db:
        _ensure_supported_schema_version(await _peek_schema_version(db))
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
        await _apply_migrations(db, path)
        await _recover_incomplete_sessions(db)
        await db.commit()


async def _recover_incomplete_sessions(db: aiosqlite.Connection) -> int:
    """Finalize durable checkpoints left by an earlier interrupted process."""

    cursor = await db.execute(
        """
        UPDATE play_history
        SET finalized = 1,
            finalized_at = COALESCE(checkpointed_at, played_at)
        WHERE session_id IS NOT NULL AND finalized = 0
        """
    )
    return max(cursor.rowcount, 0)


async def recover_incomplete_sessions(db_path: str | None = None) -> int:
    """Finalize durable checkpoints left by an interrupted process."""

    path = _path(db_path)
    async with connect_db(path) as db:
        recovered = await _recover_incomplete_sessions(db)
        await db.commit()
    return recovered


async def ping_db(db_path: str | None = None) -> bool:
    """Return whether the SQLite database is reachable."""
    path = _path(db_path)
    try:
        async with connect_db(path) as db:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        return True
    except Exception:
        return False
