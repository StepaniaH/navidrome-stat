from datetime import datetime, timezone

from src.runtime_state import runtime_state


def format_prometheus_metrics(active_sessions: int) -> str:
    """Render runtime metrics in Prometheus text exposition format."""
    seconds_since_last_poll = -1
    if runtime_state.last_poll_at is not None:
        seconds_since_last_poll = int(
            (datetime.now(timezone.utc) - runtime_state.last_poll_at).total_seconds()
        )

    upstream_error_code = runtime_state.last_upstream_error_code
    if upstream_error_code is None:
        upstream_error_code = -1

    polling_task_up = 1 if runtime_state.polling_task_alive() else 0

    lines = [
        "# HELP navidrome_stat_poll_success_total Total successful poll cycles.",
        "# TYPE navidrome_stat_poll_success_total counter",
        f"navidrome_stat_poll_success_total {runtime_state.poll_success_count}",
        "# HELP navidrome_stat_poll_failure_total Total failed poll cycles.",
        "# TYPE navidrome_stat_poll_failure_total counter",
        f"navidrome_stat_poll_failure_total {runtime_state.poll_failure_count}",
        "# HELP navidrome_stat_save_success_total Total successful play session saves.",
        "# TYPE navidrome_stat_save_success_total counter",
        f"navidrome_stat_save_success_total {runtime_state.save_success_count}",
        "# HELP navidrome_stat_save_failure_total Total failed play session saves.",
        "# TYPE navidrome_stat_save_failure_total counter",
        f"navidrome_stat_save_failure_total {runtime_state.save_failure_count}",
        "# HELP navidrome_stat_active_sessions Currently active playback sessions.",
        "# TYPE navidrome_stat_active_sessions gauge",
        f"navidrome_stat_active_sessions {active_sessions}",
        "# HELP navidrome_stat_seconds_since_last_poll Seconds since the last poll cycle.",
        "# TYPE navidrome_stat_seconds_since_last_poll gauge",
        f"navidrome_stat_seconds_since_last_poll {seconds_since_last_poll}",
        "# HELP navidrome_stat_upstream_error_code Last upstream Subsonic error code (-1 if none).",
        "# TYPE navidrome_stat_upstream_error_code gauge",
        f"navidrome_stat_upstream_error_code {upstream_error_code}",
        "# HELP navidrome_stat_polling_task_up 1 if every collector polling task is alive, 0 otherwise.",
        "# TYPE navidrome_stat_polling_task_up gauge",
        f"navidrome_stat_polling_task_up {polling_task_up}",
        "# HELP navidrome_stat_dashboard_cache_hit_total Dashboard snapshot cache hits.",
        "# TYPE navidrome_stat_dashboard_cache_hit_total counter",
        f"navidrome_stat_dashboard_cache_hit_total {runtime_state.dashboard_cache_hit_count}",
        "# HELP navidrome_stat_dashboard_cache_miss_total Dashboard snapshot cache misses.",
        "# TYPE navidrome_stat_dashboard_cache_miss_total counter",
        f"navidrome_stat_dashboard_cache_miss_total {runtime_state.dashboard_cache_miss_count}",
        "# HELP navidrome_stat_dashboard_cache_shared_total Requests joined to an in-flight build.",
        "# TYPE navidrome_stat_dashboard_cache_shared_total counter",
        f"navidrome_stat_dashboard_cache_shared_total {runtime_state.dashboard_cache_shared_count}",
        "# HELP navidrome_stat_dashboard_build_duration_seconds Dashboard snapshot build time.",
        "# TYPE navidrome_stat_dashboard_build_duration_seconds summary",
        f"navidrome_stat_dashboard_build_duration_seconds_count {runtime_state.dashboard_build_count}",
        f"navidrome_stat_dashboard_build_duration_seconds_sum {runtime_state.dashboard_build_duration_seconds:.9f}",
        "# HELP navidrome_stat_sqlite_busy_total SQLite busy or locked errors.",
        "# TYPE navidrome_stat_sqlite_busy_total counter",
        f"navidrome_stat_sqlite_busy_total {runtime_state.sqlite_busy_count}",
        "# HELP navidrome_stat_sqlite_retry_total SQLite busy errors followed by a retry.",
        "# TYPE navidrome_stat_sqlite_retry_total counter",
        f"navidrome_stat_sqlite_retry_total {runtime_state.sqlite_retry_count}",
        "# HELP navidrome_stat_import_duration_seconds Playback import time.",
        "# TYPE navidrome_stat_import_duration_seconds summary",
        f"navidrome_stat_import_duration_seconds_count {runtime_state.import_count}",
        f"navidrome_stat_import_duration_seconds_sum {runtime_state.import_duration_seconds:.9f}",
        "# HELP navidrome_stat_coverart_cache_hit_total Cover-art disk cache hits.",
        "# TYPE navidrome_stat_coverart_cache_hit_total counter",
        f"navidrome_stat_coverart_cache_hit_total {runtime_state.coverart_cache_hit_count}",
        "# HELP navidrome_stat_coverart_cache_miss_total Cover-art disk cache misses.",
        "# TYPE navidrome_stat_coverart_cache_miss_total counter",
        f"navidrome_stat_coverart_cache_miss_total {runtime_state.coverart_cache_miss_count}",
        "# HELP navidrome_stat_coverart_cache_bytes Cover-art disk cache bytes in use.",
        "# TYPE navidrome_stat_coverart_cache_bytes gauge",
        f"navidrome_stat_coverart_cache_bytes {runtime_state.coverart_cache_bytes}",
        "# HELP navidrome_stat_coverart_cache_limit_bytes Configured cover-art cache byte limit.",
        "# TYPE navidrome_stat_coverart_cache_limit_bytes gauge",
        f"navidrome_stat_coverart_cache_limit_bytes {runtime_state.coverart_cache_limit_bytes}",
        "# HELP navidrome_stat_stats_query_duration_seconds Dashboard query time by fixed section.",
        "# TYPE navidrome_stat_stats_query_duration_seconds summary",
        "# HELP navidrome_stat_stats_query_max_duration_seconds Slowest observed dashboard query by fixed section.",
        "# TYPE navidrome_stat_stats_query_max_duration_seconds gauge",
        "# HELP navidrome_stat_stats_query_over_budget_total Dashboard queries over the configured budget.",
        "# TYPE navidrome_stat_stats_query_over_budget_total counter",
    ]
    for query, timing in sorted(runtime_state.stats_query_timings.items()):
        label = f'query="{query}"'
        lines.extend([
            f"navidrome_stat_stats_query_duration_seconds_count{{{label}}} {timing.count}",
            f"navidrome_stat_stats_query_duration_seconds_sum{{{label}}} "
            f"{timing.duration_seconds:.9f}",
            f"navidrome_stat_stats_query_max_duration_seconds{{{label}}} "
            f"{timing.max_duration_seconds:.9f}",
            f"navidrome_stat_stats_query_over_budget_total{{{label}}} "
            f"{timing.over_budget_count}",
        ])
    return "\n".join(lines) + "\n"
