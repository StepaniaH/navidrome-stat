"""Versioned user-data archive export and validated import."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.artist_credits import encode_artists, normalize_artists
from src.core_types import classify_history_duration_quality
from src.privacy_common import database_path as _path
from src.privacy_constants import (
    EXPORT_FORMAT_VERSION,
    IMPORT_MAX_DURATION_SEC,
    IMPORT_MAX_PAYLOAD_BYTES,
    IMPORT_MAX_RECORDS,
    IMPORT_MAX_TEXT_LENGTH,
    SUPPORTED_IMPORT_FORMAT_VERSIONS,
)
from src.sqlite import connect_db


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


def _row_to_archive_record(
    row: aiosqlite.Row,
    *,
    freeze_duration_quality: bool,
) -> dict[str, Any]:
    duration_confidence = row["duration_confidence"]
    if freeze_duration_quality:
        quality = classify_history_duration_quality(
            listen_duration_sec=row["listen_duration_sec"],
            source=row["source"],
            session_id=row["session_id"],
            finalized=row["finalized"],
            duration_confidence=duration_confidence,
        )
        duration_confidence = quality if quality != "unknown" else "estimated"
    return {
        "record_id": row["record_id"],
        "played_at": row["played_at"],
        "client_name": row["client_name"],
        "track_id": row["track_id"],
        "title": row["title"],
        "artist": row["artist"],
        "artist_id": row["artist_id"],
        **({"artists": json.loads(row["artists"])} if row["artists"] else {}),
        "album": row["album"],
        "album_id": row["album_id"],
        "is_transcoding": row["is_transcoding"],
        "listen_duration_sec": row["listen_duration_sec"],
        "source": row["source"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "duration_confidence": duration_confidence,
    }


def _row_to_export_record(row: aiosqlite.Row) -> dict[str, Any]:
    return _row_to_archive_record(row, freeze_duration_quality=True)


def _row_to_legacy_export_record(row: aiosqlite.Row) -> dict[str, Any]:
    return _row_to_archive_record(row, freeze_duration_quality=False)


def _row_to_export_attempt(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "played_at": row["played_at"],
        "client_name": row["client_name"],
        "track_id": row["track_id"],
        "title": row["title"],
        "artist": row["artist"],
        "artist_id": row["artist_id"],
        **({"artists": json.loads(row["artists"])} if row["artists"] else {}),
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
                   artists, artist_id, album, album_id,
                   is_transcoding, listen_duration_sec, source, source_id,
                   source_name, session_id, finalized, duration_confidence
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
                   artists, artist_id, album, album_id, is_transcoding, duration_sec,
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


def _validate_duration(
    value: Any,
    field: str,
    *,
    allow_none: bool = False,
) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Import {field} must be an integer")
    if value < 0 or value > IMPORT_MAX_DURATION_SEC:
        raise ValueError(f"Import {field} must be between 0 and {IMPORT_MAX_DURATION_SEC}")
    return value


def _validate_duration_confidence(value: Any) -> str:
    if value == "reported":
        return "reported"
    if value == "lower_bound":
        return "lower_bound"
    return "estimated"


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
            allow_none=True,
        ),
        "source_id": _validate_text(record.get("source_id"), "source_id"),
        "source_name": _validate_text(record.get("source_name"), "source_name"),
        "duration_confidence": _validate_duration_confidence(
            record.get("duration_confidence")
        ),
    }


def _validate_import_attempt(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Import attempts must be objects")
    duration_sec = _validate_duration(record.get("duration_sec", 0), "duration_sec")
    assert duration_sec is not None
    validated = _validate_import_record(
        {
            **record,
            "listen_duration_sec": duration_sec,
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
    format_version: int,
) -> str | None:
    if kind == "history":
        query = """
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artists, artist_id, album, album_id, is_transcoding,
                   listen_duration_sec, source, source_id, source_name,
                   session_id, finalized, duration_confidence
            FROM play_history
            WHERE username = ? AND record_id = ?
        """
        converter = (
            _row_to_export_record
            if format_version >= 4
            else _row_to_legacy_export_record
        )
    else:
        query = """
            SELECT record_id, played_at, client_name, track_id, title, artist,
                   artists, artist_id, album, album_id, is_transcoding, duration_sec,
                   outcome, source_id, source_name, duration_confidence
            FROM play_attempts
            WHERE username = ? AND record_id = ?
        """
        converter = _row_to_export_attempt
    async with db.execute(query, (username, record_id)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    record = converter(row)
    if format_version < 5:
        record.pop("artists", None)
    return _record_fingerprint(username, kind, record)


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
        if format_version >= 5 and "artists" in raw:
            artists = raw["artists"]
            if (not isinstance(artists, list) or not 1 <= len(artists) <= 64
                    or any(not isinstance(item, dict) for item in artists)):
                raise ValueError("Import artists must be a list of 1 to 64 artists")
            for item in artists:
                name = _validate_text(item.get("name"), "artists.name", required=True)
                artist_id = _validate_text(item.get("id"), "artists.id")
                if len(name) > 512 or (artist_id is not None and len(artist_id) > 128):
                    raise ValueError("Import artist name or id is too long")
            normalized = normalize_artists(artists)
            if normalized != artists:
                raise ValueError("Import artists must use unique, normalized names and ids")
            base["artists"] = normalized
        if (
            kind == "history"
            and format_version >= 4
            and base["listen_duration_sec"] is None
            and base["duration_confidence"] != "estimated"
        ):
            raise ValueError(
                "Format v4 records without a duration must use estimated confidence"
            )
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
                        duration_confidence, record_id, artists
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        encode_artists(record.get("artists")),
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
                    format_version=format_version,
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
                        duration_confidence, record_id, artists
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        encode_artists(record.get("artists")),
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
                    format_version=format_version,
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
