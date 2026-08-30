from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.collectors import build_readiness_report
from src.main import app
from src.sessions import PlaybackSessionTracker


@pytest.mark.asyncio
async def test_metrics_returns_text_plain():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_metrics_contains_expected_metric_names():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    body = response.text
    assert "navidrome_stat_poll_success_total" in body
    assert "navidrome_stat_poll_failure_total" in body
    assert "navidrome_stat_save_success_total" in body
    assert "navidrome_stat_save_failure_total" in body
    assert "navidrome_stat_active_sessions" in body
    assert "navidrome_stat_seconds_since_last_poll" in body
    assert "navidrome_stat_upstream_error_code" in body
    assert "navidrome_stat_polling_task_up" in body
    assert "navidrome_stat_dashboard_build_duration_seconds" in body
    assert "navidrome_stat_dashboard_cache_hit_total" in body
    assert "navidrome_stat_sqlite_busy_total" in body
    assert "navidrome_stat_import_duration_seconds" in body
    assert "navidrome_stat_coverart_cache_hit_total" in body
    assert "navidrome_stat_coverart_cache_bytes" in body
    assert "navidrome_stat_stats_query_duration_seconds" in body


@pytest.mark.asyncio
async def test_metrics_contains_help_and_type_lines():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    body = response.text
    assert "# HELP" in body
    assert "# TYPE" in body


@pytest.mark.asyncio
async def test_metrics_accessible_without_auth_when_token_configured():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/metrics")
    assert response.status_code == 200
    assert "navidrome_stat_poll_success_total" in response.text


@pytest.mark.asyncio
async def test_metrics_require_auth_when_flag_enabled(monkeypatch):
    monkeypatch.setenv("STATS_METRICS_AUTH", "true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            denied = await ac.get("/metrics")
            allowed = await ac.get(
                "/metrics",
                headers={"Authorization": "Bearer synthetic-secret-token"},
            )
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Unauthorized"
    assert allowed.status_code == 200
    assert "navidrome_stat_poll_success_total" in allowed.text


@pytest.mark.asyncio
async def test_metrics_stay_public_when_auth_flag_set_without_token(monkeypatch):
    monkeypatch.setenv("STATS_METRICS_AUTH", "true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value=None):
            response = await ac.get("/metrics")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_and_metrics_aggregate_non_paused_runtime_sessions(monkeypatch):

    import src.collectors as collectors

    async def save_session(_session):
        return None

    first_tracker = PlaybackSessionTracker(save_session)
    second_tracker = PlaybackSessionTracker(save_session)
    first_tracker._sessions["active-1"] = {"paused": False}
    second_tracker._sessions["active-2"] = {"paused": False}
    second_tracker._sessions["paused"] = {"paused": True}
    monkeypatch.setattr(
        collectors, "_runtime_trackers", [first_tracker, second_tracker]
    )
    monkeypatch.setattr(collectors, "ping_db", AsyncMock(return_value=True))

    report = await build_readiness_report()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")

    assert report["metrics"]["active_sessions"] == 2
    assert "navidrome_stat_active_sessions 2\n" in response.text


@pytest.mark.asyncio
async def test_readiness_reports_one_failed_collector(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    import src.collectors as collectors
    from src.runtime_state import RuntimeState

    state = RuntimeState(client_initialized=True)
    first_task = asyncio.create_task(asyncio.Event().wait())
    second_task = asyncio.create_task(asyncio.Event().wait())
    state.set_collector_task("server-a", first_task)
    state.set_collector_task("server-b", second_task)
    now = datetime.now(timezone.utc)
    state.record_poll_success(now, "server-a")
    state.record_poll_upstream_error(now, 40, "server-b")
    monkeypatch.setattr(collectors, "runtime_state", state)
    monkeypatch.setattr(collectors, "ping_db", AsyncMock(return_value=True))
    try:
        report = await collectors.build_readiness_report()
    finally:
        first_task.cancel()
        second_task.cancel()
        await asyncio.gather(first_task, second_task, return_exceptions=True)

    assert report["status"] == "degraded"
    assert report["checks"]["upstream"] == "error"
    assert report["metrics"]["collector_count"] == 2
    assert report["metrics"]["healthy_collector_count"] == 1
    assert report["metrics"]["degraded_collector_count"] == 1


@pytest.mark.asyncio
async def test_readiness_keeps_per_source_persistence_failures_visible(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    import src.collectors as collectors
    from src.runtime_state import RuntimeState

    state = RuntimeState(client_initialized=True)
    first_task = asyncio.create_task(asyncio.Event().wait())
    second_task = asyncio.create_task(asyncio.Event().wait())
    state.set_collector_task("server-a", first_task)
    state.set_collector_task("server-b", second_task)
    now = datetime.now(timezone.utc)
    state.record_poll_success(now, "server-a")
    state.record_poll_success(now, "server-b")
    state.record_save_failure("server-a")
    state.record_save_success("server-b")
    monkeypatch.setattr(collectors, "runtime_state", state)
    monkeypatch.setattr(collectors, "ping_db", AsyncMock(return_value=True))
    try:
        report = await collectors.build_readiness_report()
        state.record_save_success("server-a")
        recovered = await collectors.build_readiness_report()
    finally:
        first_task.cancel()
        second_task.cancel()
        await asyncio.gather(first_task, second_task, return_exceptions=True)

    assert report["checks"]["persistence"] == "error"
    assert report["status"] == "not_ready"
    assert recovered["checks"]["persistence"] == "ok"
    assert recovered["status"] == "ready"


@pytest.mark.asyncio
async def test_polling_task_up_requires_every_collector_alive(monkeypatch):
    import asyncio

    import src.metrics as metrics
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    alive = asyncio.create_task(asyncio.Event().wait())
    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    state.set_collector_task("server-a", alive)
    state.set_collector_task("server-b", finished)
    monkeypatch.setattr(metrics, "runtime_state", state)
    try:
        assert state.polling_task_alive() is False
        body = metrics.format_prometheus_metrics(0)
        assert "navidrome_stat_polling_task_up 0\n" in body
        assert "every collector polling task is alive" in body
    finally:
        alive.cancel()
        await asyncio.gather(alive, return_exceptions=True)

    both_alive = asyncio.create_task(asyncio.Event().wait())
    other_alive = asyncio.create_task(asyncio.Event().wait())
    state = RuntimeState()
    state.set_collector_task("server-a", both_alive)
    state.set_collector_task("server-b", other_alive)
    monkeypatch.setattr(metrics, "runtime_state", state)
    try:
        assert state.polling_task_alive() is True
        body = metrics.format_prometheus_metrics(0)
        assert "navidrome_stat_polling_task_up 1\n" in body
    finally:
        both_alive.cancel()
        other_alive.cancel()
        await asyncio.gather(both_alive, other_alive, return_exceptions=True)


@pytest.mark.asyncio
async def test_readiness_reports_backfill_counter_totals(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    import src.collectors as collectors
    from src.runtime_state import RuntimeState

    state = RuntimeState(client_initialized=True)
    alive = asyncio.create_task(asyncio.Event().wait())
    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    state.set_collector_task("server-a", alive)
    state.set_collector_task("server-idle", finished)
    now = datetime.now(timezone.utc)
    state.record_poll_success(now, "server-a")
    state.record_backfill_result("server-a", 5)
    state.record_backfill_result("server-a", 0)
    state.record_backfill_error("server-idle")
    monkeypatch.setattr(collectors, "runtime_state", state)
    monkeypatch.setattr(collectors, "ping_db", AsyncMock(return_value=True))
    try:
        report = await collectors.build_readiness_report()
    finally:
        alive.cancel()
        await asyncio.gather(alive, return_exceptions=True)

    assert report["metrics"]["backfill_run_total"] == 2
    assert report["metrics"]["backfill_imported_total"] == 5
    assert report["metrics"]["backfill_error_total"] == 1


def test_product_metrics_render_low_cardinality_counters_and_summaries(monkeypatch):
    import src.metrics as metrics
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    state.record_dashboard_cache_hit()
    state.record_dashboard_cache_miss()
    state.record_dashboard_cache_shared()
    state.record_dashboard_build(0.125)
    state.record_sqlite_busy(retried=True)
    state.record_import(0.25)
    state.record_coverart_cache_access(hit=True, cache_bytes=1024, limit_bytes=4096)
    state.record_stats_query("summary", 0.3, budget_seconds=0.25)
    monkeypatch.setattr(metrics, "runtime_state", state)

    body = metrics.format_prometheus_metrics(0)

    assert "navidrome_stat_dashboard_cache_hit_total 1\n" in body
    assert "navidrome_stat_dashboard_cache_miss_total 1\n" in body
    assert "navidrome_stat_dashboard_cache_shared_total 1\n" in body
    assert "navidrome_stat_dashboard_build_duration_seconds_count 1\n" in body
    assert "navidrome_stat_dashboard_build_duration_seconds_sum 0.125000000\n" in body
    assert "navidrome_stat_sqlite_busy_total 1\n" in body
    assert "navidrome_stat_sqlite_retry_total 1\n" in body
    assert "navidrome_stat_import_duration_seconds_count 1\n" in body
    assert "navidrome_stat_coverart_cache_hit_total 1\n" in body
    assert "navidrome_stat_coverart_cache_bytes 1024\n" in body
    assert "navidrome_stat_coverart_cache_limit_bytes 4096\n" in body
    assert 'navidrome_stat_stats_query_duration_seconds_count{query="summary"} 1\n' in body
    assert 'navidrome_stat_stats_query_duration_seconds_sum{query="summary"} 0.300000000\n' in body
    assert 'navidrome_stat_stats_query_max_duration_seconds{query="summary"} 0.300000000\n' in body
    assert 'navidrome_stat_stats_query_over_budget_total{query="summary"} 1\n' in body
