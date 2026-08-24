from typing import Optional

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


class TopAlbumItem(BaseModel):
    album: str
    count: int
    total_listen_sec: Optional[int] = None
    value: Optional[int] = None
    album_id: Optional[str] = None


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


class ServerResponse(BaseModel):
    id: str
    display_name: str
    url: str
    username: str
    password_configured: bool
    enabled: bool = True
    runtime_status: Optional[str] = None
    last_poll_ok: Optional[bool] = None
    seconds_since_last_poll: Optional[int] = None


class ServerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    username: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, max_length=4096)
    enabled: bool = True


class ServerTestResponse(BaseModel):
    ok: bool
    message: str


class ServerStat(BaseModel):
    source_id: str
    source_name: str
    count: int
    total_listen_sec: int


class ServerOption(BaseModel):
    id: str
    display_name: str


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
