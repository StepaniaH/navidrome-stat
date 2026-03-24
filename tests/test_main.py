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
