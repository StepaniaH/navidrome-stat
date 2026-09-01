"""Shared helpers for statistics query modules."""

from src import config
from src.stats_scope import StatsScope
from src.windows import (
    _previous_window_predicate,
    _source_predicate,
    _username_predicate,
    _window_predicate,
)


def database_path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


def scope_predicate(
    scope: StatsScope,
    *,
    previous: bool = False,
) -> tuple[str, list]:
    """Build the shared date, source, and user predicate for ``scope``."""
    predicate_factory = _previous_window_predicate if previous else _window_predicate
    predicate, params = predicate_factory(
        scope.days,
        scope.timezone_name,
        scope.start_date,
        scope.end_date,
    )
    predicate, params = _source_predicate(predicate, params, scope.source_id)
    return _username_predicate(predicate, params, scope.username)
