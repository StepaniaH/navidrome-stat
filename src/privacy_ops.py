"""Privacy-oriented data retention, export, and import operations."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from src import config
from src.importers.cursor_store import (
    seal_song_history_cursor,
    song_history_cursor_key,
    song_history_cursor_prefix,
)
from src.privacy_markers import set_user_deletion_cutoff
from src.schema import (
    LEGACY_SOURCE_ID,
    PAYLOAD_BYTES_SQL,
    get_meta_value,
    set_meta_value,
)
from src.sqlite import connect_db
from src.windows import utc_instant


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


EXPORT_FORMAT_VERSION = 3
SUPPORTED_IMPORT_FORMAT_VERSIONS = (1, 2, 3)
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


def _record_fingerprint(
    username: str,
    kind: str,
    record: dict[str, Any],
) -> str:
    canonical = {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "fingerprint", "source"}
    }
    played_at = canonical.get("played_at")
    if isinstance(played_at, str):
        canonical["played_at"] = _validate_timestamp(played_at)
    encoded = json.dumps(
        [kind, username, canonical],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_to_export_record(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "played_at": row["played_at"],
        "client_name": row["client_name"],
        "track_id": row["track_id"],
        "title": row["title"],
        "artist": row["artist"],
        "artist_id": row["artist_id"],
        "album": row["album"],
        "album_id": row["album_id"],
        "is_transcoding": row["is_transcoding"],
        "listen_duration_sec": row["listen_duration_sec"],
        "source": row["source"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "duration_confidence": row["duration_confidence"],
    }


def _row_to_export_attempt(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "played_at": row["played_at"],
        "client_name": row["client_name"],
        "track_id": row["track_id"],
        "title": row["title"],
        "artist": row["artist"],
        "artist_id": row["artist_id"],
        "album": row["album"],
        "album_id": row["album_id"],
        "is_transcoding": row["is_transcoding"],
        "duration_sec": row["duration_sec"],
        "outcome": row["outcome"],
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
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artist_id, album, album_id,
                   is_transcoding, listen_duration_sec, source, source_id,
                   source_name, duration_confidence
            FROM play_history
            WHERE username = ?
            ORDER BY played_at_epoch ASC, id ASC
            """,
            (username,),
        ) as cursor:
            rows = await cursor.fetchall()
        async with db.execute(
            """
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artist_id, album, album_id, is_transcoding, duration_sec,
                   outcome, source_id, source_name, duration_confidence
            FROM play_attempts
            WHERE username = ?
            ORDER BY played_at_epoch ASC, id ASC
            """,
            (username,),
        ) as cursor:
            attempt_rows = await cursor.fetchall()

    records = [_row_to_export_record(row) for row in rows]
    for record in records:
        record["fingerprint"] = _record_fingerprint(username, "history", record)
    attempts = [_row_to_export_attempt(row) for row in attempt_rows]
    for attempt in attempts:
        attempt["fingerprint"] = _record_fingerprint(username, "attempt", attempt)

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "username": username,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "records": records,
        "attempt_count": len(attempt_rows),
        "attempts": attempts,
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
        raise ValueError(f"Import {field} must be between 0 and {IMPORT_MAX_DURATION_SEC}")
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
        "artist_id": _validate_text(record.get("artist_id"), "artist_id"),
        "album": _validate_text(record.get("album"), "album"),
        "album_id": _validate_text(record.get("album_id"), "album_id"),
        "is_transcoding": _validate_transcoding(record.get("is_transcoding")),
        "listen_duration_sec": _validate_duration(
            record.get("listen_duration_sec", 0),
            "listen_duration_sec",
        ),
        "source_id": _validate_text(record.get("source_id"), "source_id"),
        "source_name": _validate_text(record.get("source_name"), "source_name"),
        "duration_confidence": (
            "reported" if record.get("duration_confidence") == "reported" else "estimated"
        ),
    }


def _validate_import_attempt(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Import attempts must be objects")
    validated = _validate_import_record(
        {
            **record,
            "listen_duration_sec": record.get("duration_sec", 0),
        }
    )
    validated["duration_sec"] = validated.pop("listen_duration_sec")
    validated["outcome"] = "short_play"
    return validated


def _attach_import_identity(
    raw: dict[str, Any],
    validated: dict[str, Any],
    *,
    format_version: int,
    username: str,
    kind: str,
    occurrence: int,
) -> dict[str, Any]:
    computed = _record_fingerprint(username, kind, validated)
    if format_version >= 3:
        record_id = _validate_text(raw.get("record_id"), "record_id", required=True)
        fingerprint = _validate_text(raw.get("fingerprint"), "fingerprint", required=True)
        assert record_id is not None and fingerprint is not None
        if len(record_id) > 128:
            raise ValueError("Import record_id is too long")
        normalized_fingerprint = fingerprint.lower()
        if len(normalized_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in normalized_fingerprint
        ):
            raise ValueError("Import fingerprint must be a SHA-256 hex digest")
        identity_conflict = normalized_fingerprint != computed
    else:
        record_id = f"legacy-{computed}-{occurrence}"
        normalized_fingerprint = computed
        identity_conflict = False
    return {
        **validated,
        "record_id": record_id,
        "fingerprint": normalized_fingerprint,
        "identity_conflict": identity_conflict,
    }


async def _existing_import_fingerprint(
    db: aiosqlite.Connection,
    *,
    username: str,
    kind: str,
    record_id: str,
) -> str | None:
    if kind == "history":
        query = """
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artist_id, album, album_id, is_transcoding,
                   listen_duration_sec, source, source_id, source_name,
                   duration_confidence
            FROM play_history
            WHERE username = ? AND record_id = ?
        """
        converter = _row_to_export_record
    else:
        query = """
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artist_id, album, album_id, is_transcoding, duration_sec,
                   outcome, source_id, source_name, duration_confidence
            FROM play_attempts
            WHERE username = ? AND record_id = ?
        """
        converter = _row_to_export_attempt
    async with db.execute(query, (username, record_id)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return _record_fingerprint(username, kind, converter(row))


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

    format_version = int(payload["format_version"])
    occurrences: dict[tuple[str, str], int] = {}

    def identify(raw: dict[str, Any], kind: str) -> dict[str, Any]:
        base = _validate_import_record(raw) if kind == "history" else _validate_import_attempt(raw)
        fingerprint = _record_fingerprint(username, kind, base)
        occurrence_key = (kind, fingerprint)
        occurrence = occurrences.get(occurrence_key, 0)
        occurrences[occurrence_key] = occurrence + 1
        return _attach_import_identity(
            raw,
            base,
            format_version=format_version,
            username=username,
            kind=kind,
            occurrence=occurrence,
        )

    validated = [identify(item, "history") for item in records]
    validated_attempts = [identify(item, "attempt") for item in attempts]

    seen_identities: dict[tuple[str, str], str] = {}
    for kind, items in (("history", validated), ("attempt", validated_attempts)):
        for record in items:
            identity_key = (kind, record["record_id"])
            previous = seen_identities.get(identity_key)
            if previous is not None and previous != record["fingerprint"]:
                record["identity_conflict"] = True
            else:
                seen_identities[identity_key] = record["fingerprint"]

    payload_conflicts = sum(
        int(record["identity_conflict"]) for record in [*validated, *validated_attempts]
    )
    if not merge and payload_conflicts:
        return {
            "imported": 0,
            "attempts_imported": 0,
            "inserted": 0,
            "skipped": 0,
            "conflicts": payload_conflicts,
            "merge": 0,
        }

    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN")
        try:
            if not merge:
                await db.execute("DELETE FROM play_history WHERE username = ?", (username,))
                await db.execute("DELETE FROM play_attempts WHERE username = ?", (username,))

            inserted = 0
            skipped = 0
            conflicts = 0
            for record in validated:
                if record["identity_conflict"]:
                    conflicts += 1
                    continue
                cursor = await db.execute(
                    """
                    INSERT INTO play_history (
                        played_at, username, client_name, track_id,
                        title, artist, artist_id, album, album_id, is_transcoding,
                        listen_duration_sec, source, source_id, source_name,
                        duration_confidence, record_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) WHERE record_id IS NOT NULL DO NOTHING
                    """,
                    (
                        record["played_at"],
                        username,
                        record["client_name"],
                        record["track_id"],
                        record["title"],
                        record["artist"],
                        record["artist_id"],
                        record["album"],
                        record["album_id"],
                        record["is_transcoding"],
                        record["listen_duration_sec"],
                        "import",
                        record["source_id"],
                        record["source_name"],
                        record["duration_confidence"],
                        record["record_id"],
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
                    continue
                existing_fingerprint = await _existing_import_fingerprint(
                    db,
                    username=username,
                    kind="history",
                    record_id=record["record_id"],
                )
                if existing_fingerprint == record["fingerprint"]:
                    skipped += 1
                else:
                    conflicts += 1
            attempts_inserted = 0
            for record in validated_attempts:
                if record["identity_conflict"]:
                    conflicts += 1
                    continue
                cursor = await db.execute(
                    """
                    INSERT INTO play_attempts (
                        played_at, username, client_name, track_id, title,
                        artist, artist_id, album, album_id, is_transcoding,
                        duration_sec, outcome, source_id, source_name,
                        duration_confidence, record_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) WHERE record_id IS NOT NULL DO NOTHING
                    """,
                    (
                        record["played_at"],
                        username,
                        record["client_name"],
                        record["track_id"],
                        record["title"],
                        record["artist"],
                        record["artist_id"],
                        record["album"],
                        record["album_id"],
                        record["is_transcoding"],
                        record["duration_sec"],
                        record["outcome"],
                        record["source_id"],
                        record["source_name"],
                        record["duration_confidence"],
                        record["record_id"],
                    ),
                )
                if cursor.rowcount:
                    attempts_inserted += 1
                    continue
                existing_fingerprint = await _existing_import_fingerprint(
                    db,
                    username=username,
                    kind="attempt",
                    record_id=record["record_id"],
                )
                if existing_fingerprint == record["fingerprint"]:
                    skipped += 1
                else:
                    conflicts += 1
            if not merge and conflicts:
                await db.rollback()
                return {
                    "imported": 0,
                    "attempts_imported": 0,
                    "inserted": 0,
                    "skipped": 0,
                    "conflicts": conflicts,
                    "merge": 0,
                }
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return {
        "imported": inserted,
        "attempts_imported": attempts_inserted,
        "inserted": inserted + attempts_inserted,
        "skipped": skipped,
        "conflicts": conflicts,
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
