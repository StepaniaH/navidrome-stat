"""Safe environment-variable parsing for numeric runtime configuration.

These helpers centralise clamping/validation so module-level imports in
``src.main`` and ``src.sessions`` cannot crash on user-supplied env values.
They never read secrets and only return deterministic ints.
"""

from __future__ import annotations

import os
from typing import Optional


def parse_clamped_int(
    raw: Optional[str],
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    """Parse ``raw`` to int with safe bounds.

    Non-numeric / missing values fall back to ``default``. Numeric values
    outside ``[min_value, max_value]`` are clamped to the nearest bound.
    """
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