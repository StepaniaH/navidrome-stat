from typing import Optional

from pydantic import BaseModel


HISTORY_LIMIT_DEFAULT = 10
HISTORY_LIMIT_MIN = 1
HISTORY_LIMIT_MAX = 100

TOP_LIMIT_DEFAULT = 10
TOP_LIMIT_MIN = 1
TOP_LIMIT_MAX = 50

DAILY_DAYS_DEFAULT = 30
DAILY_DAYS_MIN = 7
DAILY_DAYS_MAX = 90

# Unified dashboard statistics window contract.
#
# `days` API query form uses these bounds:
#   - 0 (STATS_DAYS_ALL): all history, no WHERE filter
#   - finite window: STATS_DAYS_MIN..STATS_DAYS_MAX (7..90)
# Any other value (e.g. 1..6 or >90) must be rejected with HTTP 422.
STATS_DAYS_ALL = 0
STATS_DAYS_MIN = 7
STATS_DAYS_MAX = 90
STATS_DAYS_DEFAULT = 30
STATS_DAYS_PRESETS = (7, 30, 90, 0)

# Timezone query parameter contract. The default ``UTC`` matches the historical
# backend behavior, so existing callers that omit ``timezone`` keep seeing the
# same window/bucket boundaries. The value is validated against Python's
# stdlib ``zoneinfo.ZoneInfo`` (no new dependency); invalid names return 422.
# Timezone only controls date/hour/weekday bucket boundaries and finite-window
# UTC cutoff computation; timestamps are always stored as UTC ISO strings.
TIMEZONE_DEFAULT = "UTC"
TIMEZONE_VALIDATION_ERROR = "timezone must be a valid IANA timezone name"

# Ranking metric contract for ``/api/stats/top-artists`` and
# ``/api/stats/top-albums``. ``plays`` (default) keeps the historical
# ordering by play count; ``listen_time`` ranks by total observed listen
# seconds. ``value`` is the ranking key for the requested metric (count for
# ``plays``, seconds for ``listen_time``) so the frontend can compute bar
# widths without branching on the metric. rankings are deterministically
# ordered by ``value DESC, name ASC``. ``total_listen_sec`` is always
# provided for the secondary "12 次 · 3h 42m" line and is independent of the
# selected metric. This does not change playback/session semantics or the
# stored data; it only re-reads ``listen_duration_sec`` for aggregation.
RANKING_METRIC_PLAYS = "plays"
RANKING_METRIC_LISTEN_TIME = "listen_time"
RANKING_METRIC_DEFAULT = RANKING_METRIC_PLAYS
RANKING_METRICS = (RANKING_METRIC_PLAYS, RANKING_METRIC_LISTEN_TIME)
RANKING_METRIC_VALIDATION_ERROR = (
    "metric must be one of: plays, listen_time"
)


class PlayerStat(BaseModel):
    client_name: Optional[str] = None
    count: int
    # Extended client distribution fields. All optional so callers that only
    # read ``client_name``/``count`` keep working. ``total_listen_sec`` is the
    # sum of ``listen_duration_sec`` for this client; ``average_listen_sec``
    # is per-play mean; ``transcoded_count`` is plays with ``is_transcoding=1``
    # and ``transcoding_rate_pct`` is ``transcoded_count / count * 100``
    # rounded to 2 decimals (``0`` when ``count == 0``). Ordering is
    # ``count DESC, client_name ASC`` (null client_name sorts as "").
    total_listen_sec: Optional[int] = None
    average_listen_sec: Optional[float] = None
    transcoded_count: Optional[int] = None
    transcoding_rate_pct: Optional[float] = None


class TranscodingStat(BaseModel):
    is_transcoding: Optional[int] = None
    count: int
    # Extended transcoding fields. All optional so callers that only read
    # ``is_transcoding``/``count`` keep working. ``total_listen_sec`` is the
    # sum of ``listen_duration_sec`` for rows in this mode; ``plays_pct`` is
    # the share of plays in this mode (``count / total_plays * 100``) and
    # ``listen_sec_pct`` is the share of listen time
    # (``total_listen_sec / total_listen_sec_all * 100``), both rounded to 2
    # decimals and ``0`` when the respective denominator is zero.
    total_listen_sec: Optional[int] = None
    plays_pct: Optional[float] = None
    listen_sec_pct: Optional[float] = None


class SummaryStat(BaseModel):
    # Existing required totals (backward compatible).
    total_plays: int
    total_listen_sec: int
    unique_tracks: int
    client_count: int
    # Unified-window comparison metrics. All optional so existing callers that
    # only supply the four totals above still validate against this model.
    active_days: Optional[int] = None
    average_daily_plays: Optional[float] = None
    average_daily_listen_sec: Optional[float] = None
    previous_total_plays: Optional[int] = None
    previous_total_listen_sec: Optional[int] = None
    # Percentage changes vs the previous equal-length window. null when the
    # previous value is zero or the comparison is not applicable (days=0).
    plays_change_pct: Optional[float] = None
    listen_change_pct: Optional[float] = None
    # Echo of the requested window: ``days`` for finite windows, ``null`` for
    # all history (days=0).
    window_days: Optional[int] = None


class HourlyStat(BaseModel):
    hour: int
    count: int


class DailyStat(BaseModel):
    date: str
    count: int


class WeekdayHourStat(BaseModel):
    # Weekday convention follows Python ``date.weekday()``: 0=Monday .. 6=Sunday.
    weekday: int
    # Hour of local time in the requested timezone, 0..23 (no leading zeros).
    hour: int
    count: int


class ShortPlayStats(BaseModel):
    short_count: int
    counted_count: int
    attempt_count: int
    short_listen_sec: int
    short_play_rate_pct: float


class SourceStat(BaseModel):
    source: str
    count: int
    total_listen_sec: int


class TopArtistItem(BaseModel):
    artist: str
    count: int
    # Ranking additions. ``total_listen_sec`` is the sum of
    # ``listen_duration_sec`` for this artist; ``value`` is the ranking key
    # for the requested ``metric`` (count for ``plays``, seconds for
    # ``listen_time``). Both optional so existing callers that only read
    # ``artist``/``count`` keep validating.
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None


class TopAlbumItem(BaseModel):
    album: str
    count: int
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None


class HistoryItem(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    play_count: int
    last_played_at: Optional[str] = None
    total_listen_sec: Optional[int] = None


class HealthLiveResponse(BaseModel):
    status: str


class ReadinessChecks(BaseModel):
    database: str
    polling_task: str
    upstream: str


class ReadinessMetrics(BaseModel):
    poll_success_total: int
    poll_failure_total: int
    save_success_total: int
    save_failure_total: int
    active_sessions: int
    seconds_since_last_poll: Optional[int] = None
    last_upstream_error_code: Optional[int] = None


class ReadinessResponse(BaseModel):
    status: str
    checks: ReadinessChecks
    metrics: ReadinessMetrics


class LoginRequest(BaseModel):
    token: str


class AuthStatusResponse(BaseModel):
    auth_required: bool


class PrivacySettingsResponse(BaseModel):
    retention_days: Optional[int] = None
    permanent: bool = True


class PrivacySettingsUpdate(BaseModel):
    retention_days: Optional[int] = None


class RetentionPreviewResponse(BaseModel):
    records_to_delete: int
    retention_days: Optional[int] = None
    database_bytes: int
    total_records: int
    estimated_data_bytes: int
    bytes_to_delete: int = 0
    estimated_database_bytes_after: int


class StorageStatsResponse(BaseModel):
    database_bytes: int
    total_records: int
    estimated_data_bytes: int


class RetentionApplyResponse(BaseModel):
    deleted: int
    retention_days: Optional[int] = None


class UserSummary(BaseModel):
    username: str
    record_count: int


class UserDeletePreviewResponse(BaseModel):
    records_to_delete: int


class UserDeleteResponse(BaseModel):
    deleted: int


class UserImportRequest(BaseModel):
    payload: dict
    merge: bool = True


class UserImportResponse(BaseModel):
    imported: int
    merge: bool


class ConfirmRequest(BaseModel):
    confirm: bool = False


class NowPlayingItem(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    client_name: Optional[str] = None
    seconds_elapsed: int


class SourceConfigResponse(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password_configured: bool = False


class SourceConfigUpdate(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class SourceTestRequest(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class SourceTestResponse(BaseModel):
    ok: bool
    message: str
