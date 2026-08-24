"""Playback persistence and statistics reads.

Schema and migrations live in :mod:`src.schema`; the query layer lives in
:mod:`src.stats_queries` with time windows in :mod:`src.windows`. This module
re-exports the stable import surface that routes and services consume.
"""

from src.persistence import save_play_attempt, save_play_session  # noqa: F401
from src.schema import (  # noqa: F401
    LEGACY_SOURCE_ID,
    LEGACY_SOURCE_NAME,
    PAYLOAD_BYTES_SQL,
    SCHEMA_VERSION,
    TEXT_COLUMNS,
    get_meta_value,
    init_db,
    ping_db,
    recover_incomplete_sessions,
    set_meta_value,
)
from src.server_registry import (  # noqa: F401
    delete_server,
    get_server,
    list_servers,
    save_server,
)
from src.stats_queries import (  # noqa: F401
    WEEKDAY_HOUR_CELL_COUNT,
    WEEKDAY_HOUR_HOUR_COUNT,
    WEEKDAY_HOUR_WEEKDAY_COUNT,
    get_daily_stats,
    get_hourly_stats,
    get_playback_history,
    get_player_stats,
    get_review_summary,
    get_server_stats,
    get_short_play_stats,
    get_source_stats,
    get_summary,
    get_time_bucket_stats,
    get_top_albums,
    get_top_artists,
    get_transcoding_stats,
    get_weekday_hour_stats,
)
from src.windows import (  # noqa: F401
    TIMEZONE_DEFAULT,
    _date_window_bounds,
    _local_date_range,
    _played_at_to_local_date,
    _played_at_to_local_datetime,
    _previous_window_bounds,
    _previous_window_predicate,
    _source_predicate,
    _window_bounds,
    _window_predicate,
    resolve_timezone,
    utc_instant,
)
