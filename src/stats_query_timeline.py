"""Hourly, daily, and weekday/hour statistics from one history scan."""

from datetime import date, timedelta

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
        async with db.execute(
            f"SELECT played_at FROM play_history WHERE {pred}",
            params,
        ) as cursor:
            async for row in cursor:
                local = _played_at_to_local_datetime(row[0], tz)
                if local is None:
                    continue
                hourly_counts[local.hour] = hourly_counts.get(local.hour, 0) + 1
                local_date = local.date()
                daily_counts[local_date] = daily_counts.get(local_date, 0) + 1
                heatmap_counts[(local.weekday(), local.hour)] += 1

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
