"""Minimal durable markers that prevent deleted history from returning."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import aiosqlite

from src.schema import get_meta_value, set_meta_value


def _deletion_cutoff_key(username: str) -> str:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return f"privacy_deletion_cutoff:{digest}"


async def get_user_deletion_cutoff(
    db: aiosqlite.Connection,
    username: str,
) -> str | None:
    return await get_meta_value(db, _deletion_cutoff_key(username))


async def set_user_deletion_cutoff(
    db: aiosqlite.Connection,
    username: str,
    cutoff: str,
) -> None:
    await set_meta_value(db, _deletion_cutoff_key(username), cutoff)


def event_is_after_cutoff(played_at: object, cutoff: str) -> bool:
    """Return true only when an imported event is later than a deletion."""

    def parse(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    event_at = parse(played_at)
    deleted_at = parse(cutoff)
    return bool(event_at and deleted_at and event_at > deleted_at)
