"""Cross-dimensional statistics derived from the existing play history.

The endpoint intentionally returns chart-ready values without conclusions.  A
single selected dimension is related to time, dayparts, and the immediately
preceding equal-length period.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Literal

import aiosqlite

from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.stats_query_common import scope_predicate
from src.stats_scope import StatsScope
from src.windows import (
    _local_date_range,
    resolve_timezone,
)

RelationDimension = Literal["artist", "album", "client"]
RelationGrain = Literal["day", "week", "month"]

RELATION_DIMENSIONS = ("artist", "album", "client")
DAYPARTS = ("night", "morning", "afternoon", "evening")
OTHER_KEY = "__other__"
TREND_LIMIT = 5
MATRIX_LIMIT = 8
COMPARISON_LIMIT = 8


def _totals_query(predicate: str, dimension: RelationDimension) -> str:
    """Build an aggregate query that groups by raw identity columns.

    Constructing the public string key once per aggregate group is materially
    cheaper than concatenating it for every history row before SQLite groups it.
    """
    if dimension == "album":
        return f"""
            SELECT
                COALESCE(NULLIF(source_id, ''), ?),
                MAX(COALESCE(NULLIF(source_name, ''), ?)),
                NULLIF(album_id, ''),
                album,
                NULLIF(artist, ''),
                COUNT(*) AS play_count,
                COALESCE(SUM(COALESCE(listen_duration_sec, 0)), 0)
                    AS total_listen_sec,
                COUNT(listen_duration_sec) AS duration_count,
                COALESCE(SUM(
                    CASE
                        WHEN listen_duration_sec IS NOT NULL
                         AND duration_confidence = 'reported' THEN 1
                        ELSE 0
                    END
                ), 0) AS reported_duration_count,
                MIN(played_at_epoch) AS first_epoch,
                MAX(played_at_epoch) AS last_epoch
            FROM play_history
            WHERE ({predicate}) AND album IS NOT NULL AND album != ''
            GROUP BY source_id, album_id, album, artist
        """

    if dimension == "artist":
        identity_columns = "NULL, NULL, NULL, artist, NULL"
        eligible = "artist IS NOT NULL"
        grouping = "artist"
    else:
        identity_columns = "NULL, NULL, NULL, COALESCE(client, ''), NULL"
        eligible = "1=1"
        grouping = "client"

    return f"""
        WITH base AS (
            SELECT
                played_at_epoch,
                NULLIF(client_name, '') AS client,
                NULLIF(artist, '') AS artist,
                NULLIF(album, '') AS album,
                NULLIF(album_id, '') AS album_id,
                listen_duration_sec,
                duration_confidence,
                COALESCE(NULLIF(source_id, ''), ?) AS normalized_source_id,
                COALESCE(NULLIF(source_name, ''), ?) AS normalized_source_name
            FROM play_history
            WHERE {predicate}
        )
        SELECT
            {identity_columns},
            COUNT(*) AS play_count,
            COALESCE(SUM(COALESCE(listen_duration_sec, 0)), 0)
                AS total_listen_sec,
            COUNT(listen_duration_sec) AS duration_count,
            COALESCE(SUM(
                CASE
                    WHEN listen_duration_sec IS NOT NULL
                     AND duration_confidence = 'reported' THEN 1
                    ELSE 0
                END
            ), 0) AS reported_duration_count,
            MIN(played_at_epoch) AS first_epoch,
            MAX(played_at_epoch) AS last_epoch
        FROM base
        WHERE {eligible}
        GROUP BY {grouping}
    """


def _metric_value(values: dict, metric: str) -> int:
    field = "play_count" if metric == "plays" else "total_listen_sec"
    return int(values.get(field, 0) or 0)


def _ordered_keys(totals: dict[str, dict], metadata: dict[str, dict], metric: str) -> list[str]:
    return sorted(
        totals,
        key=lambda key: (
            -_metric_value(totals[key], metric),
            -int(totals[key].get("play_count", 0) or 0),
            str(metadata.get(key, {}).get("label", "")).casefold(),
            key,
        ),
    )


def _select_grain(start: date | None, end: date | None) -> RelationGrain:
    if start is None or end is None:
        return "day"
    span = (end - start).days + 1
    if span <= 45:
        return "day"
    if span <= 180:
        return "week"
    return "month"


def _bucket_for_day(value: date, grain: RelationGrain) -> str:
    if grain == "day":
        return value.isoformat()
    if grain == "week":
        return (value - timedelta(days=value.weekday())).isoformat()
    return f"{value.year:04d}-{value.month:02d}"


def _bucket_range(start: date | None, end: date | None, grain: RelationGrain) -> list[str]:
    if start is None or end is None:
        return []
    if grain == "day":
        count = (end - start).days + 1
        return [(start + timedelta(days=index)).isoformat() for index in range(count)]
    if grain == "week":
        current = start - timedelta(days=start.weekday())
        last = end - timedelta(days=end.weekday())
        buckets = []
        while current <= last:
            buckets.append(current.isoformat())
            current += timedelta(days=7)
        return buckets

    current_year, current_month = start.year, start.month
    last_key = f"{end.year:04d}-{end.month:02d}"
    buckets = []
    while True:
        key = f"{current_year:04d}-{current_month:02d}"
        buckets.append(key)
        if key == last_key:
            return buckets
        current_month += 1
        if current_month == 13:
            current_year += 1
            current_month = 1


def _daypart(hour: int) -> str:
    if hour < 6:
        return "night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def _empty_values() -> dict[str, int]:
    return {"play_count": 0, "total_listen_sec": 0}


def _add_value(target: dict, key, duration: int) -> None:
    value = target.get(key)
    if value is None:
        target[key] = {"play_count": 1, "total_listen_sec": duration}
        return
    value["play_count"] += 1
    value["total_listen_sec"] += duration


def _add_aggregate(target: dict, key, plays: int, duration: int) -> None:
    value = target.get(key)
    if value is None:
        target[key] = {"play_count": plays, "total_listen_sec": duration}
        return
    value["play_count"] += plays
    value["total_listen_sec"] += duration


def _shape_query(
    predicate: str,
    params: list,
    dimension: RelationDimension,
) -> tuple[str, list]:
    if dimension == "artist":
        return (
            f"""
            SELECT played_at_epoch, artist, COALESCE(listen_duration_sec, 0)
            FROM play_history
            WHERE ({predicate}) AND artist IS NOT NULL AND artist != ''
            """,
            params,
        )
    if dimension == "album":
        return (
            f"""
            SELECT
                played_at_epoch,
                COALESCE(NULLIF(source_id, ''), ?),
                NULLIF(album_id, ''),
                album,
                artist,
                COALESCE(listen_duration_sec, 0)
            FROM play_history
            WHERE ({predicate}) AND album IS NOT NULL AND album != ''
            """,
            [LEGACY_SOURCE_ID, *params],
        )
    return (
        f"""
        SELECT played_at_epoch, client_name, COALESCE(listen_duration_sec, 0)
        FROM play_history
        WHERE {predicate}
        """,
        params,
    )


def _selected_key_resolver(
    dimension: RelationDimension,
    metadata: dict[str, dict],
    selected_keys: set[str],
) -> Callable[[tuple], str | None]:
    """Resolve only visible identities, avoiding per-row public key creation."""
    if dimension == "album":
        identities = {
            (
                str(metadata[key].get("source_id") or LEGACY_SOURCE_ID),
                str(metadata[key].get("entity_id") or ""),
                "" if metadata[key].get("entity_id") else str(
                    metadata[key].get("label") or ""
                ),
                "" if metadata[key].get("entity_id") else str(
                    metadata[key].get("artist") or ""
                ),
            ): key
            for key in selected_keys
        }

        def album_key(row: tuple) -> str | None:
            entity_id = str(row[2] or "")
            return identities.get((
                str(row[1] or LEGACY_SOURCE_ID),
                entity_id,
                "" if entity_id else str(row[3] or ""),
                "" if entity_id else str(row[4] or ""),
            ))

        return album_key

    labels = {
        str(metadata[key].get("label") or ""): key
        for key in selected_keys
    }
    return lambda row: labels.get(str(row[1] or ""))


async def _scan_album_month_shapes_utc(
    db: aiosqlite.Connection,
    predicate: str,
    params: list,
    *,
    trend_keys: set[str],
    matrix_keys: set[str],
) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    """Aggregate long UTC album ranges in SQLite instead of streaming every row."""
    await db.execute("""
        CREATE TEMP TABLE IF NOT EXISTS relation_selected_album (
            entity_key TEXT PRIMARY KEY,
            in_trend INTEGER NOT NULL,
            in_matrix INTEGER NOT NULL
        ) WITHOUT ROWID
    """)
    await db.execute("DELETE FROM relation_selected_album")
    selected_keys = trend_keys | matrix_keys
    await db.executemany(
        """
        INSERT INTO relation_selected_album (entity_key, in_trend, in_matrix)
        VALUES (?, ?, ?)
        """,
        [
            (key, int(key in trend_keys), int(key in matrix_keys))
            for key in selected_keys
        ],
    )
    entity_expression = """
        'album:' || COALESCE(NULLIF(history.source_id, ''), ?) || char(31) ||
        CASE
            WHEN NULLIF(history.album_id, '') IS NOT NULL
                THEN 'id:' || NULLIF(history.album_id, '')
            ELSE 'legacy:' || history.album || char(31) ||
                 COALESCE(NULLIF(history.artist, ''), '')
        END
    """
    trend: dict[tuple[str, str], dict] = {}
    matrix: dict[tuple[str, str], dict] = {}
    async with db.execute(
        f"""
        SELECT
            strftime('%Y-%m', history.played_at_epoch, 'unixepoch') AS bucket,
            CAST(
                (((history.played_at_epoch % 86400) + 86400) % 86400) / 21600
                AS INTEGER
            ) AS daypart_index,
            CASE
                WHEN selected.in_trend = 1 THEN selected.entity_key
                ELSE ?
            END AS trend_key,
            CASE
                WHEN selected.in_matrix = 1 THEN selected.entity_key
                ELSE NULL
            END AS matrix_key,
            COUNT(*) AS play_count,
            COALESCE(SUM(COALESCE(history.listen_duration_sec, 0)), 0)
                AS total_listen_sec
        FROM play_history AS history
        LEFT JOIN relation_selected_album AS selected
          ON selected.entity_key = ({entity_expression})
        WHERE ({predicate})
          AND history.album IS NOT NULL
          AND history.album != ''
          AND history.played_at_epoch IS NOT NULL
        GROUP BY 1, 2, 3, 4
        """,
        [OTHER_KEY, LEGACY_SOURCE_ID, *params],
    ) as cursor:
        async for row in cursor:
            if row[0] is None:
                continue
            bucket = str(row[0])
            daypart = DAYPARTS[int(row[1])]
            plays = int(row[4] or 0)
            duration = int(row[5] or 0)
            _add_aggregate(trend, (bucket, str(row[2])), plays, duration)
            if row[3] is not None:
                _add_aggregate(
                    matrix,
                    (str(row[3]), daypart),
                    plays,
                    duration,
                )
    return trend, matrix


async def _scan_totals(
    db: aiosqlite.Connection,
    predicate: str,
    params: list,
    dimension: RelationDimension,
    *,
    tz=None,
) -> tuple[
    dict[str, dict],
    dict[str, dict],
    int,
    int,
    int,
    date | None,
    date | None,
]:
    totals: dict[str, dict] = {}
    metadata: dict[str, dict] = {}
    row_count = 0
    duration_count = 0
    reported_duration_count = 0
    first_epoch: int | None = None
    last_epoch: int | None = None
    async with db.execute(
        _totals_query(predicate, dimension),
        [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params],
    ) as cursor:
        async for row in cursor:
            source_id = row[0]
            source_name = row[1]
            entity_id = row[2]
            label = str(row[3] or "")
            artist = row[4]
            if dimension == "artist":
                key = f"artist:{label}"
            elif dimension == "album":
                identity = (
                    f"id:{entity_id}"
                    if entity_id
                    else f"legacy:{label}\x1f{artist or ''}"
                )
                key = f"album:{source_id}\x1f{identity}"
            else:
                key = f"client:{label}" if label else "client:__unknown__"
            candidate = {
                "key": key,
                "label": label,
                "artist": artist,
                "entity_id": entity_id,
                "source_id": source_id,
                "source_name": source_name,
            }
            existing_meta = metadata.get(key)
            if existing_meta is None:
                metadata[key] = candidate
            else:
                for field in ("label", "artist", "source_name"):
                    value = candidate.get(field)
                    if value is not None and (
                        existing_meta.get(field) is None
                        or str(value) > str(existing_meta[field])
                    ):
                        existing_meta[field] = value
            values = totals.get(key)
            if values is None:
                totals[key] = {
                    "play_count": int(row[5] or 0),
                    "total_listen_sec": int(row[6] or 0),
                }
            else:
                values["play_count"] += int(row[5] or 0)
                values["total_listen_sec"] += int(row[6] or 0)
            row_count += int(row[5] or 0)
            duration_count += int(row[7] or 0)
            reported_duration_count += int(row[8] or 0)
            if row[9] is not None:
                value = int(row[9])
                first_epoch = value if first_epoch is None else min(first_epoch, value)
            if row[10] is not None:
                value = int(row[10])
                last_epoch = value if last_epoch is None else max(last_epoch, value)
    first_date = (
        datetime.fromtimestamp(first_epoch, tz).date()
        if tz is not None and first_epoch is not None
        else None
    )
    last_date = (
        datetime.fromtimestamp(last_epoch, tz).date()
        if tz is not None and last_epoch is not None
        else None
    )
    return (
        totals,
        metadata,
        row_count,
        duration_count,
        reported_duration_count,
        first_date,
        last_date,
    )


async def _scan_shapes(
    db: aiosqlite.Connection,
    predicate: str,
    params: list,
    dimension: RelationDimension,
    *,
    tz,
    grain: RelationGrain,
    trend_keys: set[str],
    matrix_keys: set[str],
    metadata: dict[str, dict],
) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    if (
        dimension == "album"
        and getattr(tz, "key", None) == "UTC"
        and grain == "month"
    ):
        return await _scan_album_month_shapes_utc(
            db,
            predicate,
            params,
            trend_keys=trend_keys,
            matrix_keys=matrix_keys,
        )

    trend: dict[tuple[str, str], dict] = {}
    matrix: dict[tuple[str, str], dict] = {}
    query, query_params = _shape_query(predicate, params, dimension)
    key_for_row = _selected_key_resolver(
        dimension,
        metadata,
        trend_keys | matrix_keys,
    )
    async with db.execute(
        query,
        query_params,
    ) as cursor:
        async for row in cursor:
            if row[0] is None:
                continue
            try:
                local = datetime.fromtimestamp(int(row[0]), tz)
            except (OSError, OverflowError, ValueError):
                continue
            entity_key = key_for_row(row)
            duration = int(row[-1] or 0)
            trend_key = entity_key if entity_key in trend_keys else OTHER_KEY
            _add_value(trend, (_bucket_for_day(local.date(), grain), trend_key), duration)
            if entity_key in matrix_keys:
                _add_value(matrix, (entity_key, _daypart(local.hour)), duration)
    return trend, matrix


def _series_meta(metadata: dict[str, dict], key: str) -> dict:
    if key == OTHER_KEY:
        return {
            "key": OTHER_KEY,
            "label": "",
            "artist": None,
            "entity_id": None,
            "source_id": None,
            "source_name": None,
        }
    return dict(metadata[key])


async def get_data_relations(
    scope: StatsScope,
    dimension: RelationDimension,
    *,
    db_path: str | None = None,
) -> dict:
    """Return chart-ready relationships for one dimension and stats scope."""
    if dimension not in RELATION_DIMENSIONS:
        raise ValueError("dimension must be one of: artist, album, client")

    path = _path(db_path)
    tz = resolve_timezone(scope.timezone_name)
    current_pred, current_params = scope_predicate(scope)
    previous_pred, previous_params = scope_predicate(scope, previous=True)

    async with connect_db(path) as db:
        (
            current_totals,
            current_meta,
            current_rows,
            duration_rows,
            reported_duration_rows,
            observed_start,
            observed_end,
        ) = await _scan_totals(
            db,
            current_pred,
            current_params,
            dimension,
            tz=tz,
        )

        comparison_available = bool(
            scope.days > 0
            or (scope.start_date is not None and scope.end_date is not None)
        )
        previous_totals: dict[str, dict] = {}
        previous_meta: dict[str, dict] = {}
        if comparison_available:
            previous_totals, previous_meta, *_ = await _scan_totals(
                db,
                previous_pred,
                previous_params,
                dimension,
            )

        requested_start, requested_end = _local_date_range(
            scope.days,
            tz,
            scope.start_date,
            scope.end_date,
        )
        range_start = requested_start or observed_start
        range_end = requested_end or observed_end
        grain = _select_grain(range_start, range_end)
        buckets = _bucket_range(range_start, range_end, grain)

        ordered_current = _ordered_keys(current_totals, current_meta, scope.metric)
        trend_keys = ordered_current[:TREND_LIMIT]
        matrix_keys = ordered_current[:MATRIX_LIMIT]
        trend_values: dict[tuple[str, str], dict] = {}
        matrix_values: dict[tuple[str, str], dict] = {}
        if current_totals:
            trend_values, matrix_values = await _scan_shapes(
                db,
                current_pred,
                current_params,
                dimension,
                tz=tz,
                grain=grain,
                trend_keys=set(trend_keys),
                matrix_keys=set(matrix_keys),
                metadata=current_meta,
            )

    visible_trend_keys = list(trend_keys)
    if len(current_totals) > len(trend_keys):
        visible_trend_keys.append(OTHER_KEY)
    trend = []
    for key in visible_trend_keys:
        series = _series_meta(current_meta, key)
        series["points"] = [
            {
                "bucket": bucket,
                **trend_values.get((bucket, key), _empty_values()),
            }
            for bucket in buckets
        ]
        trend.append(series)

    matrix = []
    for key in matrix_keys:
        row = _series_meta(current_meta, key)
        row["points"] = [
            {
                "daypart": daypart,
                **matrix_values.get((key, daypart), _empty_values()),
            }
            for daypart in DAYPARTS
        ]
        matrix.append(row)

    comparison = []
    if comparison_available:
        combined_meta = {**previous_meta, **current_meta}
        combined_totals = {
            key: {
                "play_count": int(current_totals.get(key, {}).get("play_count", 0) or 0)
                + int(previous_totals.get(key, {}).get("play_count", 0) or 0),
                "total_listen_sec": int(
                    current_totals.get(key, {}).get("total_listen_sec", 0) or 0
                ) + int(previous_totals.get(key, {}).get("total_listen_sec", 0) or 0),
            }
            for key in current_totals.keys() | previous_totals.keys()
        }
        comparison_keys = _ordered_keys(
            combined_totals,
            combined_meta,
            scope.metric,
        )[:COMPARISON_LIMIT]
        for key in comparison_keys:
            item = _series_meta(combined_meta, key)
            item.update({
                "current_play_count": int(
                    current_totals.get(key, {}).get("play_count", 0) or 0
                ),
                "previous_play_count": int(
                    previous_totals.get(key, {}).get("play_count", 0) or 0
                ),
                "current_total_listen_sec": int(
                    current_totals.get(key, {}).get("total_listen_sec", 0) or 0
                ),
                "previous_total_listen_sec": int(
                    previous_totals.get(key, {}).get("total_listen_sec", 0) or 0
                ),
            })
            comparison.append(item)

    coverage = round(duration_rows * 100 / current_rows, 1) if current_rows else 0.0
    reported = (
        round(reported_duration_rows * 100 / current_rows, 1)
        if current_rows
        else 0.0
    )
    return {
        "dimension": dimension,
        "metric": scope.metric,
        "grain": grain,
        "comparison_available": comparison_available,
        "duration_coverage_pct": coverage,
        "reported_duration_pct": reported,
        "trend": trend,
        "matrix": matrix,
        "comparison": comparison,
    }
