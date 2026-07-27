import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

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
async def test_readiness_and_metrics_aggregate_non_paused_runtime_sessions(monkeypatch):
    import src.main as main

    async def save_session(_session):
        return None

    first_tracker = PlaybackSessionTracker(save_session)
    second_tracker = PlaybackSessionTracker(save_session)
    first_tracker.active_sessions["active-1"] = {"paused": False}
    second_tracker.active_sessions["active-2"] = {"paused": False}
    second_tracker.active_sessions["paused"] = {"paused": True}
    monkeypatch.setattr(
        main, "_runtime_trackers", [first_tracker, second_tracker], raising=False
    )
    monkeypatch.setattr(main, "ping_db", AsyncMock(return_value=True))

    report = await build_readiness_report()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")

    assert report["metrics"]["active_sessions"] == 2
    assert "navidrome_stat_active_sessions 2\n" in response.text
