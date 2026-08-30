"""Consistent dashboard reads over one SQLite snapshot."""

from datetime import date

from src import config
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


class StatsReadRepository:
    """Build dashboard data from a single, transactionally consistent snapshot."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def _path(self) -> str:
        return config.DATABASE_PATH if self._db_path is None else self._db_path

    async def dashboard(
        self,
        *,
        days: int,
        timezone_name: str,
        metric: str,
        source_id: str | None,
        start_date: date | None,
        end_date: date | None,
        username: str | None = None,
    ) -> dict:
        """Return every local dashboard section from one SQLite read snapshot."""

        scope = {
            "days": days,
            "timezone_name": timezone_name,
            "source_id": source_id,
            "username": username,
            "start_date": start_date,
            "end_date": end_date,
        }
        path = self._path()
        async with read_snapshot(path):
            summary = await get_summary(db_path=path, **scope)
            players = await get_player_stats(db_path=path, **scope)
            transcoding = await get_transcoding_stats(db_path=path, **scope)
            time_buckets = await get_time_bucket_stats(db_path=path, **scope)
            history = await get_playback_history(
                limit=HISTORY_LIMIT_DEFAULT,
                db_path=path,
                **scope,
            )
            servers = await get_server_stats(db_path=path, **scope)
            available_servers = await list_server_options(db_path=path)
            top_artists = await get_top_artists(
                limit=TOP_LIMIT_DEFAULT,
                metric=metric,
                db_path=path,
                **scope,
            )
            top_albums = await get_top_albums(
                limit=TOP_LIMIT_DEFAULT,
                metric=metric,
                db_path=path,
                **scope,
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


stats_read_repository = StatsReadRepository()
