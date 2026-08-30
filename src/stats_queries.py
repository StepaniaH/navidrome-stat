"""Statistics read queries over play history.

Window predicates come from :mod:`src.windows`; every query stays
parameterized and timezone names never enter SQL strings.
"""

from datetime import date, timedelta

import aiosqlite

from src import config
from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.windows import (
    TIMEZONE_DEFAULT,
    _local_date_range,
    _played_at_to_local_date,
    _played_at_to_local_datetime,
    _previous_window_predicate,
    _source_predicate,
    _username_predicate,
    _window_predicate,
    resolve_timezone,
)


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


async def list_usernames(db_path: str | None = None) -> list[str]:
    """Return usernames seen in play history, case-insensitively ordered."""
    path = _path(db_path)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT DISTINCT username FROM play_history "
            "WHERE username IS NOT NULL AND username != '' "
            "ORDER BY username COLLATE NOCASE"
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def get_earliest_poller_played_at(
    source_id: str,
    username: str,
    db_path: str | None = None,
) -> str | None:
    """Return the oldest live-poller play instant for an importer cutoff."""
    path = _path(db_path)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT MIN(played_at) FROM play_history "
            "WHERE source = 'poller' AND source_id = ? AND username = ?",
            (source_id, username),
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def get_short_play_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Return short-play counts and rate; this is not a skip-rate claim."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT COUNT(*) AS short_count, COALESCE(SUM(duration_sec), 0) AS short_listen_sec
            FROM play_attempts WHERE {pred} AND outcome = 'short_play'
        """, params) as cursor:
            short = await cursor.fetchone()
        async with db.execute(f"""
            SELECT COUNT(*) AS counted_count FROM play_history WHERE {pred}
        """, params) as cursor:
            counted = await cursor.fetchone()
    short_count = int(short["short_count"] or 0)
    counted_count = int(counted["counted_count"] or 0)
    attempt_count = short_count + counted_count
    return {
        "short_count": short_count,
        "counted_count": counted_count,
        "attempt_count": attempt_count,
        "short_listen_sec": int(short["short_listen_sec"] or 0),
        "short_play_rate_pct": round(short_count / attempt_count * 100, 2) if attempt_count else 0.0,
    }


async def get_source_stats(days: int = 0, timezone_name: str = TIMEZONE_DEFAULT,
                           db_path: str | None = None,
                           source_id: str | None = None,
                           username: str | None = None):
    """Return play counts grouped by provenance."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT COALESCE(source, 'poller') AS source,
                   COUNT(*) AS count,
                   COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec
            FROM play_history WHERE {pred}
            GROUP BY COALESCE(source, 'poller')
            ORDER BY count DESC, source ASC
        """, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_server_stats(days: int = 0, timezone_name: str = TIMEZONE_DEFAULT,
                           source_id: str | None = None, db_path: str | None = None,
                           start_date: date | None = None,
                           end_date: date | None = None,
                           username: str | None = None):
    """Return play counts grouped by configured server."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    where, params = _source_predicate(pred, params, source_id, column="ph.source_id")
    where, params = _username_predicate(where, params, username, column="ph.username")
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT COALESCE(ph.source_id, ?) AS source_id,
                   COALESCE(s.display_name, MAX(ph.source_name), ?) AS source_name,
                   COUNT(*) AS count,
                   COALESCE(SUM(ph.listen_duration_sec), 0) AS total_listen_sec
            FROM play_history ph
            LEFT JOIN servers s ON s.id = ph.source_id
            WHERE {where}
            GROUP BY COALESCE(ph.source_id, ?)
            ORDER BY count DESC, source_name ASC
        """, [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params,
               LEGACY_SOURCE_ID]) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_player_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return client play and listening aggregates for the selected window.

    Results sort by play count and client name. Window bounds follow the
    requested local calendar; timezone names are never interpolated into SQL.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                client_name,
                COUNT(*) AS count,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec,
                COALESCE(SUM(CASE WHEN is_transcoding = 1 THEN 1 ELSE 0 END), 0) AS transcoded_count
            FROM play_history
            WHERE {pred}
            GROUP BY client_name
            ORDER BY count DESC, COALESCE(client_name, '') ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

    out: list[dict] = []
    for row in rows:
        count = int(row["count"] or 0)
        total_listen_sec = int(row["total_listen_sec"] or 0)
        transcoded_count = int(row["transcoded_count"] or 0)
        average_listen_sec = round(total_listen_sec / count, 2) if count > 0 else 0.0
        transcoding_rate_pct = (
            round((transcoded_count / count) * 100, 2) if count > 0 else 0.0
        )
        out.append({
            "client_name": row["client_name"],
            "count": count,
            "total_listen_sec": total_listen_sec,
            "average_listen_sec": average_listen_sec,
            "transcoded_count": transcoded_count,
            "transcoding_rate_pct": transcoding_rate_pct,
        })
    return out


async def get_transcoding_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return play and listen-time aggregates by transcoding mode.

    Percentages are rounded to two decimals and use zero for empty totals.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                is_transcoding,
                COUNT(*) AS count,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec
            FROM play_history
            WHERE {pred}
            GROUP BY is_transcoding
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

    total_plays = sum(int(r["count"] or 0) for r in rows)
    total_listen_sec_all = sum(int(r["total_listen_sec"] or 0) for r in rows)
    out: list[dict] = []
    for row in rows:
        count = int(row["count"] or 0)
        total_listen_sec = int(row["total_listen_sec"] or 0)
        plays_pct = round((count / total_plays) * 100, 2) if total_plays > 0 else 0.0
        listen_sec_pct = (
            round((total_listen_sec / total_listen_sec_all) * 100, 2)
            if total_listen_sec_all > 0
            else 0.0
        )
        out.append({
            "is_transcoding": row["is_transcoding"],
            "count": count,
            "total_listen_sec": total_listen_sec,
            "plays_pct": plays_pct,
            "listen_sec_pct": listen_sec_pct,
        })
    return out


async def get_summary(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return listening aggregates and previous-window comparisons.

    Finite-window daily averages divide by active days; all-history averages
    divide by the inclusive date span. All history omits comparisons, and
    percentage changes are null when the previous total is zero.
    """
    path = _path(db_path)
    tz = resolve_timezone(timezone_name)
    cur_pred, cur_params = _window_predicate(
        days,
        timezone_name,
        start_date,
        end_date,
    )
    cur_pred, cur_params = _source_predicate(cur_pred, cur_params, source_id)
    cur_pred, cur_params = _username_predicate(cur_pred, cur_params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                COUNT(*) AS total_plays,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec,
                COUNT(DISTINCT (
                    COALESCE(source_id, 'legacy') || char(31) ||
                    COALESCE(track_id, '')
                )) AS unique_tracks,
                COUNT(DISTINCT client_name) AS client_count
            FROM play_history
            WHERE {cur_pred}
            """,
            cur_params,
        ) as cursor:
            row = await cursor.fetchone()

        async with db.execute(
            f"""
            SELECT played_at AS played_at
            FROM play_history
            WHERE {cur_pred}
            """,
            cur_params,
        ) as cursor:
            cur_rows = await cursor.fetchall()

        total_plays = int(row["total_plays"] or 0)
        total_listen_sec = int(row["total_listen_sec"] or 0)
        unique_tracks = int(row["unique_tracks"] or 0)
        client_count = int(row["client_count"] or 0)

        local_dates: set[date] = set()
        for r in cur_rows:
            local = _played_at_to_local_date(r["played_at"], tz)
            if local is not None:
                local_dates.add(local)
        active_days = len(local_dates)

        previous_total_plays: int | None = None
        previous_total_listen_sec: int | None = None
        plays_change_pct: float | None = None
        listen_change_pct: float | None = None
        avg_daily_plays: float | None
        avg_daily_listen_sec: float | None

        is_custom_window = start_date is not None and end_date is not None
        if days <= 0 and not is_custom_window:
            denom: int | None = None
            if local_dates:
                span_days = (max(local_dates) - min(local_dates)).days + 1
                if span_days > 0:
                    denom = span_days
            if denom and denom > 0:
                avg_daily_plays = round(total_plays / denom, 2)
                avg_daily_listen_sec = round(total_listen_sec / denom, 2)
            else:
                avg_daily_plays = 0.0 if total_plays == 0 else None
                avg_daily_listen_sec = 0.0 if total_listen_sec == 0 else None
        else:
            avg_daily_plays = round(total_plays / active_days, 2) if active_days > 0 else 0.0
            avg_daily_listen_sec = (
                round(total_listen_sec / active_days, 2) if active_days > 0 else 0.0
            )
            prev_pred, prev_params = _previous_window_predicate(
                days,
                timezone_name,
                start_date,
                end_date,
            )
            prev_pred, prev_params = _source_predicate(
                prev_pred, prev_params, source_id
            )
            prev_pred, prev_params = _username_predicate(
                prev_pred, prev_params, username
            )
            async with db.execute(
                f"""
                SELECT
                    COUNT(*) AS p_plays,
                    COALESCE(SUM(listen_duration_sec), 0) AS p_listen_sec
                FROM play_history
                WHERE {prev_pred}
                """,
                prev_params,
            ) as cursor:
                prow = await cursor.fetchone()
            previous_total_plays = int(prow["p_plays"] or 0)
            previous_total_listen_sec = int(prow["p_listen_sec"] or 0)
            if previous_total_plays:
                plays_change_pct = round(
                    (total_plays - previous_total_plays) / previous_total_plays * 100, 2
                )
            if previous_total_listen_sec:
                listen_change_pct = round(
                    (total_listen_sec - previous_total_listen_sec)
                    / previous_total_listen_sec
                    * 100,
                    2,
                )

        return {
            "total_plays": total_plays,
            "total_listen_sec": total_listen_sec,
            "unique_tracks": unique_tracks,
            "client_count": client_count,
            "active_days": active_days,
            "average_daily_plays": avg_daily_plays,
            "average_daily_listen_sec": avg_daily_listen_sec,
            "previous_total_plays": previous_total_plays,
            "previous_total_listen_sec": previous_total_listen_sec,
            "plays_change_pct": plays_change_pct,
            "listen_change_pct": listen_change_pct,
            "window_days": (
                (end_date - start_date).days + 1
                if is_custom_window
                else (days if days > 0 else None)
            ),
        }


async def get_hourly_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
):
    """Return non-empty local-hour buckets in ascending order.

    Stored timestamps remain UTC; timezone conversion controls window and
    bucket boundaries.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
        username=username,
    )
    return buckets["hourly"]


async def get_time_bucket_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
) -> dict[str, list[dict]]:
    """Build hourly, daily and weekday/hour buckets from one SQLite scan."""

    path = _path(db_path)
    tz = resolve_timezone(timezone_name)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        async with db.execute(
            f"SELECT played_at FROM play_history WHERE {pred}",
            params,
        ) as cursor:
            played_at_values = [row[0] for row in await cursor.fetchall()]

    hourly_counts: dict[int, int] = {}
    daily_counts: dict[date, int] = {}
    heatmap_counts = {
        (weekday, hour): 0
        for weekday in range(WEEKDAY_HOUR_WEEKDAY_COUNT)
        for hour in range(WEEKDAY_HOUR_HOUR_COUNT)
    }
    for played_at in played_at_values:
        local = _played_at_to_local_datetime(played_at, tz)
        if local is None:
            continue
        hourly_counts[local.hour] = hourly_counts.get(local.hour, 0) + 1
        local_date = local.date()
        daily_counts[local_date] = daily_counts.get(local_date, 0) + 1
        heatmap_counts[(local.weekday(), local.hour)] += 1

    hourly = [
        {"hour": hour, "count": hourly_counts[hour]}
        for hour in sorted(hourly_counts)
    ]
    if days <= 0 and (start_date is None or end_date is None):
        if daily_counts:
            start_date, end_date = min(daily_counts), max(daily_counts)
        else:
            start_date = end_date = None
    else:
        start_date, end_date = _local_date_range(
            days,
            tz,
            start_date,
            end_date,
        )
    daily = []
    cursor_date = start_date
    while cursor_date is not None and end_date is not None and cursor_date <= end_date:
        daily.append(
            {"date": cursor_date.isoformat(), "count": daily_counts.get(cursor_date, 0)}
        )
        cursor_date += timedelta(days=1)
    heatmap = [
        {"weekday": weekday, "hour": hour, "count": heatmap_counts[(weekday, hour)]}
        for weekday in range(WEEKDAY_HOUR_WEEKDAY_COUNT)
        for hour in range(WEEKDAY_HOUR_HOUR_COUNT)
    ]
    return {"hourly": hourly, "daily": daily, "heatmap": heatmap}


WEEKDAY_HOUR_WEEKDAY_COUNT = 7


WEEKDAY_HOUR_HOUR_COUNT = 24


WEEKDAY_HOUR_CELL_COUNT = WEEKDAY_HOUR_WEEKDAY_COUNT * WEEKDAY_HOUR_HOUR_COUNT


async def get_daily_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
):
    """Return zero-filled local-date buckets in ascending order.

    Finite windows cover every requested date; all history spans the earliest
    through latest play. Bucketing converts stored UTC timestamps to local time.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
        username=username,
    )
    return buckets["daily"]


async def get_weekday_hour_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
):
    """Return a zero-filled 7 by 24 local weekday/hour grid.

    Weekdays follow ``date.weekday()`` (Monday=0); stored UTC timestamps are
    converted to the requested timezone before bucketing.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
        username=username,
    )
    return buckets["heatmap"]


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
                    MAX(played_at) AS latest_played_at
                FROM album_rows
                GROUP BY normalized_source_id, album_key
            ), latest AS (
                SELECT aggregated.*, MAX(album_rows.id) AS latest_id
                FROM aggregated
                JOIN album_rows
                  ON album_rows.normalized_source_id = aggregated.normalized_source_id
                 AND album_rows.album_key = aggregated.album_key
                 AND album_rows.played_at IS aggregated.latest_played_at
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
        id_expr = (
            f"MAX(NULLIF({entity_id_column}, '')) AS entity_id, "
        )
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
                    MAX(played_at) AS latest_played_at
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
                 AND ph.played_at IS aggregated.latest_played_at
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
            ORDER BY ph.played_at DESC, latest.play_count DESC
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
