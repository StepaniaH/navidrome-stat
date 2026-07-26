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


class PlayerStat(BaseModel):
    client_name: Optional[str] = None
    count: int


class TranscodingStat(BaseModel):
    is_transcoding: Optional[int] = None
    count: int


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


class TopArtistItem(BaseModel):
    artist: str
    count: int


class TopAlbumItem(BaseModel):
    album: str
    count: int


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
