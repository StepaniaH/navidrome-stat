"""Calendar-year and calendar-month listening review queries.

Window predicates come from :mod:`src.windows`; top lists reuse the ranking
queries in :mod:`src.stats_queries` so review and dashboard rankings share
one metric implementation.
"""

from calendar import monthrange
from datetime import date, datetime, timedelta

import aiosqlite

from src import config
from src.core_types import (
    DurationQuality,
    classify_history_duration_quality,
    combine_duration_qualities,
)
from src.sqlite import connect_db
from src.stats_queries import get_top_albums, get_top_artists
from src.windows import (
    TIMEZONE_DEFAULT,
    _played_at_to_local_datetime,
    _source_predicate,
    _username_predicate,
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
    username: str | None = None,
    artist_mode: str = "combined",
    month: int | None = None,
):
    """Aggregate one local calendar year or month for the review page.

    Hour, weekday, and active-day buckets come from one scan so DST-local
    bucketing matches the rest of the dashboard; top lists use grouped
    queries over the same window.
    """
    tz = resolve_timezone(timezone_name)
    if month is not None and not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    if month is None:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        previous_start = date(year - 1, 1, 1)
        previous_end = date(year - 1, 12, 31)
    else:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        previous_end = start - timedelta(days=1)
        previous_start = date(previous_end.year, previous_end.month, 1)
    _, window_params = _window_predicate(0, timezone_name, start, end)
    pred, params = _window_predicate(0, timezone_name, start, end)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)

    path = _path(db_path)
    hourly_counts = [0] * 24
    hourly_listen_sec = [0] * 24
    weekday_counts = [0] * 7
    weekday_listen_sec = [0] * 7
    monthly_counts = [0] * 12
    monthly_listen_sec = [0] * 12
    daily_counts: dict[date, int] = {}
    daily_listen_sec: dict[date, int] = {}
    active_dates: set[date] = set()
    total_plays = 0
    total_listen_sec = 0
    duration_quality_counts: dict[DurationQuality, int] = {
        "reported": 0,
        "estimated": 0,
        "lower_bound": 0,
        "unknown": 0,
    }
    play_source_counts: dict[str, int] = {}
    unique_tracks: set[str] = set()
    first_local: datetime | None = None
    last_local: datetime | None = None

    async with connect_db(path) as db:
        async with db.execute(
            f"""
            SELECT played_at, listen_duration_sec,
                   COALESCE(source, 'poller') AS source,
                   session_id,
                   COALESCE(finalized, 1) AS finalized,
                   COALESCE(duration_confidence, 'estimated') AS duration_confidence,
                   COALESCE(source_id, 'legacy') || char(31) || COALESCE(track_id, '') AS track_key
            FROM play_history
            WHERE {pred}
            """,
            params,
        ) as cursor:
            async for (
                played_at,
                listen_sec,
                play_source,
                session_id,
                finalized,
                duration_confidence,
                track_key,
            ) in cursor:
                local = _played_at_to_local_datetime(played_at, tz)
                if local is None:
                    continue
                seconds = int(listen_sec or 0)
                quality = classify_history_duration_quality(
                    listen_duration_sec=listen_sec,
                    source=play_source,
                    session_id=session_id,
                    finalized=finalized,
                    duration_confidence=duration_confidence,
                )
                total_plays += 1
                total_listen_sec += seconds
                duration_quality_counts[quality] += 1
                source_key = str(play_source or "poller")
                play_source_counts[source_key] = play_source_counts.get(source_key, 0) + 1
                unique_tracks.add(track_key)
                hourly_counts[local.hour] += 1
                hourly_listen_sec[local.hour] += seconds
                weekday_counts[local.weekday()] += 1
                weekday_listen_sec[local.weekday()] += seconds
                monthly_counts[local.month - 1] += 1
                monthly_listen_sec[local.month - 1] += seconds
                daily_counts[local.date()] = daily_counts.get(local.date(), 0) + 1
                daily_listen_sec[local.date()] = (
                    daily_listen_sec.get(local.date(), 0) + seconds
                )
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
        artist_mode=artist_mode,
        limit=10,
        days=0,
        timezone_name=timezone_name,
        metric="plays",
        db_path=db_path,
        source_id=source_id,
        username=username,
        start_date=start,
        end_date=end,
    )
    top_artists = [{**entry, "name": entry.get("artist")} for entry in raw_artists]
    raw_albums = await get_top_albums(
        limit=10,
        days=0,
        timezone_name=timezone_name,
        metric="listen_time",
        db_path=db_path,
        source_id=source_id,
        username=username,
        start_date=start,
        end_date=end,
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

    previous_pred, previous_params = _window_predicate(
        0,
        timezone_name,
        previous_start,
        previous_end,
    )
    previous_pred, previous_params = _source_predicate(
        previous_pred,
        previous_params,
        source_id,
    )
    previous_pred, previous_params = _username_predicate(
        previous_pred,
        previous_params,
        username,
    )
    identity_pred, identity_params = _source_predicate("1=1", [], source_id)
    identity_pred, identity_params = _username_predicate(
        identity_pred,
        identity_params,
        username,
    )
    async with connect_db(path) as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM play_history WHERE {previous_pred}",
            previous_params,
        ) as cursor:
            previous_total_plays = int((await cursor.fetchone())[0] or 0)
        async with db.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT COALESCE(source_id, 'legacy') || char(31) || COALESCE(track_id, '')
                FROM play_history
                WHERE ({identity_pred}) AND played_at_epoch IS NOT NULL
                GROUP BY COALESCE(source_id, 'legacy'), track_id
                HAVING MIN(played_at_epoch) >= ? AND MIN(played_at_epoch) < ?
            )
            """,
            [*identity_params, *window_params],
        ) as cursor:
            first_recorded_tracks = int((await cursor.fetchone())[0] or 0)

    biggest_month = None
    if total_plays:
        peak = max(monthly_counts)
        if peak > 0:
            biggest_month = f"{year:04d}-{monthly_counts.index(peak) + 1:02d}"

    duration_count = total_plays - duration_quality_counts["unknown"]
    duration_coverage_pct = (
        round(duration_count / total_plays * 100, 2) if total_plays else 0.0
    )
    duration_quality = combine_duration_qualities(
        quality
        for quality, count in duration_quality_counts.items()
        if count > 0
    )

    return {
        "period": "month" if month is not None else "year",
        "year": year,
        "month": month,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "timezone": timezone_name,
        "source_id": source_id,
        "username": username,
        "total_plays": total_plays,
        "previous_total_plays": previous_total_plays,
        "plays_change_pct": (
            round((total_plays - previous_total_plays) / previous_total_plays * 100, 1)
            if previous_total_plays
            else None
        ),
        "total_listen_sec": total_listen_sec,
        "duration_quality": duration_quality,
        "duration_coverage_pct": duration_coverage_pct,
        "duration_quality_counts": duration_quality_counts,
        "play_source_counts": play_source_counts,
        "unique_tracks": len(unique_tracks),
        "first_recorded_tracks": first_recorded_tracks,
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
        "daily": [] if month is None else [
            {
                "date": cursor_date.isoformat(),
                "count": daily_counts.get(cursor_date, 0),
                "total_listen_sec": daily_listen_sec.get(cursor_date, 0),
            }
            for day_offset in range((end - start).days + 1)
            for cursor_date in (start + timedelta(days=day_offset),)
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
