"""Artist, album, and client drill-down statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import aiosqlite

from src.core_types import DurationQuality, classify_history_duration_quality
from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db
from src.stats_query_common import database_path as _path
from src.stats_query_common import scope_predicate
from src.stats_scope import StatsScope
from src.windows import (
    _local_date_range,
    _played_at_to_local_datetime,
    resolve_timezone,
)

EntityType = Literal["artist", "album", "client"]


@dataclass(frozen=True, slots=True)
class EntityIdentity:
    """Stable identity shared by ranking, relationship, and detail queries."""

    entity_type: EntityType
    name: str
    entity_id: str | None = None
    source_id: str | None = None
    artist: str | None = None

    @classmethod
    def create(
        cls,
        *,
        entity_type: str,
        name: str,
        entity_id: str | None = None,
        source_id: str | None = None,
        artist: str | None = None,
    ) -> EntityIdentity:
        if entity_type not in ("artist", "album", "client"):
            raise ValueError("entity_type must be one of: artist, album, client")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must not be empty")
        if entity_type == "album" and not source_id:
            raise ValueError("source_id is required for album details")
        if entity_type == "client":
            entity_id = None
            source_id = None
            artist = None
        return cls(
            entity_type=entity_type,
            name=name,
            entity_id=entity_id or None,
            source_id=source_id or None,
            artist=artist or None,
        )


def _entity_predicate(identity: EntityIdentity) -> tuple[str, list]:
    if identity.entity_type == "artist":
        return "artist = ?", [identity.name]
    if identity.entity_type == "client":
        return "client_name = ?", [identity.name]

    predicates = ["album = ?"]
    params: list = [identity.name]
    if identity.source_id:
        predicates.append("COALESCE(source_id, ?) = ?")
        params.extend([LEGACY_SOURCE_ID, identity.source_id])
    if identity.entity_id:
        predicates.append("NULLIF(album_id, '') = ?")
        params.append(identity.entity_id)
    else:
        predicates.append("NULLIF(album_id, '') IS NULL")
        predicates.append("COALESCE(artist, '') = ?")
        params.append(identity.artist or "")
    return " AND ".join(predicates), params


def _track_key(row: aiosqlite.Row) -> tuple:
    source_id = row["source_id"]
    track_id = row["track_id"]
    if track_id not in (None, ""):
        return (source_id, "id", track_id)
    return (
        source_id,
        "legacy",
        row["title"],
        row["artist"],
        row["album"],
    )


def _row_duration_quality(row: aiosqlite.Row) -> DurationQuality:
    """Describe what a stored duration can honestly claim.

    Poller rows written before idempotent session checkpoints have no session
    ID, and unfinished durable rows contain only the latest checkpoint. A
    finalized polling duration is still an estimate: existing rows do not
    record which collector version produced them, so playback-report records
    from before the sparse-report fix cannot be distinguished safely.
    """
    return classify_history_duration_quality(
        listen_duration_sec=row["listen_duration_sec"],
        source=row["source"],
        session_id=row["session_id"],
        finalized=row["finalized"],
        duration_confidence=row["duration_confidence"],
    )


def _combined_duration_quality(qualities: set[DurationQuality]) -> DurationQuality:
    """Combine row-level duration quality without overstating precision."""
    if not qualities or qualities == {"unknown"}:
        return "unknown"
    if "unknown" in qualities or "lower_bound" in qualities:
        return "lower_bound"
    if "estimated" in qualities:
        return "estimated"
    return "reported"


async def _artist_rank(
    db: aiosqlite.Connection,
    scope: StatsScope,
    identity: EntityIdentity,
    *,
    previous: bool,
) -> int | None:
    pred, params = scope_predicate(scope, previous=previous)
    value_column = "play_count" if scope.metric == "plays" else "total_listen_sec"
    async with db.execute(
        f"""
        WITH aggregated AS (
            SELECT
                artist AS name,
                COUNT(*) AS play_count,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec
            FROM play_history
            WHERE artist IS NOT NULL AND artist != '' AND ({pred})
            GROUP BY artist
        ), ranked AS (
            SELECT
                name,
                ROW_NUMBER() OVER (
                    ORDER BY {value_column} DESC, name ASC
                ) AS entity_rank
            FROM aggregated
        )
        SELECT entity_rank FROM ranked WHERE name = ?
        """,
        [*params, identity.name],
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def _album_rank(
    db: aiosqlite.Connection,
    scope: StatsScope,
    identity: EntityIdentity,
    *,
    previous: bool,
) -> int | None:
    pred, params = scope_predicate(scope, previous=previous)
    value_column = "play_count" if scope.metric == "plays" else "total_listen_sec"
    target_predicates = []
    target_params: list = []
    if identity.source_id:
        target_predicates.append("source_id = ?")
        target_params.append(identity.source_id)
    if identity.entity_id:
        target_predicates.append("album_id = ?")
        target_params.append(identity.entity_id)
    else:
        target_predicates.extend([
            "album_id IS NULL",
            "album = ?",
            "COALESCE(artist, '') = ?",
        ])
        target_params.extend([identity.name, identity.artist or ""])
    target_where = " AND ".join(target_predicates) or "1=1"
    async with db.execute(
        f"""
        WITH album_rows AS (
            SELECT
                id,
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
        ), entities AS (
            SELECT
                album_rows.album,
                album_rows.artist,
                album_rows.album_id,
                latest.normalized_source_id AS source_id,
                latest.play_count,
                latest.total_listen_sec
            FROM latest
            JOIN album_rows ON album_rows.id = latest.latest_id
        ), ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    ORDER BY {value_column} DESC, album ASC, artist ASC, source_id ASC
                ) AS entity_rank
            FROM entities
        )
        SELECT entity_rank FROM ranked WHERE {target_where}
        ORDER BY entity_rank ASC LIMIT 1
        """,
        [LEGACY_SOURCE_ID, *params, *target_params],
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def _client_rank(
    db: aiosqlite.Connection,
    scope: StatsScope,
    identity: EntityIdentity,
    *,
    previous: bool,
) -> int | None:
    pred, params = scope_predicate(scope, previous=previous)
    value_column = "play_count" if scope.metric == "plays" else "total_listen_sec"
    async with db.execute(
        f"""
        WITH aggregated AS (
            SELECT
                COALESCE(client_name, '') AS name,
                COUNT(*) AS play_count,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec
            FROM play_history
            WHERE {pred}
            GROUP BY COALESCE(client_name, '')
        ), ranked AS (
            SELECT
                name,
                ROW_NUMBER() OVER (
                    ORDER BY {value_column} DESC, name ASC
                ) AS entity_rank
            FROM aggregated
        )
        SELECT entity_rank FROM ranked WHERE name = ?
        """,
        [*params, identity.name],
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def _entity_rank(
    db: aiosqlite.Connection,
    scope: StatsScope,
    identity: EntityIdentity,
    *,
    previous: bool,
) -> int | None:
    if identity.entity_type == "artist":
        return await _artist_rank(db, scope, identity, previous=previous)
    if identity.entity_type == "client":
        return await _client_rank(db, scope, identity, previous=previous)
    return await _album_rank(db, scope, identity, previous=previous)


async def get_entity_detail(
    scope: StatsScope,
    identity: EntityIdentity,
    *,
    db_path: str | None = None,
) -> dict:
    """Return one artist, album, or client drill-down inside ``scope``.

    One ordered history scan builds the summary, local-date trend, popular
    tracks, and recent plays. Rank queries use the same ordering rules as the
    dashboard lists and compare against the preceding equal-length window.
    """
    path = _path(db_path)
    tz = resolve_timezone(scope.timezone_name)
    scope_pred, scope_params = scope_predicate(scope)
    entity_pred, entity_params = _entity_predicate(identity)
    where = f"({scope_pred}) AND ({entity_pred})"
    params = [*scope_params, *entity_params]

    total_plays = 0
    total_listen_sec = 0
    first_played_at: str | None = None
    last_played_at: str | None = None
    resolved_entity_id = identity.entity_id
    resolved_artist = identity.artist
    trend: dict[str, dict] = {}
    track_totals: dict[tuple, dict] = {}
    recent_plays: list[dict] = []
    duration_qualities: set[DurationQuality] = set()

    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                id,
                played_at,
                played_at_epoch,
                username,
                client_name,
                track_id,
                title,
                artist,
                artist_id,
                album,
                album_id,
                listen_duration_sec,
                COALESCE(source, 'poller') AS source,
                session_id,
                COALESCE(finalized, 1) AS finalized,
                COALESCE(duration_confidence, 'estimated') AS duration_confidence,
                COALESCE(source_id, ?) AS source_id,
                COALESCE(source_name, ?) AS source_name
            FROM play_history
            WHERE {where}
            ORDER BY played_at_epoch DESC, id DESC
            """,
            [LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME, *params],
        ) as cursor:
            async for row in cursor:
                stored_duration = row["listen_duration_sec"]
                duration = int(stored_duration or 0)
                duration_quality = _row_duration_quality(row)
                duration_qualities.add(duration_quality)
                total_plays += 1
                total_listen_sec += duration
                played_at = row["played_at"]
                if played_at:
                    if last_played_at is None:
                        last_played_at = played_at
                    first_played_at = played_at
                if resolved_entity_id is None and identity.entity_type in ("artist", "album"):
                    candidate = row[
                        "artist_id" if identity.entity_type == "artist" else "album_id"
                    ]
                    resolved_entity_id = candidate or None
                if identity.entity_type == "album" and resolved_artist is None:
                    resolved_artist = row["artist"] or None

                local = _played_at_to_local_datetime(played_at, tz)
                if local is not None:
                    bucket_key = local.date().isoformat()
                    bucket = trend.setdefault(bucket_key, {
                        "date": bucket_key,
                        "play_count": 0,
                        "total_listen_sec": 0,
                        "_duration_qualities": set(),
                    })
                    bucket["play_count"] += 1
                    bucket["total_listen_sec"] += duration
                    bucket["_duration_qualities"].add(duration_quality)

                if len(recent_plays) < 10:
                    recent_plays.append({
                        "played_at": played_at,
                        "username": row["username"],
                        "client_name": row["client_name"],
                        "track_id": row["track_id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "album": row["album"],
                        "listen_duration_sec": (
                            int(stored_duration) if stored_duration is not None else None
                        ),
                        "duration_quality": duration_quality,
                        "source_id": row["source_id"],
                        "source_name": row["source_name"],
                    })

                key = _track_key(row)
                track = track_totals.get(key)
                if track is None:
                    track = {
                        "track_id": row["track_id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "album": row["album"],
                        "play_count": 0,
                        "total_listen_sec": 0,
                        "last_played_at": played_at,
                        "source_id": row["source_id"],
                        "source_name": row["source_name"],
                        "_duration_qualities": set(),
                    }
                    track_totals[key] = track
                track["play_count"] += 1
                track["total_listen_sec"] += duration
                track["_duration_qualities"].add(duration_quality)

        current_rank = await _entity_rank(db, scope, identity, previous=False)
        comparison_available = bool(
            scope.days > 0
            or (scope.start_date is not None and scope.end_date is not None)
        )
        previous_rank = (
            await _entity_rank(db, scope, identity, previous=True)
            if comparison_available
            else None
        )

    if total_plays:
        trend_start, trend_end = _local_date_range(
            scope.days,
            tz,
            scope.start_date,
            scope.end_date,
        )
        if trend_start is None or trend_end is None:
            played_dates = sorted(trend)
            if played_dates:
                trend_start = date.fromisoformat(played_dates[0])
                trend_end = date.fromisoformat(played_dates[-1])

        cursor_date = trend_start
        while cursor_date is not None and trend_end is not None and cursor_date <= trend_end:
            bucket_key = cursor_date.isoformat()
            trend.setdefault(bucket_key, {
                "date": bucket_key,
                "play_count": 0,
                "total_listen_sec": 0,
                "_duration_qualities": set(),
            })
            cursor_date += timedelta(days=1)

    for bucket in trend.values():
        qualities = bucket.pop("_duration_qualities")
        bucket["duration_quality"] = (
            "reported"
            if int(bucket["play_count"]) == 0
            else _combined_duration_quality(qualities)
        )
    for track in track_totals.values():
        track["duration_quality"] = _combined_duration_quality(
            track.pop("_duration_qualities")
        )

    metric_key = "play_count" if scope.metric == "plays" else "total_listen_sec"
    top_tracks = sorted(
        track_totals.values(),
        key=lambda row: (
            -int(row[metric_key] or 0),
            str(row["title"] or "").casefold(),
            str(row["source_id"] or ""),
            str(row["track_id"] or ""),
        ),
    )[:10]
    rank_change = (
        previous_rank - current_rank
        if previous_rank is not None and current_rank is not None
        else None
    )
    return {
        "entity_type": identity.entity_type,
        "name": identity.name,
        "artist": resolved_artist if identity.entity_type == "album" else None,
        "entity_id": resolved_entity_id,
        "entity_source_id": identity.source_id,
        "metric": scope.metric,
        "total_plays": total_plays,
        "total_listen_sec": total_listen_sec,
        "duration_quality": _combined_duration_quality(duration_qualities),
        "unique_tracks": len(track_totals),
        "average_listen_sec": round(total_listen_sec / total_plays, 2) if total_plays else 0,
        "first_played_at": first_played_at,
        "last_played_at": last_played_at,
        "current_rank": current_rank,
        "previous_rank": previous_rank,
        "rank_change": rank_change,
        "comparison_available": comparison_available,
        "trend": [trend[key] for key in sorted(trend)],
        "top_tracks": top_tracks,
        "recent_plays": recent_plays,
    }
