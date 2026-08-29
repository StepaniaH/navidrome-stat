"""Durable progress for resumable history importers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src import config
from src.schema import get_meta_value, set_meta_value
from src.sqlite import connect_db


def _cursor_key(source_id: str, username: str) -> str:
    identity = json.dumps(
        [source_id, username], ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"song_history_cursor:{digest}"


def _default_cursor() -> dict[str, Any]:
    return {
        "next_offset": 0,
        "complete": False,
        "failure_count": 0,
        "retry_at": None,
    }


async def load_song_history_cursor(
    source_id: str,
    username: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    path = config.DATABASE_PATH if db_path is None else db_path
    async with connect_db(path) as db:
        raw = await get_meta_value(db, _cursor_key(source_id, username))
    if raw is None:
        return _default_cursor()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return _default_cursor()
    if not isinstance(data, dict):
        return _default_cursor()
    return {
        "next_offset": max(int(data.get("next_offset", 0)), 0),
        "complete": bool(data.get("complete", False)),
        "failure_count": min(max(int(data.get("failure_count", 0)), 0), 30),
        "retry_at": data.get("retry_at") if isinstance(data.get("retry_at"), str) else None,
    }


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
            _cursor_key(source_id, username),
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
        )
        await db.commit()
