"""Recent playback history aggregation."""

from datetime import date

import aiosqlite

from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.windows import (
    TIMEZONE_DEFAULT,
    _source_predicate,
    _username_predicate,
    _window_predicate,
)


async def get_playback_history(
    limit: int = 10,
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return recent tracks with aggregated play counts for the selected window."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            WITH aggregated AS (
                SELECT
                    username,
                    track_id,
                    COALESCE(source_id, ?) AS source_id,
                    COUNT(*) AS play_count,
                    SUM(COALESCE(listen_duration_sec, 0)) AS total_listen_sec,
                    MAX(played_at_epoch) AS latest_played_at_epoch
                FROM play_history
                WHERE {pred}
                GROUP BY COALESCE(source_id, ?), username, track_id
            ), latest AS (
                SELECT aggregated.*, MAX(ph.id) AS latest_id
                FROM aggregated
                JOIN play_history ph
                  ON COALESCE(ph.source_id, ?) = aggregated.source_id
                 AND ph.username IS aggregated.username
                 AND ph.track_id IS aggregated.track_id
                 AND ph.played_at_epoch IS aggregated.latest_played_at_epoch
                GROUP BY aggregated.source_id, aggregated.username, aggregated.track_id
            )
            SELECT
                ph.username,
                ph.title,
                ph.artist,
                ph.album,
                ph.played_at AS last_played_at,
                COALESCE(ph.source_id, ?) AS source_id,
                COALESCE(ph.source_name, ?) AS source_name,
                latest.play_count,
                latest.total_listen_sec
            FROM latest
            JOIN play_history ph ON ph.id = latest.latest_id
            ORDER BY ph.played_at_epoch DESC, latest.play_count DESC
            LIMIT ?
            """,
            [
                LEGACY_SOURCE_ID,
                *params,
                LEGACY_SOURCE_ID,
                LEGACY_SOURCE_ID,
                LEGACY_SOURCE_ID,
                LEGACY_SOURCE_NAME,
                limit,
            ],
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
