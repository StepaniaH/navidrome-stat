"""Statistics API endpoints."""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from src.collectors import active_now_playing
from src.coverart import cover_art_service
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
    list_usernames,
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
    ReviewResponse,
    ServerStat,
    ShortPlayStats,
    SourceStat,
    SummaryStat,
    TopAlbumItem,
    TopArtistItem,
    TranscodingStat,
    UsersResponse,
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


def _validate_custom_date_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date | None, date | None]:
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
    return start_date, end_date


def _source_kwargs(source_id: str | None) -> dict:
    return {"source_id": source_id} if source_id else {}


def _user_kwargs(username: str | None) -> dict:
    return {"username": username} if username else {}


def _date_range_kwargs(
    start_date: date | None,
    end_date: date | None,
) -> dict:
    if start_date is None or end_date is None:
        return {}
    return {"start_date": start_date, "end_date": end_date}


@router.get("/api/stats/users", response_model=UsersResponse)
async def api_stat_users():
    """Return usernames present in listening history for filtering."""
    async def fetch() -> UsersResponse:
        return UsersResponse(users=await list_usernames())

    return await _query_stats(fetch)


@router.get("/api/coverart")
async def api_cover_art(
    source_id: str = Query(min_length=1, max_length=128),
    id: str = Query(min_length=1, max_length=128),
    size: int = Query(default=300, ge=32, le=600),
):
    """Proxy one cover art image from the owning Navidrome server."""
    result = await cover_art_service.load(source_id, id, size)
    if result is None:
        raise HTTPException(status_code=404, detail="Cover art not available")
    data, content_type = result
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=2592000, immutable"},
    )


@router.get("/api/stats/dashboard", response_model=DashboardSnapshot)
async def api_dashboard_snapshot(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    metric: str = Query(default=RANKING_METRIC_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return one cached historical payload; now-playing remains real-time."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    ranking = _validate_ranking_metric(metric)
    start_date, end_date = _validate_custom_date_range(start_date, end_date)
    return await _query_stats(
        lambda: stats_service.dashboard(
            days=window,
            timezone_name=tz,
            metric=ranking,
            source_id=source_id,
            start_date=start_date,
            end_date=end_date,
            username=username,
        )
    )


@router.get("/api/stats/summary", response_model=SummaryStat)
async def api_summary_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return aggregate listening totals and period comparisons."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_summary(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
        )
    )


@router.get("/api/stats/players", response_model=list[PlayerStat])
async def api_player_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for player usage distribution over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_player_stats(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
        )
    )


@router.get("/api/stats/transcoding", response_model=list[TranscodingStat])
async def api_transcoding_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Endpoint for transcoding ratio over the selected window."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_transcoding_stats(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
        )
    )


@router.get("/api/stats/short-plays", response_model=ShortPlayStats)
async def api_short_play_stats(
    days: int = Query(default=STATS_DAYS_ALL, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    username: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Return short-play rate; it does not claim intentional skips."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    start_date, end_date = _validate_custom_date_range(start_date, end_date)
    return await _query_stats(
        lambda: get_short_play_stats(
            days=window,
            timezone_name=tz,
            **_date_range_kwargs(start_date, end_date),
            **_source_kwargs(source_id),
            **_user_kwargs(username),
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
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return play counts grouped by local hour."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_hourly_stats(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
        )
    )


@router.get("/api/stats/heatmap", response_model=list[WeekdayHourStat])
async def api_weekday_hour_stats(
    days: int = Query(default=STATS_DAYS_DEFAULT, ge=0, le=STATS_DAYS_MAX),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return a zero-filled 7-by-24 local-time listening heatmap."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_weekday_hour_stats(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
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
    username: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return zero-filled play counts grouped by local calendar day."""
    window = _validate_stats_days(days)
    tz = _validate_stats_timezone(timezone)
    return await _query_stats(
        lambda: get_daily_stats(
            days=window,
            timezone_name=tz,
            **_source_kwargs(source_id),
            **_user_kwargs(username),
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
    username: str | None = Query(default=None, min_length=1, max_length=128),
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
            **_user_kwargs(username),
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
    username: str | None = Query(default=None, min_length=1, max_length=128),
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
            **_user_kwargs(username),
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
                    source_id=session.get("source_id"),
                    track_id=session.get("track_id"),
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
    username: str | None = Query(default=None, min_length=1, max_length=128),
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
            **_user_kwargs(username),
        )
    )


@router.get("/api/stats/review", response_model=ReviewResponse)
async def api_review(
    year: int = Query(default=0, ge=0, le=9999),
    timezone: str = Query(default=TIMEZONE_DEFAULT),
    source_id: str | None = Query(default=None, min_length=1, max_length=128),
):
    """Return the year-in-review aggregation for one local calendar year."""
    from datetime import datetime

    tz = _validate_stats_timezone(timezone)
    if year == 0:
        year = datetime.now(resolve_timezone(tz)).year
    if not 1970 <= year <= 2075:
        raise HTTPException(status_code=422, detail="year must be between 1970 and 2075")
    return await _query_stats(
        lambda: stats_service.review(year=year, timezone_name=tz, source_id=source_id)
    )
