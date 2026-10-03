"""Hourly, daily, and weekday/hour statistics from one history scan."""

from datetime import date, datetime, timedelta, timezone

from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.windows import (
    TIMEZONE_DEFAULT,
    _local_date_range,
    _played_at_to_local_datetime,
    _source_predicate,
    _username_predicate,
    _window_predicate,
    resolve_timezone,
)


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
    hourly_counts: dict[int, int] = {}
    daily_counts: dict[date, int] = {}
    heatmap_counts = {
        (weekday, hour): 0
        for weekday in range(WEEKDAY_HOUR_WEEKDAY_COUNT)
        for hour in range(WEEKDAY_HOUR_HOUR_COUNT)
    }
    async with connect_db(path) as db:
        # In UTC an hour is an exact calendar bucket. Aggregate before moving
        # rows across threads; other zones retain precise per-instant conversion
        # (half-hour offsets and DST can split a UTC hour).
        grouped_utc = timezone_name == "UTC"
        utc_hour = "played_at_epoch - ((played_at_epoch % 3600 + 3600) % 3600)"
        query = (
            f"SELECT {utc_hour} AS utc_hour, NULL, COUNT(*) FROM play_history "
            f"WHERE {pred} AND played_at_epoch IS NOT NULL GROUP BY utc_hour "
            "UNION ALL SELECT NULL, played_at, 1 FROM play_history "
            f"WHERE {pred} AND played_at_epoch IS NULL"
            if grouped_utc else f"SELECT NULL, played_at, 1 FROM play_history WHERE {pred}"
        )
        async with db.execute(query, params * 2 if grouped_utc else params) as cursor:
            async for row in cursor:
                # Older timestamps can be parseable by Python but not SQLite
                # (for example a compact +0000 offset). Keep their fallback.
                try:
                    local = (
                        datetime.fromtimestamp(row[0], timezone.utc)
                        if row[0] is not None else _played_at_to_local_datetime(row[1], tz)
                    )
                except (OSError, OverflowError, ValueError):
                    continue
                if local is None:
                    continue
                count = row[2]
                hourly_counts[local.hour] = hourly_counts.get(local.hour, 0) + count
                local_date = local.date()
                daily_counts[local_date] = daily_counts.get(local_date, 0) + count
                heatmap_counts[(local.weekday(), local.hour)] += count

    hourly = [{"hour": hour, "count": hourly_counts[hour]} for hour in sorted(hourly_counts)]
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
        daily.append({"date": cursor_date.isoformat(), "count": daily_counts.get(cursor_date, 0)})
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
