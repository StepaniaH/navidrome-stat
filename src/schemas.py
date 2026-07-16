from typing import Optional

from pydantic import BaseModel


HISTORY_LIMIT_DEFAULT = 10
HISTORY_LIMIT_MIN = 1
HISTORY_LIMIT_MAX = 100


class PlayerStat(BaseModel):
    client_name: Optional[str] = None
    count: int


class TranscodingStat(BaseModel):
    is_transcoding: Optional[int] = None
    count: int


class HistoryItem(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    play_count: int


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
