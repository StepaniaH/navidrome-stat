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
    """Resolve an IANA timezone name, normalizing unknown names to ``ValueError``.

    The name is used only for Python date arithmetic, never SQL construction.
    """
    try:
        return ZoneInfo(timezone_name or TIMEZONE_DEFAULT)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def _format_utc(dt: datetime) -> str:
    """Format an aware datetime for SQLite instant comparisons.

    SQLite ``datetime()`` normalizes stored ISO 8601 timestamps to this UTC form.
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _window_bounds(days: int, tz: ZoneInfo) -> tuple[str | None, str | None]:
    """Return UTC bounds for ``[today-(days-1), tomorrow)`` in ``tz``.

    Local-calendar arithmetic happens before UTC conversion, preserving DST
    transitions. ``days <= 0`` returns unbounded values.
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
    """Return UTC bounds for the preceding equal-length local-calendar window.

    Local-date arithmetic avoids a one-hour shift across DST transitions.
    """
    if days <= 0:
        return (None, None)
    today_local = datetime.now(tz).date()
    current_start = today_local - timedelta(days=int(days) - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=int(days) - 1)
    return _date_window_bounds(previous_start, previous_end, tz)


def _window_predicate(
    days: int = 0,
    timezone_name: str = TIMEZONE_DEFAULT,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, list]:
    """Return a parameterized predicate and UTC bounds for a local window.

    All history uses ``("1=1", [])``. Timezone names are validated and never
    interpolated into SQL.
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
    """Return a predicate for the previous equal-length local window.

    All history selects no rows; local-date bounds preserve DST semantics.
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
    """Initialize the schema and recover durable playback checkpoints."""
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
    """Finalize durable checkpoints left by an interrupted process."""

    path = _path(db_path)
    async with connect_db(path) as db:
        recovered = await _recover_incomplete_sessions(db)
        await db.commit()
    return recovered


async def save_play_session(session: dict, db_path: str | None = None):
    """Upsert a playback session by ID, or append when the ID is absent.

    Checkpoint retries and final updates reuse the ID to avoid duplicate rows.
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
    """Return play counts grouped by provenance."""
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
    """Return play counts grouped by configured server."""
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
    """Return client play and listening aggregates for the selected window.

    Results sort by play count and client name. Window bounds follow the
    requested local calendar; timezone names are never interpolated into SQL.
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
    """Return play and listen-time aggregates by transcoding mode.

    Percentages are rounded to two decimals and use zero for empty totals.
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
    """Return whether the SQLite database is reachable."""
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
    """Return non-empty local-hour buckets in ascending order.

    Stored timestamps remain UTC; timezone conversion controls window and
    bucket boundaries.
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
    """Return the local date for a stored UTC timestamp, or None if invalid."""
    local = _played_at_to_local_datetime(played_at, tz)
    return local.date() if local is not None else None


def _local_date_range(
    days: int,
    tz: ZoneInfo,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[date | None, date | None]:
    """Return the requested or derived finite local-date range."""
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
    """Return zero-filled local-date buckets in ascending order.

    Finite windows cover every requested date; all history spans the earliest
    through latest play. Bucketing converts stored UTC timestamps to local time.
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
    """Return a zero-filled 7 by 24 local weekday/hour grid.

    Weekdays follow ``date.weekday()`` (Monday=0); stored UTC timestamps are
    converted to the requested timezone before bucketing.
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
    """Return artists ranked by plays or listen time for the selected window.

    ``value`` contains the selected metric; ties sort by artist name. Metric
    values map to fixed SQL expressions and timezone bounds stay parameterized.
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
    """Return albums ranked by plays or listen time for the selected window."""
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
        raise ValueError(f"unknown ranking metric: {metric!r}")

    # SQLite cannot reuse a SELECT alias elsewhere in the same SELECT list.
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
    """Return recent tracks with aggregated play counts for the selected window."""
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
