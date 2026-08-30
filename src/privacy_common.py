"""Shared database-path resolution for privacy modules."""

from src import config


def database_path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path
