"""Privacy-oriented data retention, export, and import operations."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from src.database import DB_PATH, init_db


def _path(db_path: str | None = None) -> str:
    return DB_PATH if db_path is None else db_path


_ROW_PAYLOAD_BYTES_SQL = """
    COALESCE(LENGTH(played_at), 0) +
    COALESCE(LENGTH(username), 0) +
    COALESCE(LENGTH(client_name), 0) +
    COALESCE(LENGTH(track_id), 0) +
    COALESCE(LENGTH(title), 0) +
    COALESCE(LENGTH(artist), 0) +
    COALESCE(LENGTH(album), 0) +
    16
"""

EXPORT_FORMAT_VERSION = 1
RETENTION_PERMANENT = None
RETENTION_MIN_DAYS = 1
RETENTION_MAX_DAYS = 360
META_RETENTION_DAYS = "retention_days"
META_RETENTION_PERMANENT = "permanent"


def validate_retention_days(days: Optional[int]) -> Optional[int]:
    if days is None:
        return None
    if not isinstance(days, int) or days < RETENTION_MIN_DAYS or days > RETENTION_MAX_DAYS:
        raise ValueError(
            f"retention_days must be null (permanent) or between "
            f"{RETENTION_MIN_DAYS} and {RETENTION_MAX_DAYS}"
        )
    return days


async def _ensure_meta_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)


async def _get_meta(db: aiosqlite.Connection, key: str) -> Optional[str]:
    await _ensure_meta_table(db)
    async with db.execute("SELECT value FROM schema_meta WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def _set_meta(db: aiosqlite.Connection, key: str, value: str) -> None:
    await _ensure_meta_table(db)
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


async def get_retention_days(db_path: str | None = None) -> Optional[int]:
    """Returns retention days, or None for permanent retention."""
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        raw = await _get_meta(db, META_RETENTION_DAYS)
    if raw is None or raw == META_RETENTION_PERMANENT:
        return None
    return int(raw)


async def set_retention_days(days: Optional[int], db_path: str | None = None) -> None:
    days = validate_retention_days(days)
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        if days is None:
            await _set_meta(db, META_RETENTION_DAYS, META_RETENTION_PERMANENT)
        else:
            await _set_meta(db, META_RETENTION_DAYS, str(days))
        await db.commit()


def _retention_cutoff_iso(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.isoformat()


def _estimate_database_bytes_after_purge(
    database_bytes: int,
    estimated_data_bytes: int,
    bytes_to_delete: int,
) -> int:
    if estimated_data_bytes <= 0 or bytes_to_delete <= 0:
        return database_bytes
    freed = int(database_bytes * (bytes_to_delete / estimated_data_bytes))
    return max(database_bytes - freed, 0)


async def _play_history_storage_metrics(
    db: aiosqlite.Connection,
    *,
    played_before: str | None = None,
) -> tuple[int, int]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if played_before is not None:
        where_clause = " WHERE played_at < ?"
        params = (played_before,)

    async with db.execute(
        f"SELECT COUNT(*), COALESCE(SUM({_ROW_PAYLOAD_BYTES_SQL}), 0) "
        f"FROM play_history{where_clause}",
        params,
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]), int(row[1])


async def get_storage_stats(db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    database_bytes = os.path.getsize(path) if os.path.exists(path) else 0
    async with aiosqlite.connect(path) as db:
        total_records, estimated_data_bytes = await _play_history_storage_metrics(db)
    return {
        "database_bytes": database_bytes,
        "total_records": total_records,
        "estimated_data_bytes": estimated_data_bytes,
    }


async def preview_retention_purge(
    days: Optional[int] = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    path = _path(db_path)
    storage = await get_storage_stats(path)
    if days is None:
        days = await get_retention_days(path)
    if days is None:
        return {
            "records_to_delete": 0,
            "retention_days": None,
            "bytes_to_delete": 0,
            "estimated_database_bytes_after": storage["database_bytes"],
            **storage,
        }

    cutoff = _retention_cutoff_iso(days)
    async with aiosqlite.connect(path) as db:
        records_to_delete, bytes_to_delete = await _play_history_storage_metrics(
            db,
            played_before=cutoff,
        )
    estimated_after = _estimate_database_bytes_after_purge(
        storage["database_bytes"],
        storage["estimated_data_bytes"],
        bytes_to_delete,
    )
    return {
        "records_to_delete": records_to_delete,
        "retention_days": days,
        "bytes_to_delete": bytes_to_delete,
        "estimated_database_bytes_after": estimated_after,
        **storage,
    }


async def apply_retention_purge(db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    days = await get_retention_days(path)
    preview = await preview_retention_purge(days, path)
    if preview["records_to_delete"] == 0:
        return {"deleted": 0, "retention_days": days}

    cutoff = _retention_cutoff_iso(days)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "DELETE FROM play_history WHERE played_at < ?",
            (cutoff,),
        )
        await db.commit()
        deleted = cursor.rowcount
    return {"deleted": deleted, "retention_days": days}


async def list_users(db_path: str | None = None) -> list[dict[str, Any]]:
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT username, COUNT(*) AS record_count
            FROM play_history
            WHERE username IS NOT NULL AND username != ''
            GROUP BY username
            ORDER BY username COLLATE NOCASE
        """) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _row_to_export_record(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "played_at": row["played_at"],
        "client_name": row["client_name"],
        "track_id": row["track_id"],
        "title": row["title"],
        "artist": row["artist"],
        "album": row["album"],
        "is_transcoding": row["is_transcoding"],
        "listen_duration_sec": row["listen_duration_sec"],
    }


async def export_user_data(username: str, db_path: str | None = None) -> dict[str, Any]:
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT played_at, client_name, track_id, title, artist, album,
                   is_transcoding, listen_duration_sec
            FROM play_history
            WHERE username = ?
            ORDER BY played_at ASC, id ASC
            """,
            (username,),
        ) as cursor:
            rows = await cursor.fetchall()

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "username": username,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "records": [_row_to_export_record(row) for row in rows],
    }


def _validate_import_record(record: dict[str, Any]) -> dict[str, Any]:
    required = ("played_at", "track_id")
    for field in required:
        if not record.get(field):
            raise ValueError(f"Import record missing required field: {field}")
    return {
        "played_at": record["played_at"],
        "client_name": record.get("client_name"),
        "track_id": record["track_id"],
        "title": record.get("title"),
        "artist": record.get("artist"),
        "album": record.get("album"),
        "is_transcoding": record.get("is_transcoding"),
        "listen_duration_sec": record.get("listen_duration_sec"),
    }


async def import_user_data(
    username: str,
    payload: dict[str, Any],
    *,
    merge: bool = True,
    db_path: str | None = None,
) -> dict[str, int]:
    if payload.get("format_version") != EXPORT_FORMAT_VERSION:
        raise ValueError("Unsupported export format_version")
    if payload.get("username") != username:
        raise ValueError("Export username does not match target username")

    records = payload.get("records") or []
    if not isinstance(records, list):
        raise ValueError("records must be a list")

    validated = [_validate_import_record(item) for item in records]

    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("BEGIN")
        try:
            if not merge:
                await db.execute("DELETE FROM play_history WHERE username = ?", (username,))

            inserted = 0
            for record in validated:
                await db.execute(
                    """
                    INSERT INTO play_history (
                        played_at, username, client_name, track_id,
                        title, artist, album, is_transcoding, listen_duration_sec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["played_at"],
                        username,
                        record["client_name"],
                        record["track_id"],
                        record["title"],
                        record["artist"],
                        record["album"],
                        record["is_transcoding"],
                        record["listen_duration_sec"],
                    ),
                )
                inserted += 1
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return {"imported": inserted, "merge": int(merge)}


async def preview_delete_user(username: str, db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM play_history WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
    return {"records_to_delete": int(row[0])}


async def delete_user_data(username: str, db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    preview = await preview_delete_user(username, path)
    if preview["records_to_delete"] == 0:
        return {"deleted": 0}

    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "DELETE FROM play_history WHERE username = ?",
            (username,),
        )
        await db.commit()
        deleted = cursor.rowcount
    return {"deleted": deleted}
