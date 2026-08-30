"""Shared SQLite connection policy for the single-host application."""

from contextlib import asynccontextmanager
from contextvars import ContextVar

import aiosqlite

SQLITE_BUSY_TIMEOUT_MS = 5_000
_active_read_connection: ContextVar[tuple[str, aiosqlite.Connection] | None] = ContextVar(
    "active_sqlite_read_connection", default=None
)


@asynccontextmanager
async def connect_db(path: str, *, initialize: bool = False):
    """Open a connection with the application's SQLite pragmas."""

    active = _active_read_connection.get()
    if not initialize and active is not None and active[0] == str(path):
        yield active[1]
        return

    async with aiosqlite.connect(
        path,
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1_000,
    ) as db:
        await db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        await db.execute("PRAGMA foreign_keys = ON")
        if initialize:
            await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        yield db


@asynccontextmanager
async def read_snapshot(path: str):
    """Reuse one read transaction across nested query helpers in this task."""

    normalized_path = str(path)
    if _active_read_connection.get() is not None:
        raise RuntimeError("nested SQLite read snapshots are not supported")
    async with connect_db(normalized_path) as db:
        await db.execute("BEGIN")
        token = _active_read_connection.set((normalized_path, db))
        try:
            yield db
        finally:
            _active_read_connection.reset(token)
            await db.rollback()
