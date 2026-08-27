"""Year-in-review aggregation queries.

Window predicates come from :mod:`src.windows`; top lists reuse the ranking
queries in :mod:`src.stats_queries` so review and dashboard rankings share
one metric implementation.
"""

from datetime import date, datetime

import aiosqlite

from src import config
from src.sqlite import connect_db
from src.stats_queries import get_top_albums, get_top_artists
from src.windows import (
    TIMEZONE_DEFAULT,
    _played_at_to_local_datetime,
    _source_predicate,
    _window_predicate,
    resolve_timezone,
)


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


async def get_review_summary(
    year: int,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
):
    """Aggregate one local calendar year for the review page.

    Hour, weekday, and active-day buckets come from one scan so DST-local
    bucketing matches the rest of the dashboard; top lists use grouped
    queries over the same window.
    """
    tz = resolve_timezone(timezone_name)
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    pred, params = _window_predicate(0, timezone_name, start, end)
    pred, params = _source_predicate(pred, params, source_id)

    path = _path(db_path)
    hourly_counts = [0] * 24
    hourly_listen_sec = [0] * 24
    weekday_counts = [0] * 7
    weekday_listen_sec = [0] * 7
    monthly_counts = [0] * 12
    monthly_listen_sec = [0] * 12
    active_dates: set[date] = set()
    total_plays = 0
    total_listen_sec = 0
    unique_tracks: set[str] = set()
    first_local: datetime | None = None
    last_local: datetime | None = None

    async with connect_db(path) as db:
        async with db.execute(
            f"""
            SELECT played_at, COALESCE(listen_duration_sec, 0) AS listen_sec,
                   COALESCE(source_id, 'legacy') || char(31) || COALESCE(track_id, '') AS track_key
            FROM play_history
            WHERE {pred}
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

    for played_at, listen_sec, track_key in rows:
        local = _played_at_to_local_datetime(played_at, tz)
        if local is None:
            continue
        seconds = int(listen_sec or 0)
        total_plays += 1
        total_listen_sec += seconds
        unique_tracks.add(track_key)
        hourly_counts[local.hour] += 1
        hourly_listen_sec[local.hour] += seconds
        weekday_counts[local.weekday()] += 1
        weekday_listen_sec[local.weekday()] += seconds
        monthly_counts[local.month - 1] += 1
        monthly_listen_sec[local.month - 1] += seconds
        active_dates.add(local.date())
        if first_local is None or local < first_local:
            first_local = local
        if last_local is None or local > last_local:
            last_local = local

    longest_streak = 0
    current_streak = 0
    previous_date: date | None = None
    for active_date in sorted(active_dates):
        if previous_date is not None and (active_date - previous_date).days == 1:
            current_streak += 1
        else:
            current_streak = 1
        longest_streak = max(longest_streak, current_streak)
        previous_date = active_date

    raw_artists = await get_top_artists(
        limit=10, days=0, timezone_name=timezone_name,
        metric="plays", db_path=db_path, source_id=source_id,
        start_date=start, end_date=end,
    )
    top_artists = [{**entry, "name": entry.get("artist")} for entry in raw_artists]
    raw_albums = await get_top_albums(
        limit=10, days=0, timezone_name=timezone_name,
        metric="listen_time", db_path=db_path, source_id=source_id,
        start_date=start, end_date=end,
    )
    top_albums = [{**entry, "name": entry.get("album")} for entry in raw_albums]

    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT COALESCE(title, '') AS name,
                   COALESCE(source_id, 'legacy') || char(31) || COALESCE(track_id, '') AS track_key,
                   COUNT(*) AS count,
                   COALESCE(SUM(COALESCE(listen_duration_sec, 0)), 0) AS value
            FROM play_history
            WHERE {pred}
            GROUP BY track_key
            ORDER BY count DESC, value DESC, name ASC
            LIMIT 10
            """,
            params,
        ) as cursor:
            track_rows = await cursor.fetchall()

    top_tracks = [
        {
            "name": row["name"] or "-",
            "source_id": row["track_key"].split("\x1f", 1)[0],
            "track_id": row["track_key"].split("\x1f", 1)[1] if "\x1f" in row["track_key"] else "",
            "count": int(row["count"] or 0),
            "total_listen_sec": int(row["value"] or 0),
            "value": int(row["value"] or 0),
        }
        for row in track_rows
    ]

    biggest_month = None
    if total_plays:
        peak = max(monthly_counts)
        if peak > 0:
            biggest_month = f"{year:04d}-{monthly_counts.index(peak) + 1:02d}"

    return {
        "year": year,
        "total_plays": total_plays,
        "total_listen_sec": total_listen_sec,
        "unique_tracks": len(unique_tracks),
        "active_days": len(active_dates),
        "longest_streak_days": longest_streak,
        "first_played_at": first_local.isoformat() if first_local else None,
        "last_played_at": last_local.isoformat() if last_local else None,
        "biggest_month": biggest_month,
        "monthly": [
            {
                "month": f"{year:04d}-{month:02d}",
                "count": monthly_counts[month - 1],
                "total_listen_sec": monthly_listen_sec[month - 1],
            }
            for month in range(1, 13)
        ],
        "hourly": [
            {
                "hour": hour,
                "count": hourly_counts[hour],
                "total_listen_sec": hourly_listen_sec[hour],
            }
            for hour in range(24)
        ],
        "weekday": [
            {
                "weekday": weekday,
                "count": weekday_counts[weekday],
                "total_listen_sec": weekday_listen_sec[weekday],
            }
            for weekday in range(7)
        ],
        "top_artists": top_artists,
        "top_albums": top_albums,
        "top_tracks": top_tracks,
    }
