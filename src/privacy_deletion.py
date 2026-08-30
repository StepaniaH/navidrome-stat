"""Per-user inventory, preview, deletion, and importer-cursor sealing."""

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.importers.cursor_store import (
    seal_song_history_cursor,
    song_history_cursor_key,
    song_history_cursor_prefix,
)
from src.privacy_common import database_path as _path
from src.privacy_markers import set_user_deletion_cutoff
from src.schema import LEGACY_SOURCE_ID, get_meta_value, set_meta_value
from src.sqlite import connect_db


async def list_users(db_path: str | None = None) -> list[dict[str, Any]]:
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT username, COUNT(*) AS record_count
            FROM (
                SELECT username FROM play_history
                UNION ALL
                SELECT username FROM play_attempts
            )
            WHERE username IS NOT NULL AND username != ''
            GROUP BY username
            ORDER BY username COLLATE NOCASE
        """) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]




async def preview_delete_user(username: str, db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM play_history WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        async with db.execute(
            "SELECT COUNT(*) FROM play_attempts WHERE username = ?",
            (username,),
        ) as cursor:
            attempt_row = await cursor.fetchone()
    return {"records_to_delete": int(row[0]) + int(attempt_row[0])}


async def delete_user_data(username: str, db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    async with connect_db(path) as db:
        await set_user_deletion_cutoff(
            db,
            username,
            datetime.now(timezone.utc).isoformat(),
        )
        prefix = song_history_cursor_prefix(username)
        async with db.execute(
            "SELECT key, value FROM schema_meta WHERE key LIKE ?",
            (f"{prefix}%",),
        ) as cursor:
            existing_cursors = await cursor.fetchall()
        sealed_keys = set()
        for key, raw in existing_cursors:
            await set_meta_value(db, key, seal_song_history_cursor(raw))
            sealed_keys.add(key)

        async with db.execute(
            """
            SELECT DISTINCT COALESCE(source_id, ?) AS source_id
            FROM play_history
            WHERE username = ?
            UNION
            SELECT DISTINCT COALESCE(source_id, ?)
            FROM play_attempts
            WHERE username = ?
            UNION
            SELECT id FROM servers WHERE username = ?
            """,
            (LEGACY_SOURCE_ID, username, LEGACY_SOURCE_ID, username, username),
        ) as cursor:
            source_ids = [row[0] for row in await cursor.fetchall() if row[0]]
        for source_id in source_ids:
            key = song_history_cursor_key(str(source_id), username)
            if key in sealed_keys:
                continue
            raw = await get_meta_value(db, key)
            await set_meta_value(db, key, seal_song_history_cursor(raw))

        cursor = await db.execute(
            "DELETE FROM play_history WHERE username = ?",
            (username,),
        )
        attempt_cursor = await db.execute(
            "DELETE FROM play_attempts WHERE username = ?",
            (username,),
        )
        await db.commit()
        deleted = cursor.rowcount + attempt_cursor.rowcount
    return {"deleted": deleted}
