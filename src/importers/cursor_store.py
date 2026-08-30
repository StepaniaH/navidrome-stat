"""Durable progress for resumable history importers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src import config
from src.schema import get_meta_value, set_meta_value
from src.sqlite import connect_db


def _identity_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def song_history_cursor_prefix(username: str) -> str:
    """Return the hashed key prefix used for one upstream username."""
    return f"song_history_cursor:{_identity_digest(username)}:"


def song_history_cursor_key(source_id: str, username: str) -> str:
    return f"{song_history_cursor_prefix(username)}{_identity_digest(source_id)}"


def _default_cursor() -> dict[str, Any]:
    return {
        "next_offset": 0,
        "complete": False,
        "failure_count": 0,
        "retry_at": None,
    }


def _normalize_cursor(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _default_cursor()
    try:
        next_offset = max(int(data.get("next_offset", 0)), 0)
        failure_count = min(max(int(data.get("failure_count", 0)), 0), 30)
    except (TypeError, ValueError):
        return _default_cursor()
    retry_at = data.get("retry_at")
    return {
        "next_offset": next_offset,
        "complete": bool(data.get("complete", False)),
        "failure_count": failure_count,
        "retry_at": retry_at if isinstance(retry_at, str) else None,
    }


def seal_song_history_cursor(raw: str | None) -> str:
    """Encode a completed cursor that prevents deleted history from returning."""
    try:
        data = json.loads(raw) if raw is not None else None
    except (TypeError, ValueError):
        data = None
    cursor = _normalize_cursor(data)
    cursor.update(complete=True, failure_count=0, retry_at=None)
    return json.dumps(cursor, ensure_ascii=False, separators=(",", ":"))


async def load_song_history_cursor(
    source_id: str,
    username: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    path = config.DATABASE_PATH if db_path is None else db_path
    async with connect_db(path) as db:
        raw = await get_meta_value(db, song_history_cursor_key(source_id, username))
    if raw is None:
        return _default_cursor()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return _default_cursor()
    return _normalize_cursor(data)


async def save_song_history_cursor(
    source_id: str,
    username: str,
    cursor: dict[str, Any],
    db_path: str | None = None,
) -> None:
    path = config.DATABASE_PATH if db_path is None else db_path
    normalized = {
        "next_offset": max(int(cursor.get("next_offset", 0)), 0),
        "complete": bool(cursor.get("complete", False)),
        "failure_count": min(max(int(cursor.get("failure_count", 0)), 0), 30),
        "retry_at": cursor.get("retry_at"),
    }
    async with connect_db(path) as db:
        await set_meta_value(
            db,
            song_history_cursor_key(source_id, username),
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
        )
        await db.commit()
