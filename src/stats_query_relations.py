"""Cross-dimensional statistics derived from the existing play history.

The endpoint intentionally returns chart-ready values without conclusions.  A
single selected dimension is related to time, dayparts, and the immediately
preceding equal-length period.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import aiosqlite

from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.stats_scope import StatsScope
from src.windows import (
    _local_date_range,
    _played_at_to_local_datetime,
    _previous_window_predicate,
    _source_predicate,
    _username_predicate,
    _window_predicate,
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


def _scope_predicate(scope: StatsScope, *, previous: bool = False) -> tuple[str, list]:
    predicate_factory = _previous_window_predicate if previous else _window_predicate
    pred, params = predicate_factory(
        scope.days,
        scope.timezone_name,
        scope.start_date,
        scope.end_date,
    )
    pred, params = _source_predicate(pred, params, scope.source_id)
    pred, params = _username_predicate(pred, params, scope.username)
    return pred, params


def _clean(value) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _entity_for_row(row: aiosqlite.Row, dimension: RelationDimension) -> dict | None:
    if dimension == "artist":
        label = _clean(row["artist"])
        if not label:
            return None
        # Artist rankings and the existing artist drill-down both aggregate by
        # name across the active source scope, so the relation view does too.
        return {
            "key": f"artist:{label}",
            "label": label,
            "artist": None,
            "entity_id": None,
            "source_id": None,
            "source_name": None,
        }

    if dimension == "album":
        label = _clean(row["album"])
        if not label:
            return None
        source_id = _clean(row["source_id"]) or LEGACY_SOURCE_ID
        source_name = _clean(row["source_name"]) or LEGACY_SOURCE_NAME
        album_id = _clean(row["album_id"]) or None
        artist = _clean(row["artist"]) or None
        identity = (
            f"id:{album_id}"
            if album_id
            else f"legacy:{label}\x1f{artist or ''}"
        )
        return {
            "key": f"album:{source_id}\x1f{identity}",
            "label": label,
            "artist": artist,
            "entity_id": album_id,
            "source_id": source_id,
            "source_name": source_name,
        }

    label = _clean(row["client_name"])
    return {
        "key": f"client:{label}" if label else "client:__unknown__",
        "label": label,
        "artist": None,
        "entity_id": None,
        "source_id": None,
        "source_name": None,
    }


def _merge_meta(target: dict[str, dict], entity: dict) -> None:
    existing = target.get(entity["key"])
    if existing is None:
        target[entity["key"]] = entity
        return
    for field in ("artist", "entity_id", "source_id", "source_name"):
        if not existing.get(field) and entity.get(field):
            existing[field] = entity[field]


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
    return value.strftime("%Y-%m")


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
    last_key = end.strftime("%Y-%m")
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
    value = target.setdefault(key, _empty_values())
    value["play_count"] += 1
    value["total_listen_sec"] += duration


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
    first_date: date | None = None
    last_date: date | None = None
    async with db.execute(
        f"""
        SELECT
            played_at,
            client_name,
            artist,
            artist_id,
            album,
            album_id,
            listen_duration_sec,
            duration_confidence,
            COALESCE(source_id, ?) AS source_id,
            COALESCE(source_name, ?) AS source_name
        FROM play_history
        WHERE {predicate}
        """,
        [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params],
    ) as cursor:
        async for row in cursor:
            entity = _entity_for_row(row, dimension)
            if entity is None:
                continue
            _merge_meta(metadata, entity)
            duration = int(row["listen_duration_sec"] or 0)
            _add_value(totals, entity["key"], duration)
            row_count += 1
            if row["listen_duration_sec"] is not None:
                duration_count += 1
                if row["duration_confidence"] == "reported":
                    reported_duration_count += 1
            if tz is not None:
                local = _played_at_to_local_datetime(row["played_at"], tz)
                if local is not None:
                    local_date = local.date()
                    first_date = local_date if first_date is None else min(first_date, local_date)
                    last_date = local_date if last_date is None else max(last_date, local_date)
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
) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    trend: dict[tuple[str, str], dict] = {}
    matrix: dict[tuple[str, str], dict] = {}
    async with db.execute(
        f"""
        SELECT
            played_at,
            client_name,
            artist,
            artist_id,
            album,
            album_id,
            listen_duration_sec,
            COALESCE(source_id, ?) AS source_id,
            COALESCE(source_name, ?) AS source_name
        FROM play_history
        WHERE {predicate}
        """,
        [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params],
    ) as cursor:
        async for row in cursor:
            entity = _entity_for_row(row, dimension)
            if entity is None:
                continue
            local = _played_at_to_local_datetime(row["played_at"], tz)
            if local is None:
                continue
            entity_key = entity["key"]
            duration = int(row["listen_duration_sec"] or 0)
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
    current_pred, current_params = _scope_predicate(scope)
    previous_pred, previous_params = _scope_predicate(scope, previous=True)

    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
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
