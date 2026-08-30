"""Artist and album ranking statistics."""

from datetime import date

import aiosqlite

from src.schema import LEGACY_SOURCE_ID
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.windows import (
    TIMEZONE_DEFAULT,
    _source_predicate,
    _username_predicate,
    _window_predicate,
)


async def get_top_artists(
    limit: int = 10,
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    metric: str = "plays",
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return artists ranked by plays or listen time for the selected window.

    ``value`` contains the selected metric; ties sort by artist name. Metric
    values map to fixed SQL expressions and timezone bounds stay parameterized.
    """
    return await _get_top_entity(
        entity_column="artist",
        entity_id_column="artist_id",
        limit=limit,
        days=days,
        timezone_name=timezone_name,
        metric=metric,
        db_path=db_path,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
        username=username,
    )


async def get_top_albums(
    limit: int = 10,
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    metric: str = "plays",
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return albums ranked by plays or listen time for the selected window."""
    if metric not in ("plays", "listen_time"):
        raise ValueError(f"unknown ranking metric: {metric!r}")

    value_column = "play_count" if metric == "plays" else "total_listen_sec"
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            WITH album_rows AS (
                SELECT
                    id,
                    played_at,
                    played_at_epoch,
                    album,
                    artist,
                    NULLIF(album_id, '') AS album_id,
                    COALESCE(source_id, ?) AS normalized_source_id,
                    CASE
                        WHEN NULLIF(album_id, '') IS NOT NULL
                            THEN 'id:' || album_id
                        ELSE 'legacy:' || album || char(31) || COALESCE(artist, '')
                    END AS album_key,
                    COALESCE(listen_duration_sec, 0) AS listen_duration_sec
                FROM play_history
                WHERE album IS NOT NULL AND album != '' AND ({pred})
            ), aggregated AS (
                SELECT
                    normalized_source_id,
                    album_key,
                    COUNT(*) AS play_count,
                    SUM(listen_duration_sec) AS total_listen_sec,
                    MAX(played_at_epoch) AS latest_played_at_epoch
                FROM album_rows
                GROUP BY normalized_source_id, album_key
            ), latest AS (
                SELECT aggregated.*, MAX(album_rows.id) AS latest_id
                FROM aggregated
                JOIN album_rows
                  ON album_rows.normalized_source_id = aggregated.normalized_source_id
                 AND album_rows.album_key = aggregated.album_key
                 AND album_rows.played_at_epoch IS aggregated.latest_played_at_epoch
                GROUP BY aggregated.normalized_source_id, aggregated.album_key
            )
            SELECT
                album_rows.album,
                album_rows.artist,
                album_rows.album_id,
                latest.normalized_source_id AS source_id,
                latest.play_count AS count,
                latest.total_listen_sec,
                latest.{value_column} AS value
            FROM latest
            JOIN album_rows ON album_rows.id = latest.latest_id
            ORDER BY value DESC, album ASC, artist ASC, source_id ASC
            LIMIT ?
            """,
            [LEGACY_SOURCE_ID, *params, limit],
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {
            "album": row["album"],
            "artist": row["artist"],
            "album_id": row["album_id"],
            "source_id": row["source_id"],
            "count": int(row["count"] or 0),
            "total_listen_sec": int(row["total_listen_sec"] or 0),
            "value": int(row["value"] or 0),
        }
        for row in rows
    ]


async def _get_top_entity(
    entity_column: str,
    limit: int,
    days: int,
    timezone_name: str,
    metric: str,
    db_path: str | None,
    source_id: str | None,
    start_date: date | None,
    end_date: date | None,
    username: str | None = None,
    entity_id_column: str | None = None,
):
    if metric not in ("plays", "listen_time"):
        raise ValueError(f"unknown ranking metric: {metric!r}")

    # SQLite cannot reuse a SELECT alias elsewhere in the same SELECT list.
    if metric == "plays":
        value_expr = "COUNT(*)"
    else:
        value_expr = "COALESCE(SUM(listen_duration_sec), 0)"

    # MAX over text picks one deterministic non-empty id per entity name;
    # NULLIF keeps blank identifiers from winning over real ones.
    if entity_id_column:
        id_expr = f"MAX(NULLIF({entity_id_column}, '')) AS entity_id, "
    else:
        id_expr = ""

    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                {entity_column} AS name,
                {id_expr}
                COUNT(*) AS count,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec,
                {value_expr} AS value
            FROM play_history
            WHERE {entity_column} IS NOT NULL AND {entity_column} != "" AND ({pred})
            GROUP BY {entity_column}
            ORDER BY value DESC, {entity_column} ASC
            LIMIT ?
            """,
            [*params, limit],
        ) as cursor:
            rows = await cursor.fetchall()

    out = []
    for row in rows:
        entry = {
            entity_column: row["name"],
            "count": int(row["count"] or 0),
            "total_listen_sec": int(row["total_listen_sec"] or 0),
            "value": int(row["value"] or 0),
        }
        if entity_id_column:
            entry[f"{entity_id_column}"] = row["entity_id"]
        out.append(entry)
    return out
