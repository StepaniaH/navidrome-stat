"""Statistics API endpoints."""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from src.collectors import active_now_playing
from src.database import (
    get_daily_stats,
    get_hourly_stats,
    get_playback_history,
    get_player_stats,
    get_server_stats,
    get_short_play_stats,
    get_source_stats,
    get_summary,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    get_weekday_hour_stats,
    resolve_timezone,
)
from src.schemas import (
    DAILY_DAYS_DEFAULT,
    DAILY_DAYS_MAX,
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    HISTORY_LIMIT_MIN,
    RANKING_METRIC_DEFAULT,
    RANKING_METRIC_VALIDATION_ERROR,
    RANKING_METRICS,
    STATS_DAYS_ALL,
    STATS_DAYS_DEFAULT,
    STATS_DAYS_MAX,
    STATS_DAYS_MIN,
    TIMEZONE_DEFAULT,
    TIMEZONE_VALIDATION_ERROR,
    TOP_LIMIT_DEFAULT,
    TOP_LIMIT_MAX,
    TOP_LIMIT_MIN,
    DailyStat,
    DashboardSnapshot,
    HistoryItem,
    HourlyStat,
    NowPlayingItem,
    PlayerStat,
    ServerStat,
    ShortPlayStats,
    SourceStat,
    SummaryStat,
    TopAlbumItem,
    TopArtistItem,
    TranscodingStat,
    WeekdayHourStat,
)
from src.stats_service import stats_service

logger = logging.getLogger(__name__)
router = APIRouter()


async def _query_stats(fetch):
    try:
        return await fetch()
    except Exception:
        logger.error("Database query failed")
        raise HTTPException(status_code=503, detail="Stats temporarily unavailable")


def _validate_stats_days(days: int) -> int:
    """Accept all history or a supported finite statistics window."""
    if days == STATS_DAYS_ALL:
        return STATS_DAYS_ALL
    if STATS_DAYS_MIN <= days <= STATS_DAYS_MAX:
        return days
    raise HTTPException(
        status_code=422,
        detail=f"days must be {STATS_DAYS_ALL} (all history) or between "
        f"{STATS_DAYS_MIN} and {STATS_DAYS_MAX}",
    )


def _validate_stats_timezone(timezone_name: str) -> str:
    """Validate an IANA timezone name."""
    try:
        resolve_timezone(timezone_name)
    except ValueError:
        raise HTTPException(status_code=422, detail=TIMEZONE_VALIDATION_ERROR)
    return timezone_name


def _validate_ranking_metric(metric: str) -> str:
    """Validate a ranking metric shared by artist and album endpoints."""
    if metric not in RANKING_METRICS:
        raise HTTPException(status_code=422, detail=RANKING_METRIC_VALIDATION_ERROR)
    return metric


def _source_kwargs(source_id: str | None) -> dict:
    return {"source_id": source_id} if source_id else {}


@router.get("/api/stats/dashboard", response_model=DashboardSnapshot)
async def api_dashboard_snapshot(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Return one cached historical payload; now-playing remains real-time."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    ranking = _validate_ranking_metric(metric)
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be provided together",
        )
    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date must not be after end_date",
            )
        if (end_date - start_date).days + 1 > 366:
            raise HTTPException(
                status_code=422,
                detail="custom date range must not exceed 366 days",
            )
    return await _query_stats(
        lambda: stats_service.dashboard(
            days=window,
            timezone_name=tz,
            metric=ranking,
            source_id=source_id,
            start_date=start_date,
            end_date=end_date,
        )
    )


@router.get("/api/stats/summary", response_model=SummaryStat)
async def api_summary_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return aggregate listening totals and period comparisons."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_summary(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/players", response_model=list[PlayerStat])
async def api_player_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for player usage distribution over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_player_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/transcoding", response_model=list[TranscodingStat])
async def api_transcoding_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for transcoding ratio over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_transcoding_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/short-plays", response_model=ShortPlayStats)
async def api_short_play_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return short-play rate; it does not claim intentional skips."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_short_play_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/sources", response_model=list[SourceStat])
async def api_source_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return formal play counts grouped by provenance source."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_source_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/servers", response_model=list[ServerStat])
async def api_server_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return formal play totals grouped by configured server identity."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(lambda: get_server_stats(days=window, timezone_name=tz, source_id=source_id))


@router.get("/api/stats/hourly", response_model=list[HourlyStat])
async def api_hourly_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return play counts grouped by local hour."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_hourly_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/heatmap", response_model=list[WeekdayHourStat])
async def api_weekday_hour_stats(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return a zero-filled 7-by-24 local-time listening heatmap."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_weekday_hour_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/daily", response_model=list[DailyStat])
async def api_daily_stats(
    days: int = Query(
        default=DAILY_DAYS_DEFAULT,
        ge=0,
        le=DAILY_DAYS_MAX,
    ),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return zero-filled play counts grouped by local calendar day."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_daily_stats(
            days=window, timezone_name=tz, **_source_kwargs(source_id)
        )
    )


@router.get("/api/stats/top-artists", response_model=list[TopArtistItem])
async def api_top_artists(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return top artists ranked by plays or listening time."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    m = _validate_ranking_metric(metric)
    return await _query_stats(
        lambda: get_top_artists(
            limit=limit,
            days=window,
            timezone_name=tz,
            metric=m,
            **_source_kwargs(source_id),
        )
    )


@router.get("/api/stats/top-albums", response_model=list[TopAlbumItem])
async def api_top_albums(
    limit: int = Query(
        default=TOP_LIMIT_DEFAULT,
        ge=TOP_LIMIT_MIN,
        le=TOP_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return top albums ranked by plays or listening time."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    m = _validate_ranking_metric(metric)
    return await _query_stats(
        lambda: get_top_albums(
            limit=limit,
            days=window,
            timezone_name=tz,
            metric=m,
            **_source_kwargs(source_id),
        )
    )


@router.get("/api/stats/now-playing", response_model=list[NowPlayingItem])
async def api_now_playing(
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for currently active playback sessions (in-memory, no DB access)."""
    try:
        now = datetime.now(timezone.utc)
        items: list[NowPlayingItem] = []
        for session in active_now_playing():
            if source_id and session.get("source_id") != source_id:
                continue
            first_seen_at = session.get("first_seen_at")
            seconds_elapsed = 0
            if first_seen_at is not None:
                seconds_elapsed = int((now - first_seen_at).total_seconds())
                if seconds_elapsed < 0:
                    seconds_elapsed = 0
            items.append(
                NowPlayingItem(
                    username=session.get("username"),
                    title=session.get("title"),
                    artist=session.get("artist"),
                    client_name=session.get("client_name"),
                    seconds_elapsed=seconds_elapsed,
                    source_name=session.get("source_name"),
                )
            )
        return items
    except Exception:
        logger.error("Now playing query failed")
        raise HTTPException(status_code=503, detail="Stats temporarily unavailable")


@router.get("/api/stats/history", response_model=list[HistoryItem])
async def api_playback_history(
    limit: int = Query(
        default=HISTORY_LIMIT_DEFAULT,
        ge=HISTORY_LIMIT_MIN,
        le=HISTORY_LIMIT_MAX,
    ),
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for recent playback history over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_playback_history(
            limit=limit,
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
        )
    )
