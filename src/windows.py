"""Local-time window arithmetic and SQL predicate composition.

Timezone names are validated here and never interpolated into SQL; window
bounds are computed on local calendars before UTC conversion so DST
transitions keep their day boundaries.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.schema import LEGACY_SOURCE_ID

TIMEZONE_DEFAULT = "UTC"


def resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    """Resolve an IANA timezone name, normalizing unknown names to ``ValueError``.

    The name is used only for Python date arithmetic, never SQL construction.
    """
    try:
        return ZoneInfo(timezone_name or TIMEZONE_DEFAULT)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def utc_instant(dt: datetime) -> str:
    """Format an aware datetime for SQLite instant comparisons.

    SQLite ``datetime()`` normalizes stored ISO 8601 timestamps to this UTC form.
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _utc_epoch(instant: str) -> int:
    """Convert an internally formatted UTC instant to Unix seconds."""
    parsed = datetime.strptime(instant, "%Y-%m-%d %H:%M:%S")
    return int(parsed.replace(tzinfo=timezone.utc).timestamp())


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
    return (utc_instant(start_dt), utc_instant(end_dt))


def _date_window_bounds(
    start_date: date,
    end_date: date,
    tz: ZoneInfo,
) -> tuple[str, str]:
    """Return UTC bounds for an inclusive local calendar-date range."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    return (utc_instant(start_dt), utc_instant(end_dt))


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
        "played_at_epoch >= ? AND played_at_epoch < ?",
        [_utc_epoch(start), _utc_epoch(end)],
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
        "played_at_epoch >= ? AND played_at_epoch < ?",
        [_utc_epoch(start), _utc_epoch(end)],
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
    if source_id == LEGACY_SOURCE_ID:
        return (
            f"({predicate}) AND ({column} = ? OR {column} IS NULL)",
            [*params, source_id],
        )
    return (
        f"({predicate}) AND {column} = ?",
        [*params, source_id],
    )


def _username_predicate(
    predicate: str,
    params: list,
    username: str | None,
    *,
    column: str = "username",
) -> tuple[str, list]:
    if username is None:
        return predicate, params
    return (
        f"({predicate}) AND {column} = ?",
        [*params, username],
    )


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
