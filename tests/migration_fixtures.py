"""Reusable fixtures for schema-migration and backup/restore regression tests.

``build_legacy_db`` recreates a database as an older release left it (historical
table shape plus a pinned ``schema_version``), so every new migration can be
exercised against real pre-upgrade layouts instead of mocked ones.
"""

import sqlite3

import aiosqlite

from src.database import init_db


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _create_v0_base_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE play_history (
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


_LEGACY_ROW = (
    "2024-03-24T01:00:00+00:00",
    "legacy_user",
    "Web Player",
    "t1",
    "Song 1",
    "Artist A",
    "Album X",
    0,
    45,
)
# The v0 base table has ten columns; the fixture row supplies NULL id.
_LEGACY_ROW_WITH_ID = (None, *_LEGACY_ROW)


async def _bump_and_migrate(path: str, from_version: int):
    conn = _connect(path)
    _create_v0_base_table(conn)
    conn.execute(
        "INSERT INTO play_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _LEGACY_ROW_WITH_ID,
    )
    if from_version >= 4:
        # Versions >= 4 carry the provenance column on existing tables.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(play_history)")}
        if "source" not in columns:
            conn.execute(
                "ALTER TABLE play_history ADD COLUMN source TEXT NOT NULL DEFAULT 'poller'"
            )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO schema_meta VALUES ('schema_version', ?)", (str(from_version),))
    conn.commit()
    conn.close()
    await init_db(path)


async def build_legacy_db(path: str, *, from_version: int):
    """Create a database pinned at ``from_version`` and migrate it to current."""
    await _bump_and_migrate(path, from_version)
    async with aiosqlite.connect(path) as db:
        version_row = await db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        row = await version_row.fetchone()
        return int(row[0])
