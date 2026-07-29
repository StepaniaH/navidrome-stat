import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite

from src.sqlite import connect_db

DB_PATH = os.getenv("DATABASE_URL", "navidrome_stats.db")
SCHEMA_VERSION = 7
LEGACY_SOURCE_ID = "legacy"
LEGACY_SOURCE_NAME = "Legacy environment source"

TIMEZONE_DEFAULT = "UTC"


def _path(db_path: str | None = None) -> str:
    return DB_PATH if db_path is None else db_path


def resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    """Resolve a user-supplied timezone name to a ``ZoneInfo`` instance.

    Raises ``ValueError`` on unknown names (``zoneinfo.ZoneInfoNotFoundError``
    is a ``KeyError`` subclass, so it is normalized to ``ValueError`` here;
    callers translate this to HTTP 422). Never accept arbitrary SQL fragments
    here; the value is only used for Python date math.
    """
    try:
        return ZoneInfo(timezone_name or TIMEZONE_DEFAULT)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def _format_utc(dt: datetime) -> str:
    """Format a timezone-aware datetime as a UTC ``YYYY-MM-DD HH:MM:SS`` string.

    SQLite ``datetime()`` normalizes ISO 8601 ``played_at`` strings (including
    ``...T...Z``) to UTC. Returning the bound in the same canonical form keeps
    comparisons by real time, independent of byte order or local timezone.
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _window_bounds(days: int, tz: ZoneInfo) -> tuple[str | None, str | None]:
    """Return UTC cutoff strings for ``[today-(days-1), today+1)`` in ``tz``.

    ``days <= 0`` returns ``(None, None)`` (all history, no filter). The upper
    bound is exclusive (start of tomorrow) so the window covers every play on
    today's local date. Both bounds are computed as timezone-aware datetimes
    in ``tz`` and converted to UTC before formatting; SQLite never sees the
    user timezone name and never relies on its local time mode.
    """
    if days <= 0:
        return (None, None)
    today_local = datetime.now(tz).date()
    start_local = today_local - timedelta(days=int(days) - 1)
    start_dt = datetime.combine(start_local, time.min, tzinfo=tz)
    end_dt = datetime.combine(today_local + timedelta(days=1), time.min, tzinfo=tz)
    return (_format_utc(start_dt), _format_utc(end_dt))


def _date_window_bounds(
    start_date: date,
    end_date: date,
    tz: ZoneInfo,
) -> tuple[str, str]:
    """Return UTC bounds for an inclusive local calendar-date range."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    return (_format_utc(start_dt), _format_utc(end_dt))


def _previous_window_bounds(days: int, tz: ZoneInfo) -> tuple[str | None, str | None]:
    """Return UTC cutoff strings for the previous equal-length window.

    Only meaningful for finite windows (``days > 0``); returns ``(None, None)``
    otherwise. The previous window is ``[start - N days, start)`` in UTC, where
    ``start`` is the current window's lower bound.
    """
    if days <= 0:
        return (None, None)
    cur_start, cur_end = _window_bounds(days, tz)
    if cur_start is None or cur_end is None:
        return (None, None)
    start_dt = datetime.strptime(cur_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(cur_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    span = end_dt - start_dt
    prev_start = start_dt - span
    return (_format_utc(prev_start), _format_utc(start_dt))


def _window_predicate(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, list]:
    """Return a parameterized SQL predicate selecting rows inside the window.

    ``days <= 0`` means all history (no filter); the returned predicate is
    ``"1=1"`` so it can be safely AND-ed into an existing WHERE clause when
    more conditions are needed. For ``days > 0`` the predicate compares
    SQLite-normalized ``datetime(played_at)`` against two UTC cutoff strings
    computed from the requested timezone, so date/hour bucket boundaries
    follow the user's local calendar rather than SQLite's local time mode.
    ``timezone_name`` is validated via ``ZoneInfo`` before being used and is
    never string-interpolated into SQL.

    The returned tuple is ``(predicate, params)``.
    """
    if start_date is not None and end_date is not None:
        start, end = _date_window_bounds(
            start_date,
            end_date,
            resolve_timezone(timezone_name),
        )
    elif days <= 0:
        return ("1=1", [])
    else:
        start, end = _window_bounds(days, resolve_timezone(timezone_name))
    return (
        "datetime(played_at) >= ? AND datetime(played_at) < ?",
        [start, end],
    )


def _previous_window_predicate(
    days: int,
    timezone_name: str = TIMEZONE_DEFAULT,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, list]:
    """Return a parameterized SQL predicate for the previous equal-length window.

    Only meaningful for finite windows (``days > 0``); for ``days <= 0`` returns
    ``("1=0", [])`` to select nothing (caller must skip comparisons for all
    history). Bounds are computed in the requested timezone (see
    ``_previous_window_bounds``).
    """
    if start_date is not None and end_date is not None:
        tz = resolve_timezone(timezone_name)
        span_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span_days - 1)
        start, end = _date_window_bounds(previous_start, previous_end, tz)
    elif days <= 0:
        return ("1=0", [])
    else:
        start, end = _previous_window_bounds(days, resolve_timezone(timezone_name))
    if start is None or end is None:
        return ("1=0", [])
    return (
        "datetime(played_at) >= ? AND datetime(played_at) < ?",
        [start, end],
    )


def _source_predicate(
    predicate: str,
    params: list,
    source_id: str | None,
    *,
    column: str = "source_id",
) -> tuple[str, list]:
    if source_id is None:
        return predicate, params
    return (
        f"({predicate}) AND COALESCE({column}, ?) = ?",
        [*params, LEGACY_SOURCE_ID, source_id],
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

    if version < 3:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT,
                username TEXT,
                client_name TEXT,
                track_id TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                is_transcoding INTEGER,
                duration_sec INTEGER NOT NULL,
                outcome TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_attempts_played_at
            ON play_attempts(played_at DESC)
        """)
        await _set_schema_version(db, 3)

    if version < 4:
        await db.execute("ALTER TABLE play_history ADD COLUMN source TEXT NOT NULL DEFAULT 'poller'")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_play_history_source ON play_history(source)")
        await _set_schema_version(db, 4)

    if version < 5:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "source_id" not in columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN source_id TEXT")
        if "source_name" not in columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN source_name TEXT")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT, username TEXT, client_name TEXT, track_id TEXT,
                title TEXT, artist TEXT, album TEXT, is_transcoding INTEGER,
                duration_sec INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL DEFAULT 'short_play'
            )
        """)
        async with db.execute("PRAGMA table_info(play_attempts)") as cursor:
            attempt_columns = {row[1] for row in await cursor.fetchall()}
        if "source_id" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN source_id TEXT")
        if "source_name" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN source_name TEXT")
        await db.execute(
            "UPDATE play_history SET source_id = ?, source_name = ? "
            "WHERE source_id IS NULL OR source_id = ''",
            (LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME),
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_play_history_source_id ON play_history(source_id)")
        await _set_schema_version(db, 5)

    if version < 6:
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            history_columns = {row[1] for row in await cursor.fetchall()}
        if "session_id" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN session_id TEXT")
        if "duration_confidence" not in history_columns:
            await db.execute(
                "ALTER TABLE play_history ADD COLUMN "
                "duration_confidence TEXT NOT NULL DEFAULT 'estimated'"
            )
        if "finalized" not in history_columns:
            await db.execute(
                "ALTER TABLE play_history ADD COLUMN finalized INTEGER NOT NULL DEFAULT 1"
            )
        if "finalized_at" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN finalized_at TEXT")

        async with db.execute("PRAGMA table_info(play_attempts)") as cursor:
            attempt_columns = {row[1] for row in await cursor.fetchall()}
        if "attempt_id" not in attempt_columns:
            await db.execute("ALTER TABLE play_attempts ADD COLUMN attempt_id TEXT")
        if "duration_confidence" not in attempt_columns:
            await db.execute(
                "ALTER TABLE play_attempts ADD COLUMN "
                "duration_confidence TEXT NOT NULL DEFAULT 'estimated'"
            )

        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_history_session_id
            ON play_history(session_id)
            WHERE session_id IS NOT NULL
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_play_attempts_attempt_id
            ON play_attempts(attempt_id)
            WHERE attempt_id IS NOT NULL
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_source_user_track
            ON play_history(source_id, username, track_id)
        """)
        await _set_schema_version(db, 6)

    if version < 7:
        async with db.execute("PRAGMA table_info(play_history)") as cursor:
            history_columns = {row[1] for row in await cursor.fetchall()}
        if "checkpointed_at" not in history_columns:
            await db.execute("ALTER TABLE play_history ADD COLUMN checkpointed_at TEXT")
        await _set_schema_version(db, 7)


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
    async with connect_db(path, initialize=True) as db:
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
        await _recover_incomplete_sessions(db)
        await db.commit()


async def _recover_incomplete_sessions(db: aiosqlite.Connection) -> int:
    """Finalize durable checkpoints left by an earlier interrupted process."""

    cursor = await db.execute(
        """
        UPDATE play_history
        SET finalized = 1,
            finalized_at = COALESCE(checkpointed_at, played_at)
        WHERE session_id IS NOT NULL AND finalized = 0
        """
    )
    return max(cursor.rowcount, 0)


async def recover_incomplete_sessions(db_path: str | None = None) -> int:
    """Public maintenance hook used by tests and operational tooling."""

    path = _path(db_path)
    async with connect_db(path) as db:
        recovered = await _recover_incomplete_sessions(db)
        await db.commit()
    return recovered


async def save_play_session(session: dict, db_path: str | None = None):
    """Insert or update one playback session by its privacy-safe random ID.

    Older/imported callers may omit ``session_id`` and retain append-only
    behavior. Poller sessions always provide an ID, allowing the threshold
    checkpoint and final duration update to be retried without duplicate rows.
    """
    path = _path(db_path)
    async with connect_db(path) as db:
        columns = (
            "played_at, username, client_name, track_id, title, artist, album, "
            "is_transcoding, listen_duration_sec, source, source_id, source_name, "
            "session_id, duration_confidence, finalized, finalized_at, checkpointed_at"
        )
        values = (
            session.get("last_seen_at"),
            session.get("username"),
            session.get("client_name"),
            session.get("track_id"),
            session.get("title"),
            session.get("artist"),
            session.get("album"),
            session.get("is_transcoding"),
            session.get("duration_sec"),
            session.get("source", "poller"),
            session.get("source_id", LEGACY_SOURCE_ID),
            session.get("source_name", LEGACY_SOURCE_NAME),
            session.get("session_id"),
            session.get("duration_confidence", "estimated"),
            int(bool(session.get("finalized", False))),
            session.get("finalized_at"),
            session.get("checkpointed_at", session.get("last_seen_at")),
        )
        if session.get("session_id"):
            await db.execute(
                f"""
                INSERT INTO play_history ({columns})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) WHERE session_id IS NOT NULL DO UPDATE SET
                    played_at=excluded.played_at,
                    username=excluded.username,
                    client_name=excluded.client_name,
                    track_id=excluded.track_id,
                    title=excluded.title,
                    artist=excluded.artist,
                    album=excluded.album,
                    is_transcoding=excluded.is_transcoding,
                    listen_duration_sec=excluded.listen_duration_sec,
                    source=excluded.source,
                    source_id=excluded.source_id,
                    source_name=excluded.source_name,
                    duration_confidence=excluded.duration_confidence,
                    finalized=excluded.finalized,
                    finalized_at=excluded.finalized_at,
                    checkpointed_at=excluded.checkpointed_at
                """,
                values,
            )
        else:
            await db.execute(
                f"""
                INSERT INTO play_history ({columns})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        await db.commit()


async def save_play_attempt(attempt: dict, db_path: str | None = None):
    """Save a below-threshold playback attempt without counting it as a play."""
    path = _path(db_path)
    async with connect_db(path) as db:
        await db.execute("""
            INSERT INTO play_attempts (
                played_at, username, client_name, track_id, title, artist,
                album, is_transcoding, duration_sec, outcome, source_id, source_name,
                attempt_id, duration_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id) WHERE attempt_id IS NOT NULL DO UPDATE SET
                played_at=excluded.played_at,
                duration_sec=excluded.duration_sec,
                duration_confidence=excluded.duration_confidence
        """, (
            attempt.get("last_seen_at"), attempt.get("username"),
            attempt.get("client_name"), attempt.get("track_id"),
            attempt.get("title"), attempt.get("artist"), attempt.get("album"),
            attempt.get("is_transcoding"), int(attempt.get("duration_sec", 0)),
            attempt.get("outcome", "short_play"),
            attempt.get("source_id", LEGACY_SOURCE_ID),
            attempt.get("source_name", LEGACY_SOURCE_NAME),
            attempt.get("session_id"),
            attempt.get("duration_confidence", "estimated"),
        ))
        await db.commit()


async def get_short_play_stats(days: int = 0, timezone_name: str = TIMEZONE_DEFAULT,
                               db_path: str | None = None,
                               source_id: str | None = None):
    """Return short-play counts and rate; this is not a skip-rate claim."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name)
    pred, params = _source_predicate(pred, params, source_id)
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
                           source_id: str | None = None):
    """Return formal play counts grouped by provenance source."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name)
    pred, params = _source_predicate(pred, params, source_id)
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
                           end_date: date | None = None):
    """Return formal play counts grouped by configured server identity."""
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    where, params = _source_predicate(pred, params, source_id, column="ph.source_id")
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


async def list_servers(db_path: str | None = None):
    path = _path(db_path)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, display_name, url, username, password, enabled FROM servers ORDER BY created_at, id") as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_server(server_id: str, db_path: str | None = None):
    rows = await list_servers(db_path)
    return next((row for row in rows if row["id"] == server_id), None)


async def save_server(server: dict, db_path: str | None = None) -> None:
    path = _path(db_path)
    now = datetime.now(timezone.utc).isoformat()
    async with connect_db(path) as db:
        await db.execute("""
            INSERT INTO servers (id, display_name, url, username, password, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                url=excluded.url, username=excluded.username, password=excluded.password,
                enabled=excluded.enabled, updated_at=excluded.updated_at
        """, (server["id"], server["display_name"], server["url"], server["username"],
              server["password"], int(server.get("enabled", True)), now, now))
        await db.commit()


async def delete_server(server_id: str, db_path: str | None = None) -> bool:
    path = _path(db_path)
    async with connect_db(path) as db:
        cursor = await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_player_stats(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Returns the distribution of client usage based on play counts.

    Each row is ``{client_name, count, total_listen_sec, average_listen_sec,
    transcoded_count, transcoding_rate_pct}``. ``client_name`` and ``count``
    preserve the historical contract; the additional fields are sourced from
    ``listen_duration_sec`` and ``is_transcoding`` already stored on each row
    (no schema change). Ordering is ``count DESC, client_name ASC`` so empty
    and ``null`` client names sort deterministically above any non-empty name.

    ``days <= 0`` selects all history; ``days > 0`` selects records with
    ``played_at`` within the window bounds (UTC) derived from the requested
    timezone's local calendar. The timezone value is validated via
    ``ZoneInfo`` and never string-interpolated into SQL.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
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
):
    """Returns the ratio of transcoded vs direct play counts plus listen time.

    Each row is ``{is_transcoding, count, total_listen_sec, plays_pct,
    listen_sec_pct}``. ``is_transcoding`` and ``count`` preserve the historical
    contract. ``total_listen_sec`` is the sum of ``listen_duration_sec`` for
    rows in this mode; ``plays_pct`` is the share of plays in this mode and
    ``listen_sec_pct`` is the share of listen time. Both percentages are
    rounded to 2 decimals and ``0`` when the respective denominator is zero.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``
    using UTC bounds derived from the requested timezone's local calendar.
    The timezone value is validated via ``ZoneInfo`` and never
    string-interpolated into SQL.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
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


async def ping_db(db_path: str | None = None) -> bool:
    """Returns True when the SQLite database is reachable."""
    path = _path(db_path)
    try:
        async with connect_db(path) as db:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        return True
    except Exception:
        return False


async def get_summary(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
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
    tz = resolve_timezone(timezone_name)
    cur_pred, cur_params = _window_predicate(
        days,
        timezone_name,
        start_date,
        end_date,
    )
    cur_pred, cur_params = _source_predicate(cur_pred, cur_params, source_id)
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
):
    """Returns play counts grouped by local hour of day (0-23).

    Hours are taken in the requested timezone, not the stored UTC value; this
    matches the heatmap and daily semantics where timezone controls bucket
    boundaries. Only hours present in the data are returned (no zero-fill),
    ordered by hour ascending, preserving the historical shape of the
    endpoint. ``days <= 0`` selects all history; ``days > 0`` selects a finite
    window whose UTC bounds are derived from the requested timezone's local
    calendar.

    The user timezone value is never string-interpolated into SQL and is
    validated via ``ZoneInfo``.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
    )
    return buckets["hourly"]


def _played_at_to_local_datetime(
    played_at: str,
    tz: ZoneInfo,
) -> datetime | None:
    if not played_at:
        return None
    raw = played_at.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(played_at[:19], "%Y-%m-%dT%H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _played_at_to_local_date(played_at: str, tz: ZoneInfo) -> date | None:
    """Convert a stored UTC ``played_at`` ISO string to a local ``date`` in ``tz``.

    Returns ``None`` when the value cannot be parsed. Stored timestamps remain
    UTC; the timezone only controls date/hour/weekday bucket boundaries here.
    """
    local = _played_at_to_local_datetime(played_at, tz)
    return local.date() if local is not None else None


def _local_date_range(
    days: int,
    tz: ZoneInfo,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[date | None, date | None]:
    """Return ``(start_date, end_date)`` for finite windows, both local in ``tz``.

    For ``days <= 0`` returns ``(None, None)``; the caller derives the all-history
    range from the database itself.
    """
    if start_date is not None and end_date is not None:
        return (start_date, end_date)
    if days <= 0:
        return (None, None)
    today = datetime.now(tz).date()
    return (today - timedelta(days=int(days) - 1), today)


async def get_time_bucket_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, list[dict]]:
    """Build hourly, daily and weekday/hour buckets from one SQLite scan."""

    path = _path(db_path)
    tz = resolve_timezone(timezone_name)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
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


async def get_daily_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
):
    """Returns play counts per local day, ordered by date ASC, zero-filled.

    * ``days > 0``: every calendar date in ``[today-(days-1), today]`` in the
      requested timezone is included with at least count 0, ordered ascending.
    * ``days <= 0`` (all history): every date from the earliest local played
      date to the latest local played date is included, zero-filled. An empty
      table returns ``[]``.

    Stored ``played_at`` timestamps remain UTC; only bucket boundaries shift
    with the timezone. The user timezone value is never string-interpolated
    into SQL and is validated via ``ZoneInfo``.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
    )
    return buckets["daily"]


WEEKDAY_HOUR_WEEKDAY_COUNT = 7
WEEKDAY_HOUR_HOUR_COUNT = 24
WEEKDAY_HOUR_CELL_COUNT = WEEKDAY_HOUR_WEEKDAY_COUNT * WEEKDAY_HOUR_HOUR_COUNT


async def get_weekday_hour_stats(
    days: int = 30,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
):
    """Returns play counts for every weekday x hour cell (7 x 24 = 168 rows).

    Each row is ``{"weekday": 0..6, "hour": 0..23, "count": int}``. The grid is
    fully zero-filled so consumers can render a complete heatmap regardless of
    data presence. Weekday convention follows Python's ``date.weekday()``: 0 =
    Monday ... 6 = Sunday. Stored timestamps remain UTC; the timezone only
    controls bucket boundaries (weekday and hour are taken in the requested
    timezone). All-history (``days <= 0``) aggregates every row; finite windows
    filter by UTC bounds derived from the timezone's local calendar.

    The user timezone value is never string-interpolated into SQL and is
    validated via ``ZoneInfo``.
    """
    buckets = await get_time_bucket_stats(
        days=days,
        timezone_name=timezone_name,
        db_path=db_path,
        source_id=source_id,
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
):
    """Returns top artists ranked by ``metric`` over the selected window.

    Each row is ``{artist, count, total_listen_sec, value}``:

    * ``count`` is the play count (rows in the window for this artist) and
      preserves the historical contract;
    * ``total_listen_sec`` is the sum of ``listen_duration_sec`` for this
      artist, used to render a secondary "12 次 · 3h 42m" line;
    * ``value`` is ``count`` for ``metric="plays"`` and ``total_listen_sec``
      for ``metric="listen_time"`` so the frontend can compute bar widths
      from a single field.

    Ordering is deterministic: ``value DESC, artist ASC``. Empty and ``null``
    artists are excluded (matches the historical contract).

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``
    using UTC bounds derived from the requested timezone's local calendar.
    The timezone and metric values are validated by ``src.main`` before being
    passed here and are never string-interpolated into SQL.
    """
    return await _get_top_entity(
        entity_column="artist",
        limit=limit,
        days=days,
        timezone_name=timezone_name,
        metric=metric,
        db_path=db_path,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
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
):
    """Returns top albums ranked by ``metric`` over the selected window.

    Same contract as ``get_top_artists`` with ``album`` in place of
    ``artist``; empty and ``null`` albums are excluded.
    """
    return await _get_top_entity(
        entity_column="album",
        limit=limit,
        days=days,
        timezone_name=timezone_name,
        metric=metric,
        db_path=db_path,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
    )


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
):
    if metric not in ("plays", "listen_time"):
        # Defensive: callers should validate; reject defensively rather than
        # silently fall back to a different ranking.
        raise ValueError(f"unknown ranking metric: {metric!r}")

    # ``value`` mirrors the selected metric so the frontend can render bar
    # widths without branching. The expression is repeated (rather than
    # reusing the ``count``/``total_listen_sec`` aliases) because SQLite does
    # not allow SELECT-list aliases to be referenced in other SELECT-list
    # expressions. ``ORDER BY value`` does resolve the alias.
    if metric == "plays":
        value_expr = "COUNT(*)"
    else:
        value_expr = "COALESCE(SUM(listen_duration_sec), 0)"

    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                {entity_column} AS name,
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

    return [{
        entity_column: row["name"],
        "count": int(row["count"] or 0),
        "total_listen_sec": int(row["total_listen_sec"] or 0),
        "value": int(row["value"] or 0),
    } for row in rows]


async def get_playback_history(
    limit: int = 10,
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    db_path: str | None = None,
    source_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Returns recent tracks with aggregated play counts.

    ``days <= 0`` selects all history; ``days > 0`` selects the last ``days``
    using UTC bounds derived from the requested timezone's local calendar.
    The timezone value is validated via ``ZoneInfo`` and never
    string-interpolated into SQL.
    """
    path = _path(db_path)
    pred, params = _window_predicate(days, timezone_name, start_date, end_date)
    pred, params = _source_predicate(pred, params, source_id)
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT
                ph.username,
                ph.title,
                ph.artist,
                ph.album,
                ph.played_at AS last_played_at,
                COALESCE(ph.source_id, ?) AS source_id,
                COALESCE(ph.source_name, ?) AS source_name,
                agg.play_count,
                agg.total_listen_sec
            FROM (
                SELECT
                    username,
                    track_id,
                    COALESCE(source_id, ?) AS source_id,
                    COUNT(*) AS play_count,
                    SUM(listen_duration_sec) AS total_listen_sec,
                    MAX(id) AS latest_id
                FROM play_history
                WHERE {pred}
                GROUP BY COALESCE(source_id, ?), username, track_id
            ) agg
            JOIN play_history ph ON ph.id = agg.latest_id
            ORDER BY ph.played_at DESC, agg.play_count DESC
            LIMIT ?
            """,
            [
                LEGACY_SOURCE_ID,
                LEGACY_SOURCE_NAME,
                LEGACY_SOURCE_ID,
                *params,
                LEGACY_SOURCE_ID,
                limit,
            ],
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
