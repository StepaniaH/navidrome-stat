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
        "# HELP navidrome_stat_polling_task_up 1 if the polling task is alive, 0 otherwise.",
        "# TYPE navidrome_stat_polling_task_up gauge",
        f"navidrome_stat_polling_task_up {polling_task_up}",
    ]
    return "\n".join(lines) + "\n"