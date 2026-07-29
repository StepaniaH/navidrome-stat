"""Privacy-oriented data retention, export, and import operations."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from src.database import DB_PATH
from src.sqlite import connect_db


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

EXPORT_FORMAT_VERSION = 2
SUPPORTED_IMPORT_FORMAT_VERSIONS = (1, 2)
IMPORT_MAX_RECORDS = 10_000
IMPORT_MAX_PAYLOAD_BYTES = 5 * 1024 * 1024
IMPORT_MAX_TEXT_LENGTH = 2_048
IMPORT_MAX_DURATION_SEC = 7 * 24 * 60 * 60
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
    async with connect_db(path) as db:
        raw = await _get_meta(db, META_RETENTION_DAYS)
    if raw is None or raw == META_RETENTION_PERMANENT:
        return None
    return int(raw)


async def set_retention_days(days: Optional[int], db_path: str | None = None) -> None:
    days = validate_retention_days(days)
    path = _path(db_path)
    async with connect_db(path) as db:
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


async def _play_attempt_storage_metrics(
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
        f"""
        SELECT COUNT(*), COALESCE(SUM(
            COALESCE(LENGTH(played_at), 0) +
            COALESCE(LENGTH(username), 0) +
            COALESCE(LENGTH(client_name), 0) +
            COALESCE(LENGTH(track_id), 0) +
            COALESCE(LENGTH(title), 0) +
            COALESCE(LENGTH(artist), 0) +
            COALESCE(LENGTH(album), 0) + 16
        ), 0)
        FROM play_attempts{where_clause}
        """,
        params,
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]), int(row[1])


async def get_storage_stats(db_path: str | None = None) -> dict[str, int]:
    path = _path(db_path)
    database_bytes = os.path.getsize(path) if os.path.exists(path) else 0
    async with connect_db(path) as db:
        history_records, history_bytes = await _play_history_storage_metrics(db)
        attempt_records, attempt_bytes = await _play_attempt_storage_metrics(db)
    return {
        "database_bytes": database_bytes,
        "total_records": history_records + attempt_records,
        "history_records": history_records,
        "attempt_records": attempt_records,
        "estimated_data_bytes": history_bytes + attempt_bytes,
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
            "history_records_to_delete": 0,
            "attempt_records_to_delete": 0,
            "retention_days": None,
            "bytes_to_delete": 0,
            "estimated_database_bytes_after": storage["database_bytes"],
            **storage,
        }

    cutoff = _retention_cutoff_iso(days)
    async with connect_db(path) as db:
        history_to_delete, history_bytes = await _play_history_storage_metrics(
            db,
            played_before=cutoff,
        )
        attempts_to_delete, attempt_bytes = await _play_attempt_storage_metrics(
            db,
            played_before=cutoff,
        )
    records_to_delete = history_to_delete + attempts_to_delete
    bytes_to_delete = history_bytes + attempt_bytes
    estimated_after = _estimate_database_bytes_after_purge(
        storage["database_bytes"],
        storage["estimated_data_bytes"],
        bytes_to_delete,
    )
    return {
        "records_to_delete": records_to_delete,
        "history_records_to_delete": history_to_delete,
        "attempt_records_to_delete": attempts_to_delete,
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
        return {
            "deleted": 0,
            "history_deleted": 0,
            "attempts_deleted": 0,
            "retention_days": days,
        }

    cutoff = _retention_cutoff_iso(days)
    async with connect_db(path) as db:
        history_cursor = await db.execute(
            "DELETE FROM play_history WHERE played_at < ?",
            (cutoff,),
        )
        attempt_cursor = await db.execute(
            "DELETE FROM play_attempts WHERE played_at < ?",
            (cutoff,),
        )
        await db.commit()
        history_deleted = history_cursor.rowcount
        attempts_deleted = attempt_cursor.rowcount
    return {
        "deleted": history_deleted + attempts_deleted,
        "history_deleted": history_deleted,
        "attempts_deleted": attempts_deleted,
        "retention_days": days,
    }


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
        "source": row["source"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "duration_confidence": row["duration_confidence"],
    }


async def export_user_data(username: str, db_path: str | None = None) -> dict[str, Any]:
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT played_at, client_name, track_id, title, artist, album,
                   is_transcoding, listen_duration_sec, source, source_id,
                   source_name, duration_confidence
            FROM play_history
            WHERE username = ?
            ORDER BY played_at ASC, id ASC
            """,
            (username,),
        ) as cursor:
            rows = await cursor.fetchall()
        async with db.execute(
            """
            SELECT played_at, client_name, track_id, title, artist, album,
                   is_transcoding, duration_sec, outcome, source_id,
                   source_name, duration_confidence
            FROM play_attempts
            WHERE username = ?
            ORDER BY played_at ASC, id ASC
            """,
            (username,),
        ) as cursor:
            attempt_rows = await cursor.fetchall()

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "username": username,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "records": [_row_to_export_record(row) for row in rows],
        "attempt_count": len(attempt_rows),
        "attempts": [
            {
                "played_at": row["played_at"],
                "client_name": row["client_name"],
                "track_id": row["track_id"],
                "title": row["title"],
                "artist": row["artist"],
                "album": row["album"],
                "is_transcoding": row["is_transcoding"],
                "duration_sec": row["duration_sec"],
                "outcome": row["outcome"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "duration_confidence": row["duration_confidence"],
            }
            for row in attempt_rows
        ],
    }


def _validate_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"Import record missing required field: {field}")
        return None
    if not isinstance(value, str):
        raise ValueError(f"Import field must be a string: {field}")
    if required and not value.strip():
        raise ValueError(f"Import record missing required field: {field}")
    if len(value) > IMPORT_MAX_TEXT_LENGTH:
        raise ValueError(f"Import field is too long: {field}")
    return value


def _validate_timestamp(value: Any) -> str:
    text = _validate_text(value, "played_at", required=True)
    assert text is not None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Import played_at must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("Import played_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_duration(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Import {field} must be an integer")
    if value < 0 or value > IMPORT_MAX_DURATION_SEC:
        raise ValueError(
            f"Import {field} must be between 0 and {IMPORT_MAX_DURATION_SEC}"
        )
    return value


def _validate_transcoding(value: Any) -> int:
    if value in (None, False, 0):
        return 0
    if value in (True, 1):
        return 1
    raise ValueError("Import is_transcoding must be 0 or 1")


def _validate_import_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Import records must be objects")
    required = ("played_at", "track_id")
    for field in required:
        if not record.get(field):
            raise ValueError(f"Import record missing required field: {field}")
    return {
        "played_at": _validate_timestamp(record["played_at"]),
        "client_name": _validate_text(record.get("client_name"), "client_name"),
        "track_id": _validate_text(record["track_id"], "track_id", required=True),
        "title": _validate_text(record.get("title"), "title"),
        "artist": _validate_text(record.get("artist"), "artist"),
        "album": _validate_text(record.get("album"), "album"),
        "is_transcoding": _validate_transcoding(record.get("is_transcoding")),
        "listen_duration_sec": _validate_duration(
            record.get("listen_duration_sec", 0),
            "listen_duration_sec",
        ),
        "source_id": _validate_text(record.get("source_id"), "source_id"),
        "source_name": _validate_text(record.get("source_name"), "source_name"),
        "duration_confidence": (
            "reported"
            if record.get("duration_confidence") == "reported"
            else "estimated"
        ),
    }


def _validate_import_attempt(record: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_import_record({
        **record,
        "listen_duration_sec": record.get("duration_sec", 0),
    })
    validated["duration_sec"] = validated.pop("listen_duration_sec")
    return validated


async def import_user_data(
    username: str,
    payload: dict[str, Any],
    *,
    merge: bool = True,
    db_path: str | None = None,
) -> dict[str, int]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > IMPORT_MAX_PAYLOAD_BYTES:
        raise ValueError("Import payload is too large")
    if payload.get("format_version") not in SUPPORTED_IMPORT_FORMAT_VERSIONS:
        raise ValueError("Unsupported export format_version")
    if payload.get("username") != username:
        raise ValueError("Export username does not match target username")

    records = payload.get("records") or []
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    attempts = payload.get("attempts") or []
    if not isinstance(attempts, list):
        raise ValueError("attempts must be a list")
    if len(records) + len(attempts) > IMPORT_MAX_RECORDS:
        raise ValueError(f"Import contains more than {IMPORT_MAX_RECORDS} records")

    validated = [_validate_import_record(item) for item in records]
    validated_attempts = [_validate_import_attempt(item) for item in attempts]

    path = _path(db_path)
    async with connect_db(path) as db:
        await db.execute("BEGIN")
        try:
            if not merge:
                await db.execute("DELETE FROM play_history WHERE username = ?", (username,))
                await db.execute("DELETE FROM play_attempts WHERE username = ?", (username,))

            inserted = 0
            for record in validated:
                await db.execute(
                    """
                    INSERT INTO play_history (
                        played_at, username, client_name, track_id,
                        title, artist, album, is_transcoding, listen_duration_sec, source
                        , source_id, source_name, duration_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        "import",
                        record["source_id"],
                        record["source_name"],
                        record["duration_confidence"],
                    ),
                )
                inserted += 1
            attempts_inserted = 0
            for record in validated_attempts:
                await db.execute(
                    """
                    INSERT INTO play_attempts (
                        played_at, username, client_name, track_id, title,
                        artist, album, is_transcoding, duration_sec, outcome,
                        source_id, source_name, duration_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'short_play', ?, ?, ?)
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
                        record["duration_sec"],
                        record["source_id"],
                        record["source_name"],
                        record["duration_confidence"],
                    ),
                )
                attempts_inserted += 1
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return {
        "imported": inserted,
        "attempts_imported": attempts_inserted,
        "merge": int(merge),
    }


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
    preview = await preview_delete_user(username, path)
    if preview["records_to_delete"] == 0:
        return {"deleted": 0}

    async with connect_db(path) as db:
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
