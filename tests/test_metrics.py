import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from src.main import app


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