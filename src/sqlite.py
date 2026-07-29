"""Shared SQLite connection policy for the single-host application."""

from contextlib import asynccontextmanager

import aiosqlite

SQLITE_BUSY_TIMEOUT_MS = 5_000


@asynccontextmanager
async def connect_db(path: str, *, initialize: bool = False):
    """Open one configured aiosqlite connection.

    WAL is selected while initializing the database. Every connection enables
    foreign-key enforcement and the same bounded busy timeout. This remains a
    single-host SQLite policy; it does not make network filesystems or multiple
    application replicas safe.
    """

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
