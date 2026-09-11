"""User, source, client, transcoding, and summary statistics."""

from datetime import date

import aiosqlite

from src.core_types import (
    DurationQuality,
    classify_history_duration_quality,
    combine_duration_qualities,
)
from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.windows import (
    TIMEZONE_DEFAULT,
    _played_at_to_local_date,
    _previous_window_predicate,
    _source_predicate,
    _username_predicate,
    _window_predicate,
    resolve_timezone,
)


async def list_usernames(
    db_path: str | None = None,
    source_id: str | None = None,
) -> list[str]:
    """Return usernames seen in play history, case-insensitively ordered."""
    path = _path(db_path)
    pred, params = _source_predicate("1=1", [], source_id)
    async with connect_db(path) as db:
        async with db.execute(
            "SELECT DISTINCT username FROM play_history "
            f"WHERE ({pred}) AND username IS NOT NULL AND username != '' "
            "ORDER BY username COLLATE NOCASE",
            params,
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
            "SELECT played_at FROM play_history "
            "WHERE source = 'poller' AND source_id = ? AND username = ? "
            "ORDER BY played_at_epoch ASC, id ASC LIMIT 1",
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
    """Return short-play counts among recorded attempts; this is not skip rate."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT COUNT(*) AS short_count, COALESCE(SUM(duration_sec), 0) AS short_listen_sec
            FROM play_attempts WHERE {pred} AND outcome = 'short_play'
        """,
            params,
        ) as cursor:
            short = await cursor.fetchone()
        async with db.execute(
            f"""
            SELECT COUNT(*) AS counted_count FROM play_history
            WHERE {pred} AND COALESCE(source, 'poller') IN ('poller', 'import')
        """,
            params,
        ) as cursor:
            counted = await cursor.fetchone()
    short_count = int(short["short_count"] or 0)
    counted_count = int(counted["counted_count"] or 0)
    attempt_count = short_count + counted_count
    return {
        "short_count": short_count,
        "counted_count": counted_count,
        "attempt_count": attempt_count,
        "short_listen_sec": int(short["short_listen_sec"] or 0),
        "short_play_rate_pct": round(short_count / attempt_count * 100, 2)
        if attempt_count
        else 0.0,
    }


async def get_source_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
):
    """Return play counts grouped by provenance."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name)
    pred, params = _source_predicate(pred, params, source_id)
    pred, params = _username_predicate(pred, params, username)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT COALESCE(source, 'poller') AS source,
                   COUNT(*) AS count,
                   COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec
            FROM play_history WHERE {pred}
            GROUP BY COALESCE(source, 'poller')
            ORDER BY count DESC, source ASC
        """,
            params,
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_server_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    source_id: str | None = None,
    db_path: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    username: str | None = None,
):
    """Return play counts grouped by configured server."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    where, params = _source_predicate(pred, params, source_id, column="ph.source_id")
    where, params = _username_predicate(where, params, username, column="ph.username")
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT COALESCE(ph.source_id, ?) AS source_id,
                   COALESCE(s.display_name, MAX(ph.source_name), ?) AS source_name,
                   COUNT(*) AS count,
                   COALESCE(SUM(ph.listen_duration_sec), 0) AS total_listen_sec
            FROM play_history ph
            LEFT JOIN servers s ON s.id = ph.source_id
            WHERE {where}
            GROUP BY COALESCE(ph.source_id, ?)
            ORDER BY count DESC, source_name ASC
        """,
            [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params, LEGACY_SOURCE_ID],
        ) as cursor:
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
                COALESCE(SUM(CASE WHEN is_transcoding = 1 THEN 1 ELSE 0 END), 0) AS transcoded_count,
                COALESCE(SUM(CASE WHEN is_transcoding IS NOT NULL THEN 1 ELSE 0 END), 0)
                    AS known_transcoding_count
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
        known_transcoding_count = int(row["known_transcoding_count"] or 0)
        average_listen_sec = round(total_listen_sec / count, 2) if count > 0 else 0.0
        transcoding_rate_pct = (
            round((transcoded_count / known_transcoding_count) * 100, 2)
            if known_transcoding_count > 0
            else None
        )
        out.append(
            {
                "client_name": row["client_name"],
                "count": count,
                "total_listen_sec": total_listen_sec,
                "average_listen_sec": average_listen_sec,
                "transcoded_count": transcoded_count,
                "transcoding_rate_pct": transcoding_rate_pct,
            }
        )
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
        out.append(
            {
                "is_transcoding": row["is_transcoding"],
                "count": count,
                "total_listen_sec": total_listen_sec,
                "plays_pct": plays_pct,
                "listen_sec_pct": listen_sec_pct,
            }
        )
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
    local_dates: set[date] = set()
    duration_quality_counts: dict[DurationQuality, int] = {
        "reported": 0,
        "estimated": 0,
        "lower_bound": 0,
        "unknown": 0,
    }
    play_source_counts: dict[str, int] = {}
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
            SELECT played_at,
                   listen_duration_sec,
                   COALESCE(source, 'poller') AS source,
                   session_id,
                   COALESCE(finalized, 1) AS finalized,
                   COALESCE(duration_confidence, 'estimated') AS duration_confidence
            FROM play_history
            WHERE {cur_pred}
            """,
            cur_params,
        ) as cursor:
            async for current in cursor:
                local = _played_at_to_local_date(current["played_at"], tz)
                if local is not None:
                    local_dates.add(local)
                quality = classify_history_duration_quality(
                    listen_duration_sec=current["listen_duration_sec"],
                    source=current["source"],
                    session_id=current["session_id"],
                    finalized=current["finalized"],
                    duration_confidence=current["duration_confidence"],
                )
                duration_quality_counts[quality] += 1
                play_source = str(current["source"] or "poller")
                play_source_counts[play_source] = (
                    play_source_counts.get(play_source, 0) + 1
                )

        total_plays = int(row["total_plays"] or 0)
        total_listen_sec = int(row["total_listen_sec"] or 0)
        unique_tracks = int(row["unique_tracks"] or 0)
        client_count = int(row["client_count"] or 0)
        duration_count = total_plays - duration_quality_counts["unknown"]
        duration_coverage_pct = (
            round(duration_count / total_plays * 100, 2) if total_plays else 0.0
        )
        duration_quality = combine_duration_qualities(
            quality
            for quality, count in duration_quality_counts.items()
            if count > 0
        )

        active_days = len(local_dates)

        previous_total_plays: int | None = None
        previous_total_listen_sec: int | None = None
        plays_change_pct: float | None = None
        listen_change_pct: float | None = None
        avg_daily_plays: float | None
        avg_daily_listen_sec: float | None
        previous_duration_quality: DurationQuality | None = None
        previous_duration_coverage_pct: float | None = None
        listen_change_reason = "all_history"

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
            prev_pred, prev_params = _source_predicate(prev_pred, prev_params, source_id)
            prev_pred, prev_params = _username_predicate(prev_pred, prev_params, username)
            async with db.execute(
                f"""
                SELECT
                    COUNT(*) AS p_plays,
                    COALESCE(SUM(listen_duration_sec), 0) AS p_listen_sec,
                    COUNT(listen_duration_sec) AS p_duration_count,
                    COALESCE(SUM(CASE
                        WHEN listen_duration_sec IS NOT NULL AND (
                            duration_confidence = 'lower_bound'
                            OR (
                                COALESCE(source, 'poller') = 'poller'
                                AND (session_id IS NULL OR COALESCE(finalized, 1) = 0)
                            )
                        ) THEN 1 ELSE 0 END), 0) AS p_lower_bound_count,
                    COALESCE(SUM(CASE
                        WHEN listen_duration_sec IS NOT NULL
                         AND COALESCE(source, 'poller') != 'poller'
                         AND duration_confidence = 'reported'
                        THEN 1 ELSE 0 END), 0) AS p_reported_count
                FROM play_history
                WHERE {prev_pred}
                """,
                prev_params,
            ) as cursor:
                prow = await cursor.fetchone()
            previous_total_plays = int(prow["p_plays"] or 0)
            previous_total_listen_sec = int(prow["p_listen_sec"] or 0)
            previous_duration_count = int(prow["p_duration_count"] or 0)
            previous_lower_bound_count = int(prow["p_lower_bound_count"] or 0)
            previous_reported_count = int(prow["p_reported_count"] or 0)
            previous_duration_coverage_pct = (
                round(previous_duration_count / previous_total_plays * 100, 2)
                if previous_total_plays
                else 0.0
            )
            previous_qualities: set[DurationQuality] = set()
            if previous_duration_count < previous_total_plays:
                previous_qualities.add("unknown")
            if previous_lower_bound_count:
                previous_qualities.add("lower_bound")
            if previous_reported_count:
                previous_qualities.add("reported")
            previous_estimated_count = (
                previous_duration_count
                - previous_lower_bound_count
                - previous_reported_count
            )
            if previous_estimated_count > 0:
                previous_qualities.add("estimated")
            previous_duration_quality = combine_duration_qualities(previous_qualities)
            if previous_total_plays:
                plays_change_pct = round(
                    (total_plays - previous_total_plays) / previous_total_plays * 100, 2
                )
            current_duration_incomplete = total_plays > 0 and duration_quality in {
                "lower_bound",
                "unknown",
            }
            previous_duration_incomplete = (
                previous_total_plays > 0
                and previous_duration_quality in {"lower_bound", "unknown"}
            )
            if current_duration_incomplete or previous_duration_incomplete:
                listen_change_reason = "incomplete_duration"
            elif previous_total_listen_sec:
                listen_change_pct = round(
                    (total_listen_sec - previous_total_listen_sec)
                    / previous_total_listen_sec
                    * 100,
                    2,
                )
                listen_change_reason = "available"
            else:
                listen_change_reason = "no_previous_data"

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
            "listen_change_reason": listen_change_reason,
            "window_days": (
                (end_date - start_date).days + 1
                if is_custom_window
                else (days if days > 0 else None)
            ),
            "duration_quality": duration_quality,
            "duration_coverage_pct": duration_coverage_pct,
            "duration_quality_counts": duration_quality_counts,
            "play_source_counts": play_source_counts,
            "previous_duration_quality": previous_duration_quality,
            "previous_duration_coverage_pct": previous_duration_coverage_pct,
        }
