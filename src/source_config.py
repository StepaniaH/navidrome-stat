"""Persist and resolve Navidrome source configuration.

Non-empty request values override environment variables, which override saved
SQLite values. Saved passwords are never returned by GET endpoints or logged.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

from src import database
from src.sqlite import connect_db

SOURCE_URL_KEY = "source_url"
SOURCE_USER_KEY = "source_user"
SOURCE_PASSWORD_KEY = "source_password"

ENV_URL = "NAVIDROME_URL"
ENV_USER = "NAVIDROME_USER"
ENV_PASS = "NAVIDROME_PASS"


def _path(db_path: str | None = None) -> str:
    return database.DB_PATH if db_path is None else db_path


async def _set_meta(db, key: str, value: str) -> None:
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


async def get_saved_source_config(
    db_path: str | None = None,
) -> dict[str, Optional[str]]:
    """Return saved source config from the DB; keys are None when unsaved."""
    path = _path(db_path)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT key, value FROM schema_meta WHERE key IN (?, ?, ?)",
            (SOURCE_URL_KEY, SOURCE_USER_KEY, SOURCE_PASSWORD_KEY),
        ) as cursor:
            saved = dict(await cursor.fetchall())
    return {
        "url": saved.get(SOURCE_URL_KEY),
        "user": saved.get(SOURCE_USER_KEY),
        "password": saved.get(SOURCE_PASSWORD_KEY),
    }


async def set_saved_source_config(
    url: str,
    user: str,
    password: Optional[str] = None,
    db_path: str | None = None,
) -> None:
    """Persist url and user; password only updates when a non-empty value is supplied."""
    path = _path(db_path)
    async with connect_db(path) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _set_meta(db, SOURCE_URL_KEY, url)
            await _set_meta(db, SOURCE_USER_KEY, user)
            if password:
                await _set_meta(db, SOURCE_PASSWORD_KEY, password)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


async def replace_saved_source_config(
    *,
    url: Optional[str],
    user: Optional[str],
    password: Optional[str],
    db_path: str | None = None,
) -> None:
    """Atomically replace the saved tuple, deleting fields set to None."""
    path = _path(db_path)
    values = {
        SOURCE_URL_KEY: url,
        SOURCE_USER_KEY: user,
        SOURCE_PASSWORD_KEY: password,
    }
    async with connect_db(path) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for key, value in values.items():
                if value is None:
                    await db.execute("DELETE FROM schema_meta WHERE key = ?", (key,))
                else:
                    await _set_meta(db, key, value)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


def validate_source_url(url: Optional[str]) -> str:
    """Validate URL scheme is http/https and return normalized URL."""
    if not url or not url.strip():
        raise ValueError("url is required")
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must use http or https scheme")
    if not parsed.netloc:
        raise ValueError("url must include a host")
    return url.rstrip("/")


def resolve_source_config(
    overrides: Optional[dict[str, Optional[str]]] = None,
    saved: Optional[dict[str, Optional[str]]] = None,
) -> dict[str, Optional[str]]:
    """Resolve effective source config. Request overrides > env > saved DB.

    `overrides` values are only considered when non-empty (truthy). Empty
    string or None falls back to env, then saved DB.
    """
    overrides = overrides or {}
    saved = saved or {}

    def pick(key: str, env_name: str) -> Optional[str]:
        override = overrides.get(key)
        if override:
            return override
        env = os.getenv(env_name)
        if env:
            return env
        return saved.get(key)

    return {
        "url": pick("url", ENV_URL),
        "user": pick("user", ENV_USER),
        "password": pick("password", ENV_PASS),
    }


async def resolve_effective_source_config(
    db_path: str | None = None,
) -> dict[str, Optional[str]]:
    """Resolve the configuration used by the live polling client (env > saved)."""
    saved = await get_saved_source_config(db_path)
    return resolve_source_config(overrides=None, saved=saved)


def has_full_config(config: dict[str, Optional[str]]) -> bool:
    return all([config.get("url"), config.get("user"), config.get("password")])


def redacted_view(config: dict[str, Optional[str]]) -> dict[str, Any]:
    """Return a non-sensitive view for the GET endpoint."""
    return {
        "url": config.get("url"),
        "username": config.get("user"),
        "password_configured": bool(config.get("password")),
    }
