"""CRUD helpers for configured Navidrome servers."""

import logging
from datetime import datetime, timezone

import aiosqlite

from src import config
from src.secretbox import decrypt, encrypt, is_encrypted, read_key_if_present
from src.sqlite import connect_db

logger = logging.getLogger(__name__)


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


def _decrypt_credential(value: str | None, key: bytes | None) -> str:
    """Open a stored credential, degrading to empty on any failure."""
    if not value:
        return ""
    if not is_encrypted(value):
        logger.error("Saved credential is not encrypted (type=%s)", type(value).__name__)
        return ""
    try:
        return decrypt(value, key)
    except Exception as exc:
        logger.error("Saved credential decryption failed (type=%s)", type(exc).__name__)
        return ""


async def list_servers(db_path: str | None = None):
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, display_name, url, username, password, enabled, "
            "backfill_playlist_id FROM servers ORDER BY created_at, id"
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
    try:
        key = read_key_if_present(path)
    except Exception:
        key = None
    for row in rows:
        row["password"] = _decrypt_credential(row["password"], key)
    return rows


async def list_server_options(db_path: str | None = None) -> list[dict[str, str]]:
    """Return the non-sensitive server identity used by statistics views."""
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, display_name FROM servers ORDER BY created_at, id"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_server(server_id: str, db_path: str | None = None):
    rows = await list_servers(db_path)
    return next((row for row in rows if row["id"] == server_id), None)


async def save_server(server: dict, db_path: str | None = None) -> None:
    path = _path(db_path)
    now = datetime.now(timezone.utc).isoformat()
    stored_password = encrypt(server["password"], db_path=path)
    async with connect_db(path) as db:
        await db.execute(
            """
            INSERT INTO servers (id, display_name, url, username, password, enabled, backfill_playlist_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                url=excluded.url, username=excluded.username, password=excluded.password,
                enabled=excluded.enabled, backfill_playlist_id=excluded.backfill_playlist_id,
                updated_at=excluded.updated_at
        """,
            (
                server["id"],
                server["display_name"],
                server["url"],
                server["username"],
                stored_password,
                int(server.get("enabled", True)),
                server.get("backfill_playlist_id") or None,
                now,
                now,
            ),
        )
        await db.commit()


async def delete_server(server_id: str, db_path: str | None = None) -> bool:
    path = _path(db_path)
    async with connect_db(path) as db:
        cursor = await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await db.commit()
        return cursor.rowcount > 0
