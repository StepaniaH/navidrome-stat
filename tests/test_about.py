from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import SCHEMA_VERSION
from src.main import app
from src.version import APP_VERSION, LICENSE, PROJECT_NAME, PROJECT_URL


@pytest.mark.asyncio
async def test_about_returns_public_project_identity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/about")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == PROJECT_NAME
    assert body["version"] == APP_VERSION
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["license"] == LICENSE
    assert body["project_url"] == PROJECT_URL
    assert PROJECT_URL.startswith("https://github.com/StepaniaH/navidrome-stat")


@pytest.mark.asyncio
async def test_about_requires_auth_when_token_configured():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            denied = await ac.get("/api/about")
            allowed = await ac.get(
                "/api/about",
                headers={"Authorization": "Bearer synthetic-secret-token"},
            )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["project_url"] == PROJECT_URL
