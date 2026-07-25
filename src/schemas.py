from typing import Optional

from pydantic import BaseModel


HISTORY_LIMIT_DEFAULT = 10
HISTORY_LIMIT_MIN = 1
HISTORY_LIMIT_MAX = 100

TOP_LIMIT_DEFAULT = 10
TOP_LIMIT_MIN = 1
TOP_LIMIT_MAX = 50


class PlayerStat(BaseModel):
    client_name: Optional[str] = None
    count: int


class TranscodingStat(BaseModel):
    is_transcoding: Optional[int] = None
    count: int


class SummaryStat(BaseModel):
    total_plays: int
    total_listen_sec: int
    unique_tracks: int
    client_count: int


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
