"""Consistent dashboard reads over one SQLite snapshot."""

import time

from src import config
from src.config import env_int
from src.runtime_state import runtime_state
from src.schemas import HISTORY_LIMIT_DEFAULT, TOP_LIMIT_DEFAULT
from src.server_registry import list_server_options
from src.sqlite import read_snapshot
from src.stats_queries import (
    get_playback_history,
    get_player_stats,
    get_server_stats,
    get_summary,
    get_time_bucket_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
)
from src.stats_query_entities import EntityIdentity, get_entity_detail
from src.stats_query_relations import RelationDimension, get_data_relations
from src.stats_scope import StatsScope

QUERY_BUDGET_SECONDS = env_int(
    "STATS_QUERY_BUDGET_MS",
    default=250,
    min_value=10,
    max_value=60_000,
) / 1000


class StatsReadRepository:
    """Build dashboard data from a single, transactionally consistent snapshot."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def _path(self) -> str:
        return config.DATABASE_PATH if self._db_path is None else self._db_path

    @staticmethod
    async def _timed(query: str, operation):
        started = time.perf_counter()
        try:
            return await operation
        finally:
            runtime_state.record_stats_query(
                query,
                time.perf_counter() - started,
                budget_seconds=QUERY_BUDGET_SECONDS,
            )

    async def dashboard(self, scope: StatsScope) -> dict:
        """Return every local dashboard section from one SQLite read snapshot."""

        query_scope = scope.query_kwargs()
        path = self._path()
        async with read_snapshot(path):
            summary = await self._timed(
                "summary", get_summary(db_path=path, **query_scope)
            )
            players = await self._timed(
                "players", get_player_stats(db_path=path, **query_scope)
            )
            transcoding = await self._timed(
                "transcoding", get_transcoding_stats(db_path=path, **query_scope)
            )
            time_buckets = await self._timed(
                "time_buckets", get_time_bucket_stats(db_path=path, **query_scope)
            )
            history = await self._timed(
                "history",
                get_playback_history(
                    limit=HISTORY_LIMIT_DEFAULT,
                    db_path=path,
                    **query_scope,
                ),
            )
            servers = await self._timed(
                "servers", get_server_stats(db_path=path, **query_scope)
            )
            available_servers = await self._timed(
                "available_servers", list_server_options(db_path=path)
            )
            top_artists = await self._timed(
                "top_artists",
                get_top_artists(
                    artist_mode=scope.artist_mode,
                    limit=TOP_LIMIT_DEFAULT,
                    metric=scope.metric,
                    db_path=path,
                    **query_scope,
                ),
            )
            top_albums = await self._timed(
                "top_albums",
                get_top_albums(
                    limit=TOP_LIMIT_DEFAULT,
                    metric=scope.metric,
                    db_path=path,
                    **query_scope,
                ),
            )

        return {
            "summary": summary,
            "players": players,
            "transcoding": transcoding,
            "time_buckets": time_buckets,
            "history": history,
            "servers": servers,
            "available_servers": available_servers,
            "top_artists": top_artists,
            "top_albums": top_albums,
        }

    async def entity_detail(
        self,
        scope: StatsScope,
        identity: EntityIdentity,
    ) -> dict:
        """Return one entity drill-down from a consistent SQLite snapshot."""
        path = self._path()
        async with read_snapshot(path):
            return await self._timed(
                "entity_detail",
                get_entity_detail(scope, identity, db_path=path),
            )

    async def data_relations(
        self,
        scope: StatsScope,
        dimension: RelationDimension,
    ) -> dict:
        """Return cross-dimensional chart data from one SQLite snapshot."""
        path = self._path()
        async with read_snapshot(path):
            return await self._timed(
                "data_relations",
                get_data_relations(scope, dimension, db_path=path),
            )


stats_read_repository = StatsReadRepository()
