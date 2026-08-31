from typing import Literal, Optional

from pydantic import BaseModel, Field

HISTORY_LIMIT_DEFAULT = 10
HISTORY_LIMIT_MIN = 1
HISTORY_LIMIT_MAX = 100

TOP_LIMIT_DEFAULT = 10
TOP_LIMIT_MIN = 1
TOP_LIMIT_MAX = 50

DAILY_DAYS_DEFAULT = 30
DAILY_DAYS_MIN = 7
DAILY_DAYS_MAX = 90

# `days=0` selects all history; finite windows accept 7 through 90 days.
STATS_DAYS_ALL = 0
STATS_DAYS_MIN = 7
STATS_DAYS_MAX = 90
STATS_DAYS_DEFAULT = 30
STATS_DAYS_PRESETS = (7, 30, 90, 0)

# Timezones affect bucket boundaries and finite windows; timestamps remain UTC.
TIMEZONE_DEFAULT = "UTC"
TIMEZONE_VALIDATION_ERROR = "timezone must be a valid IANA timezone name"

# `value` mirrors the selected sort key so one frontend renderer handles both metrics.
RANKING_METRIC_PLAYS = "plays"
RANKING_METRIC_LISTEN_TIME = "listen_time"
RANKING_METRIC_DEFAULT = RANKING_METRIC_PLAYS
RANKING_METRICS = (RANKING_METRIC_PLAYS, RANKING_METRIC_LISTEN_TIME)
RANKING_METRIC_VALIDATION_ERROR = (
    "metric must be one of: plays, listen_time"
)

SUBSONIC_AUTH_ERROR_CODES = frozenset({40, 41, 42, 43, 44, 50})

ConnectionFailureCategory = Literal[
    "auth_failed",
    "tls_error",
    "timeout",
    "network_unreachable",
    "upstream_error",
    "invalid_response",
    "unknown",
]
ConnectionTestCategory = Literal["ok", "incomplete", ConnectionFailureCategory]
ConnectionDiagnosticCategory = Literal[
    "unconfigured",
    "disabled",
    "starting",
    "collector_degraded",
    "connected_no_plays",
    "ready",
    ConnectionFailureCategory,
]


class PlayerStat(BaseModel):
    client_name: Optional[str] = None
    count: int
    total_listen_sec: Optional[int] = None
    average_listen_sec: Optional[float] = None
    transcoded_count: Optional[int] = None
    transcoding_rate_pct: Optional[float] = None


class TranscodingStat(BaseModel):
    is_transcoding: Optional[int] = None
    count: int
    total_listen_sec: Optional[int] = None
    plays_pct: Optional[float] = None
    listen_sec_pct: Optional[float] = None


class SummaryStat(BaseModel):
    total_plays: int
    total_listen_sec: int
    unique_tracks: int
    client_count: int
    active_days: Optional[int] = None
    average_daily_plays: Optional[float] = None
    average_daily_listen_sec: Optional[float] = None
    previous_total_plays: Optional[int] = None
    previous_total_listen_sec: Optional[int] = None
    # Null when the previous value is zero or all history is selected.
    plays_change_pct: Optional[float] = None
    listen_change_pct: Optional[float] = None
    window_days: Optional[int] = None


class HourlyStat(BaseModel):
    hour: int
    count: int


class DailyStat(BaseModel):
    date: str
    count: int


class WeekdayHourStat(BaseModel):
    # Python date.weekday(): Monday=0 through Sunday=6.
    weekday: int
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
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None
    artist_id: Optional[str] = None


class TopAlbumItem(BaseModel):
    album: str
    artist: Optional[str] = None
    count: int
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None
    album_id: Optional[str] = None
    source_id: Optional[str] = None


class EntityTrendPoint(BaseModel):
    date: str
    play_count: int
    total_listen_sec: int


class EntityTrackItem(BaseModel):
    track_id: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    play_count: int
    total_listen_sec: int
    last_played_at: Optional[str] = None
    source_id: Optional[str] = None
    source_name: Optional[str] = None


class EntityRecentPlayItem(BaseModel):
    played_at: Optional[str] = None
    username: Optional[str] = None
    client_name: Optional[str] = None
    track_id: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    listen_duration_sec: int
    source_id: Optional[str] = None
    source_name: Optional[str] = None


class EntityDetailResponse(BaseModel):
    entity_type: Literal["artist", "album"]
    name: str
    artist: Optional[str] = None
    entity_id: Optional[str] = None
    entity_source_id: Optional[str] = None
    metric: Literal["plays", "listen_time"]
    total_plays: int
    total_listen_sec: int
    unique_tracks: int
    average_listen_sec: float
    first_played_at: Optional[str] = None
    last_played_at: Optional[str] = None
    current_rank: Optional[int] = None
    previous_rank: Optional[int] = None
    rank_change: Optional[int] = None
    comparison_available: bool
    trend: list[EntityTrendPoint]
    top_tracks: list[EntityTrackItem]
    recent_plays: list[EntityRecentPlayItem]


class HistoryItem(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    play_count: int
    last_played_at: Optional[str] = None
    total_listen_sec: Optional[int] = None
    source_id: Optional[str] = None
    source_name: Optional[str] = None


class HealthLiveResponse(BaseModel):
    status: str


class ReadinessChecks(BaseModel):
    database: str
    polling_task: str
    upstream: str
    persistence: str


class ReadinessMetrics(BaseModel):
    poll_success_total: int
    poll_failure_total: int
    save_success_total: int
    save_failure_total: int
    active_sessions: int
    seconds_since_last_poll: Optional[int] = None
    last_upstream_error_code: Optional[int] = None
    collector_count: int = 0
    healthy_collector_count: int = 0
    degraded_collector_count: int = 0
    backfill_run_total: int = 0
    backfill_imported_total: int = 0
    backfill_error_total: int = 0


class ReadinessResponse(BaseModel):
    status: str
    checks: ReadinessChecks
    metrics: ReadinessMetrics


class LoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class AuthStatusResponse(BaseModel):
    auth_required: bool


class PrivacySettingsResponse(BaseModel):
    retention_days: Optional[int] = None
    permanent: bool = True


class PrivacySettingsUpdate(BaseModel):
    retention_days: Optional[int] = None


class RetentionPreviewResponse(BaseModel):
    records_to_delete: int
    history_records_to_delete: int = 0
    attempt_records_to_delete: int = 0
    retention_days: Optional[int] = None
    database_bytes: int
    total_records: int
    estimated_data_bytes: int
    bytes_to_delete: int = 0
    estimated_database_bytes_after: int


class StorageStatsResponse(BaseModel):
    database_bytes: int
    total_records: int
    history_records: int = 0
    attempt_records: int = 0
    estimated_data_bytes: int


class RetentionApplyResponse(BaseModel):
    deleted: int
    history_deleted: int = 0
    attempts_deleted: int = 0
    retention_days: Optional[int] = None


class RetentionApplyRequest(BaseModel):
    confirm: bool = False
    expected_retention_days: Optional[int]


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
    attempts_imported: int = 0
    inserted: int = 0
    skipped: int = 0
    conflicts: int = 0
    merge: bool


class ConfirmRequest(BaseModel):
    confirm: bool = False


class NowPlayingItem(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    client_name: Optional[str] = None
    seconds_elapsed: int
    source_name: Optional[str] = None
    source_id: Optional[str] = None
    track_id: Optional[str] = None


class SourceConfigResponse(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password_configured: bool = False


class SourceConfigUpdate(BaseModel):
    url: Optional[str] = Field(default=None, max_length=2048)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=4096)


class SourceTestRequest(BaseModel):
    url: Optional[str] = Field(default=None, max_length=2048)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=4096)


class SourceTestResponse(BaseModel):
    ok: bool
    message: str
    category: ConnectionTestCategory = "unknown"
    upstream_code: Optional[int] = None


class ServerResponse(BaseModel):
    id: str
    display_name: str
    url: str
    username: str
    password_configured: bool
    enabled: bool = True
    backfill_playlist_id: Optional[str] = None
    backfill_summary: Optional[dict] = None
    runtime_status: Optional[str] = None
    last_poll_ok: Optional[bool] = None
    seconds_since_last_poll: Optional[int] = None
    seconds_since_last_success: Optional[int] = None
    last_error_category: Optional[ConnectionFailureCategory] = None
    last_upstream_error_code: Optional[int] = None
    retry_in_seconds: Optional[int] = None
    song_history_ready: Optional[bool] = None


class ServerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    username: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, max_length=4096)
    enabled: bool = True
    backfill_playlist_id: Optional[str] = Field(default=None, max_length=64)


class ServerTestResponse(BaseModel):
    ok: bool
    message: str
    category: ConnectionTestCategory = "unknown"
    upstream_code: Optional[int] = None


class ConnectionDiagnosticsResponse(BaseModel):
    schema_version: int
    category: ConnectionDiagnosticCategory
    configured_connection_count: int
    enabled_connection_count: int
    history_record_count: int
    healthy_collector_count: int
    degraded_collector_count: int
    last_success_at: Optional[str] = None
    retry_in_seconds: Optional[int] = None


class ServerStat(BaseModel):
    source_id: str
    source_name: str
    count: int
    total_listen_sec: int


class ServerOption(BaseModel):
    id: str
    display_name: str


class UsersResponse(BaseModel):
    users: list[str]


class DashboardSnapshot(BaseModel):
    summary: SummaryStat
    players: list[PlayerStat]
    transcoding: list[TranscodingStat]
    hourly: list[HourlyStat]
    daily: list[DailyStat]
    heatmap: list[WeekdayHourStat]
    history: list[HistoryItem]
    servers: list[ServerStat]
    available_servers: list[ServerOption]
    top_artists: list[TopArtistItem]
    top_albums: list[TopAlbumItem]


class AboutResponse(BaseModel):
    name: str
    version: str
    schema_version: int
    features: list[str]
    license: str
    project_url: Optional[str] = None


class ReviewMonthBucket(BaseModel):
    month: str
    count: int
    total_listen_sec: int = 0


class ReviewHourBucket(BaseModel):
    hour: int
    count: int
    total_listen_sec: int = 0


class ReviewWeekdayBucket(BaseModel):
    weekday: int
    count: int
    total_listen_sec: int = 0


class ReviewTopItem(BaseModel):
    name: Optional[str] = None
    count: int
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None
    source_id: Optional[str] = None
    album_id: Optional[str] = None
    track_id: Optional[str] = None


class ReviewResponse(BaseModel):
    year: int
    timezone: str = TIMEZONE_DEFAULT
    source_id: Optional[str] = None
    username: Optional[str] = None
    total_plays: int
    total_listen_sec: int
    unique_tracks: int
    active_days: int
    longest_streak_days: int
    first_played_at: Optional[str] = None
    last_played_at: Optional[str] = None
    biggest_month: Optional[str] = None
    monthly: list[ReviewMonthBucket]
    hourly: list[ReviewHourBucket]
    weekday: list[ReviewWeekdayBucket]
    top_artists: list[ReviewTopItem]
    top_albums: list[ReviewTopItem]
    top_tracks: list[ReviewTopItem]
