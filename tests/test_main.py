import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@patch("src.main.ping_db", return_value=True)
async def test_health_ready_ok_when_database_available(mock_ping):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ready", "degraded", "not_ready")
    assert body["checks"]["database"] == "ok"
    assert "metrics" in body
    assert "poll_success_total" in body["metrics"]


@pytest.mark.asyncio
@patch("src.main.ping_db", return_value=False)
async def test_health_ready_not_ready_when_database_unavailable(mock_ping):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "error"

@pytest.mark.asyncio
@patch("src.main.get_player_stats")
async def test_api_player_stats(mock_get_stats):
    mock_get_stats.return_value = [{"client_name": "Feishin", "count": 10}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/players")
    assert response.status_code == 200
    assert response.json() == [{"client_name": "Feishin", "count": 10}]

@pytest.mark.asyncio
@patch("src.main.get_transcoding_stats")
async def test_api_transcoding_stats(mock_get_stats):
    mock_get_stats.return_value = [{"is_transcoding": 0, "count": 5}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/stats/transcoding")
    assert response.status_code == 200
    assert response.json() == [{"is_transcoding": 0, "count": 5}]
