"""Shared SQLite connection policy for the single-host application."""

from contextlib import asynccontextmanager

import aiosqlite

SQLITE_BUSY_TIMEOUT_MS = 5_000


@asynccontextmanager
async def connect_db(path: str, *, initialize: bool = False):
    """Open a connection with the application's SQLite pragmas."""

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
