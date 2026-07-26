import aiosqlite
import os
from datetime import date

DB_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")
SCHEMA_VERSION = 2


def _path(db_path: str | None = None) -> str:
    return DB_PATH if db_path is None else db_path


def _window_predicate(days: int = 0) -> tuple[str, list]:
    """Return a parameterized SQL predicate selecting rows inside the window.

    ``days <= 0`` means all history (no filter); the returned predicate is
    ``"1=1"`` so it can be safely AND-ed into an existing WHERE clause when
    more conditions are needed. For ``days > 0`` the predicate compares
    SQLite-normalized ``datetime(played_at)`` against ``datetime('now', ?)``
    cutoff bound to a single parameter, which is never string-interpolated.
    Wrapping with ``datetime()`` normalizes ISO 8601 ``played_at`` strings
    (``...T...Z``) so the comparison is by real time, not raw byte order.

    The returned tuple is ``(predicate, params)``.
    """
    if days <= 0:
        return ("1=1", [])
    return ("datetime(played_at) >= datetime('now', ?)", [f"-{int(days)} days"])


def _previous_window_predicate(days: int) -> tuple[str, list]:
    """Return a parameterized SQL predicate for the previous equal-length window.

    Only meaningful for finite windows (``days > 0``); for ``days <= 0`` returns
    ``("1=0", [])`` to select nothing (caller must skip comparisons for all
    history).
    """
    if days <= 0:
        return ("1=0", [])
    n = int(days)
    return (
        "datetime(played_at) >= datetime('now', ?) "
        "AND datetime(played_at) < datetime('now', ?)",
        [f"-{n * 2} days", f"-{n} days"],
    )


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    async with db.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


async def _set_schema_version(db: aiosqlite.Connection, version: int) -> None:
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


async def _apply_migrations(db: aiosqlite.Connection) -> None:
    version = await _get_schema_version(db)

    if version < 1:
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_user_track
            ON play_history(username, track_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_played_at
            ON play_history(played_at DESC)
        """)
        await _set_schema_version(db, 1)

    if version < 2:
        existing = await _get_meta_value(db, "retention_days")
        if existing is None:
            await _set_meta_value(db, "retention_days", "permanent")
        await _set_schema_version(db, 2)


async def _get_meta_value(db: aiosqlite.Connection, key: str):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    async with db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", (key,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def _set_meta_value(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        """
        INSERT INTO schema_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


async def init_db(db_path: str | None = None):
    """Initializes the database and creates the play_history table."""
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT,
                username TEXT,
                client_name TEXT,
                track_id TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                is_transcoding INTEGER,
                listen_duration_sec INTEGER
            )
        """)
        await _apply_migrations(db)
        await db.commit()


async def save_play_session(session: dict, db_path: str | None = None):
    """Saves a completed playback session to the database."""
    path = _path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            INSERT INTO play_history (
                played_at, username, client_name, track_id,
                title, artist, album, is_transcoding, listen_duration_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("last_seen_at"),
            session.get("username"),
            session.get("client_name"),
            session.get("track_id"),
            session.get("title"),
            session.get("artist"),
            session.get("album"),
            session.get("is_transcoding"),
            session.get("duration_sec")
        ))
        await db.commit()


async def get_player_stats(days: int = 0, db_path: str | None = None):
    """Returns the distribution of client usage based on play counts.

    ``days <= 0`` selects all history; ``days > 0`` selects records with
    ``played_at`` within the last ``days`` days (UTC, via SQLite cutoff).
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT client_name, COUNT(*) as count
            FROM play_history
            WHERE {pred}
            GROUP BY client_name
            ORDER BY count DESC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_transcoding_stats(days: int = 0, db_path: str | None = None):
    """Returns the ratio of transcoded vs direct play counts.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT is_transcoding, COUNT(*) as count
            FROM play_history
            WHERE {pred}
            GROUP BY is_transcoding
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def ping_db(db_path: str | None = None) -> bool:
    """Returns True when the SQLite database is reachable."""
    path = _path(db_path)
    try:
        async with aiosqlite.connect(path) as db:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        return True
    except Exception:
        return False


async def get_summary(days: int = 0, db_path: str | None = None):
    """Returns aggregate listening statistics for the selected window.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.

    Comparison metrics compare the current window against the previous
    equal-length window:

    * ``active_days`` - count of distinct dates with at least one play in the
      current window.
    * ``average_daily_plays`` / ``average_daily_listen_sec`` - for finite
      windows, divided by ``active_days``; for ``days=0`` (all history),
      divided by the inclusive span from the minimum to the maximum played
      date (or ``null`` if there are no records). ``0`` when ``active_days``
      is zero.
    * ``previous_total_plays`` / ``previous_total_listen_sec`` - aggregates
      over the previous equal-length window (``null`` for all history).
    * ``plays_change_pct`` / ``listen_change_pct`` - percentage change versus
      the previous window; ``null`` when the previous value is zero or the
      comparison is not applicable (``days <= 0``).
    """
    path = _path(db_path)
    cur_pred, cur_params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                COUNT(*) AS total_plays,
                COALESCE(SUM(listen_duration_sec), 0) AS total_listen_sec,
                COUNT(DISTINCT track_id) AS unique_tracks,
                COUNT(DISTINCT client_name) AS client_count,
                COUNT(DISTINCT date(played_at)) AS active_days
            FROM play_history
            WHERE {cur_pred}
            """,
            cur_params,
        ) as cursor:
            row = await cursor.fetchone()

        total_plays = int(row["total_plays"] or 0)
        total_listen_sec = int(row["total_listen_sec"] or 0)
        unique_tracks = int(row["unique_tracks"] or 0)
        client_count = int(row["client_count"] or 0)
        active_days = int(row["active_days"] or 0)

        previous_total_plays: int | None = None
        previous_total_listen_sec: int | None = None
        plays_change_pct: float | None = None
        listen_change_pct: float | None = None
        avg_daily_plays: float | None
        avg_daily_listen_sec: float | None

        if days <= 0:
            denom: int | None = None
            async with db.execute(
                """
                SELECT MIN(date(played_at)) AS mn, MAX(date(played_at)) AS mx
                FROM play_history
                """
            ) as cursor:
                span_row = await cursor.fetchone()
            mn = span_row["mn"] if span_row else None
            mx = span_row["mx"] if span_row else None
            if mn and mx:
                try:
                    span_days = (date.fromisoformat(mx) - date.fromisoformat(mn)).days + 1
                    if span_days > 0:
                        denom = span_days
                except ValueError:
                    denom = None
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
            prev_pred, prev_params = _previous_window_predicate(days)
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
            "window_days": days if days > 0 else None,
        }


async def get_hourly_stats(days: int = 0, db_path: str | None = None):
    """Returns play counts grouped by hour of day (0-23).

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT CAST(strftime("%H", played_at) AS INTEGER) AS hour,
                   COUNT(*) AS count
            FROM play_history
            WHERE {pred}
            GROUP BY hour
            ORDER BY hour ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_daily_stats(days: int = 30, db_path: str | None = None):
    """Returns play counts per day, ordered by date ASC.

    Backward compatible with the original ``days=30`` default behavior.

    * ``days > 0``: rows with ``date(played_at) >= date('now', '-N days')``.
    * ``days <= 0`` (including ``0``): all history.
    """
    path = _path(db_path)
    if days <= 0:
        pred = "1=1"
        params: list = []
    else:
        pred = "date(played_at) >= date('now', ?)"
        params = [f"-{int(days)} days"]
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT date(played_at) AS date,
                   COUNT(*) AS count
            FROM play_history
            WHERE {pred}
            GROUP BY date
            ORDER BY date ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_top_artists(limit: int = 10, days: int = 0, db_path: str | None = None):
    """Returns top artists by play count, ordered by count DESC.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT artist, COUNT(*) AS count
            FROM play_history
            WHERE artist IS NOT NULL AND artist != "" AND ({pred})
            GROUP BY artist
            ORDER BY count DESC
            LIMIT ?
            """,
            [*params, limit],
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_top_albums(limit: int = 10, days: int = 0, db_path: str | None = None):
    """Returns top albums by play count, ordered by count DESC.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT album, COUNT(*) AS count
            FROM play_history
            WHERE album IS NOT NULL AND album != "" AND ({pred})
            GROUP BY album
            ORDER BY count DESC
            LIMIT ?
            """,
            [*params, limit],
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_playback_history(
    limit: int = 10, days: int = 0, db_path: str | None = None
):
    """Returns recent tracks with aggregated play counts.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                ph.username,
                ph.title,
                ph.artist,
                ph.album,
                ph.played_at AS last_played_at,
                agg.play_count,
                agg.total_listen_sec
            FROM (
                SELECT
                    username,
                    track_id,
                    COUNT(*) AS play_count,
                    SUM(listen_duration_sec) AS total_listen_sec,
                    MAX(id) AS latest_id
                FROM play_history
                WHERE {pred}
                GROUP BY username, track_id
            ) agg
            JOIN play_history ph ON ph.id = agg.latest_id
            ORDER BY ph.played_at DESC, agg.play_count DESC
            LIMIT ?
            """,
            [*params, limit],
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
