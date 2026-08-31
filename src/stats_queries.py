"""Compatibility imports for the statistics query modules.

New code may import the focused modules directly. Existing imports remain
supported through this module.
"""

from src.stats_query_history import get_playback_history
from src.stats_query_overview import (
    get_earliest_poller_played_at,
    get_player_stats,
    get_server_stats,
    get_short_play_stats,
    get_source_stats,
    get_summary,
    get_transcoding_stats,
    list_usernames,
)
from src.stats_query_rankings import get_top_albums, get_top_artists
from src.stats_query_timeline import (
    WEEKDAY_HOUR_CELL_COUNT,
    WEEKDAY_HOUR_HOUR_COUNT,
    WEEKDAY_HOUR_WEEKDAY_COUNT,
    get_daily_stats,
    get_hourly_stats,
    get_time_bucket_stats,
    get_weekday_hour_stats,
)

__all__ = [
    "WEEKDAY_HOUR_CELL_COUNT",
    "WEEKDAY_HOUR_HOUR_COUNT",
    "WEEKDAY_HOUR_WEEKDAY_COUNT",
    "get_daily_stats",
    "get_earliest_poller_played_at",
    "get_hourly_stats",
    "get_playback_history",
    "get_player_stats",
    "get_server_stats",
    "get_short_play_stats",
    "get_source_stats",
    "get_summary",
    "get_time_bucket_stats",
    "get_top_albums",
    "get_top_artists",
    "get_transcoding_stats",
    "get_weekday_hour_stats",
    "list_usernames",
]
