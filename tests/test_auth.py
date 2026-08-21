from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth import login_rate_limiter
from src.main import app


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_stats_open_when_auth_not_configured(mock_get_stats):
    mock_get_stats.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value=None):
            response = await ac.get("/api/stats/players")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_stats_require_token_when_auth_enabled(mock_get_stats):
    mock_get_stats.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/api/stats/players")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_stats_allow_bearer_token(mock_get_stats):
    mock_get_stats.return_value = [{"client_name": "Web", "count": 1}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get(
                "/api/stats/players",
                headers={"Authorization": "Bearer synthetic-secret-token"},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_stats_allow_session_cookie_after_login(mock_get_stats):
    mock_get_stats.return_value = [{"client_name": "Web", "count": 1}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            login = await ac.post(
                "/api/auth/login",
                json={"token": "synthetic-secret-token"},
            )
            assert login.status_code == 200
            response = await ac.get("/api/stats/players")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_rejects_invalid_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.post("/api/auth/login", json={"token": "wrong-token"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_remains_public_when_auth_enabled():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            health = await ac.get("/health")
            ready = await ac.get("/health/ready")
    assert health.status_code == 200
    assert ready.status_code in (200, 503)


@pytest.mark.asyncio
async def test_openapi_blocked_when_auth_enabled():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get("/openapi.json")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_openapi_routes_absent_when_disabled(monkeypatch):
    import importlib

    import src.main as main_module

    monkeypatch.setenv("OPENAPI_ENABLED", "false")
    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.OPENAPI_ENABLED is False
        async with AsyncClient(
            transport=ASGITransport(app=reloaded.app), base_url="http://test"
        ) as ac:
            openapi = await ac.get("/openapi.json")
            docs = await ac.get("/docs")
        assert openapi.status_code == 404
        assert docs.status_code == 404
    finally:
        monkeypatch.delenv("OPENAPI_ENABLED", raising=False)
        importlib.reload(main_module)


@pytest.mark.asyncio
async def test_auth_status_reports_requirement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            enabled = await ac.get("/api/auth/status")
        with patch("src.auth.get_stats_api_token", return_value=None):
            disabled = await ac.get("/api/auth/status")
    assert enabled.json() == {"auth_required": True}
    assert disabled.json() == {"auth_required": False}


@pytest.mark.asyncio
async def test_security_headers_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "Content-Security-Policy" in response.headers


@pytest.mark.asyncio
async def test_login_rate_limit_uses_generic_response():
    login_rate_limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            for _ in range(login_rate_limiter.max_attempts):
                response = await ac.post("/api/auth/login", json={"token": "wrong-token"})
                assert response.status_code == 401
            limited = await ac.post("/api/auth/login", json={"token": "wrong-token"})
    login_rate_limiter.reset()
    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many login attempts"}
    assert int(limited.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_secure_cookie_can_be_enabled(monkeypatch):
    login_rate_limiter.reset()
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.post(
                "/api/auth/login",
                json={"token": "synthetic-secret-token"},
            )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


@pytest.mark.asyncio
@patch("src.main.get_player_stats", new_callable=AsyncMock)
async def test_stats_allow_lowercase_bearer_scheme(mock_get_stats):
    mock_get_stats.return_value = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            response = await ac.get(
                "/api/stats/players",
                headers={"Authorization": "bearer synthetic-secret-token"},
            )
    assert response.status_code == 200


def test_non_ascii_credentials_are_rejected_without_raising():
    from unittest.mock import MagicMock

    from src.auth import is_authorized

    request = MagicMock()
    with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
        request.headers.get.return_value = None
        request.cookies.get.return_value = "测试令牌"
        assert is_authorized(request) is False
        request.headers.get.return_value = "Bearer 测试令牌"
        request.cookies.get.return_value = None
        assert is_authorized(request) is False


def test_verify_login_token_rejects_non_ascii_without_raising(monkeypatch):
    monkeypatch.setenv("STATS_API_TOKEN", "synthetic-secret-token")
    from src.auth import verify_login_token

    assert verify_login_token("synthetic-secret-token") is True
    assert verify_login_token("测试令牌") is False


@pytest.mark.asyncio
async def test_logout_clears_secure_cookie(monkeypatch):
    login_rate_limiter.reset()
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            login = await ac.post(
                "/api/auth/login",
                json={"token": "synthetic-secret-token"},
            )
            logout = await ac.post("/api/auth/logout")
    assert login.status_code == 200
    assert logout.status_code == 200
    set_cookie = logout.headers["set-cookie"]
    assert "stats_session=" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
