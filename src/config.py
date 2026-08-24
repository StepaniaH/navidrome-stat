"""Parse bounded runtime values from environment variables."""

from __future__ import annotations

import os
from typing import Optional

# Single source of truth for the SQLite file location. Modules resolve this
# attribute at call time so tests can patch it in one place.
DATABASE_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")


def parse_clamped_int(
    raw: Optional[str],
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    """Parse an integer, using the default for invalid input and clamping bounds."""
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def env_int(name: str, *, default: int, min_value: int, max_value: int) -> int:
    """Read ``name`` from the environment, clamped to the given bounds."""
    return parse_clamped_int(
        os.getenv(name),
        default=default,
        min_value=min_value,
        max_value=max_value,
    )


def env_flag(name: str, *, default: bool = False) -> bool:
    """Read a flag accepting 1, true, yes, or on; blank values use the default."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
