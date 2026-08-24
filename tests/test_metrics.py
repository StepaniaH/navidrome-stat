from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, build_readiness_report
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
    import src.main as main

    async def save_session(_session):
        return None

    first_tracker = PlaybackSessionTracker(save_session)
    second_tracker = PlaybackSessionTracker(save_session)
    first_tracker._sessions["active-1"] = {"paused": False}
    second_tracker._sessions["active-2"] = {"paused": False}
    second_tracker._sessions["paused"] = {"paused": True}
    monkeypatch.setattr(
        main, "_runtime_trackers", [first_tracker, second_tracker], raising=False
    )
    monkeypatch.setattr(main, "ping_db", AsyncMock(return_value=True))

    report = await build_readiness_report()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")

    assert report["metrics"]["active_sessions"] == 2
    assert "navidrome_stat_active_sessions 2\n" in response.text


@pytest.mark.asyncio
async def test_readiness_reports_one_failed_collector(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    import src.main as main
    from src.runtime_state import RuntimeState

    state = RuntimeState(client_initialized=True)
    first_task = asyncio.create_task(asyncio.Event().wait())
    second_task = asyncio.create_task(asyncio.Event().wait())
    state.set_collector_task("server-a", first_task)
    state.set_collector_task("server-b", second_task)
    now = datetime.now(timezone.utc)
    state.record_poll_success(now, "server-a")
    state.record_poll_upstream_error(now, 40, "server-b")
    monkeypatch.setattr(main, "runtime_state", state)
    monkeypatch.setattr(main, "ping_db", AsyncMock(return_value=True))
    try:
        report = await main.build_readiness_report()
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
