"""Retention policy, storage estimates, and purge execution."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from src.privacy_common import database_path as _path
from src.privacy_constants import (
    META_RETENTION_DAYS,
    META_RETENTION_PERMANENT,
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
)
from src.schema import PAYLOAD_BYTES_SQL, get_meta_value, set_meta_value
from src.sqlite import connect_db
from src.windows import utc_instant


def validate_retention_days(days: Optional[int]) -> Optional[int]:
    if days is None:
        return None
    if not isinstance(days, int) or days < RETENTION_MIN_DAYS or days > RETENTION_MAX_DAYS:
        raise ValueError(
            f"retention_days must be null (permanent) or between "
            f"{RETENTION_MIN_DAYS} and {RETENTION_MAX_DAYS}"
        )
    return days


async def get_retention_days(db_path: str | None = None) -> Optional[int]:
    """Returns retention days, or None for permanent retention."""
    path = _path(db_path)
    async with connect_db(path) as db:
        raw = await get_meta_value(db, META_RETENTION_DAYS)
    if raw is None or raw == META_RETENTION_PERMANENT:
        return None
    return int(raw)


async def set_retention_days(days: Optional[int], db_path: str | None = None) -> None:
    days = validate_retention_days(days)
    path = _path(db_path)
    async with connect_db(path) as db:
        if days is None:
            await set_meta_value(db, META_RETENTION_DAYS, META_RETENTION_PERMANENT)
        else:
            await set_meta_value(db, META_RETENTION_DAYS, str(days))
        await db.commit()


_RETENTION_BEFORE_SQL = "played_at_epoch < unixepoch(?)"


def _retention_cutoff_sql(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return utc_instant(cutoff)


async def _play_history_storage_metrics(
    db: aiosqlite.Connection,
    *,
    played_before: str | None = None,
) -> tuple[int, int]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if played_before is not None:
        where_clause = f" WHERE {_RETENTION_BEFORE_SQL}"
        params = (played_before,)

    async with db.execute(
        f"SELECT COUNT(*), COALESCE(SUM({PAYLOAD_BYTES_SQL}), 0) FROM play_history{where_clause}",
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
        where_clause = f" WHERE {_RETENTION_BEFORE_SQL}"
        params = (played_before,)
    async with db.execute(
        f"SELECT COUNT(*), COALESCE(SUM({PAYLOAD_BYTES_SQL}), 0) FROM play_attempts{where_clause}",
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

    cutoff = _retention_cutoff_sql(days)
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
    return {
        "records_to_delete": records_to_delete,
        "history_records_to_delete": history_to_delete,
        "attempt_records_to_delete": attempts_to_delete,
        "retention_days": days,
        "bytes_to_delete": bytes_to_delete,
        # SQLite DELETE makes pages reusable but does not shrink the file.
        # Keep this compatibility field truthful unless a future explicit
        # compaction operation is added.
        "estimated_database_bytes_after": storage["database_bytes"],
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

    cutoff = _retention_cutoff_sql(days)
    async with connect_db(path) as db:
        history_cursor = await db.execute(
            f"DELETE FROM play_history WHERE {_RETENTION_BEFORE_SQL}",
            (cutoff,),
        )
        attempt_cursor = await db.execute(
            f"DELETE FROM play_attempts WHERE {_RETENTION_BEFORE_SQL}",
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
