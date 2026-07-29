"""Navidrome source configuration persistence and resolution.

Configuration precedence (highest first):
  1. Non-empty values supplied by an API request (e.g. the /api/source/test
     "test these values" payload).
  2. Environment variables (NAVIDROME_URL / NAVIDROME_USER / NAVIDROME_PASS).
  3. Saved values stored in the local SQLite `schema_meta` table.

The password is treated as sensitive: it is persisted locally so the GUI can
be a fallback when the corresponding env var is absent, but it is never
returned by GET endpoints and never logged here. Local SQLite storage is an
accepted tradeoff for self-hosted software; deployers must protect the
database file with filesystem access controls.

This module must not import from `src.main` to avoid circular imports.
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


async def _get_meta(key: str, db_path: str | None = None) -> Optional[str]:
    path = _path(db_path)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT value FROM schema_meta WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def _set_meta(key: str, value: str, db_path: str | None = None) -> None:
    path = _path(db_path)
    async with connect_db(path) as db:
        await db.execute(
            """
            INSERT INTO schema_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await db.commit()


async def get_saved_source_config(
    db_path: str | None = None,
) -> dict[str, Optional[str]]:
    """Return saved source config from the DB; keys are None when unsaved."""
    return {
        "url": await _get_meta(SOURCE_URL_KEY, db_path),
        "user": await _get_meta(SOURCE_USER_KEY, db_path),
        "password": await _get_meta(SOURCE_PASSWORD_KEY, db_path),
    }


async def set_saved_source_config(
    url: str,
    user: str,
    password: Optional[str] = None,
    db_path: str | None = None,
) -> None:
    """Persist url and user; password only updates when a non-empty value is supplied."""
    await _set_meta(SOURCE_URL_KEY, url, db_path)
    await _set_meta(SOURCE_USER_KEY, user, db_path)
    if password:
        await _set_meta(SOURCE_PASSWORD_KEY, password, db_path)


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
