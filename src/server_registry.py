"""CRUD helpers for configured Navidrome servers."""

from datetime import datetime, timezone

import aiosqlite

from src import config
from src.sqlite import connect_db


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


async def list_servers(db_path: str | None = None):
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, display_name, url, username, password, enabled "
            "FROM servers ORDER BY created_at, id"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_server(server_id: str, db_path: str | None = None):
    rows = await list_servers(db_path)
    return next((row for row in rows if row["id"] == server_id), None)


async def save_server(server: dict, db_path: str | None = None) -> None:
    path = _path(db_path)
    now = datetime.now(timezone.utc).isoformat()
    async with connect_db(path) as db:
        await db.execute("""
            INSERT INTO servers (id, display_name, url, username, password, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                url=excluded.url, username=excluded.username, password=excluded.password,
                enabled=excluded.enabled, updated_at=excluded.updated_at
        """, (server["id"], server["display_name"], server["url"], server["username"],
              server["password"], int(server.get("enabled", True)), now, now))
        await db.commit()


async def delete_server(server_id: str, db_path: str | None = None) -> bool:
    path = _path(db_path)
    async with connect_db(path) as db:
        cursor = await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await db.commit()
        return cursor.rowcount > 0
