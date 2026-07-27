from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


def payload(*, enabled=True):
    return {
        "display_name": "Synthetic Server",
        "url": "http://navidrome.example.invalid:4533",
        "username": "synthetic-user",
        "password": "synthetic-password",
        "enabled": enabled,
    }


@pytest.mark.asyncio
async def test_create_server_applies_runtime_config_immediately():
    manager = AsyncMock()
    with patch("src.main.save_server", AsyncMock()) as save:
        with patch("src.main.collector_manager", manager):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 200
    saved = save.await_args.args[0]
    manager.replace.assert_awaited_once_with(saved)


@pytest.mark.asyncio
async def test_update_server_applies_disabled_state_immediately():
    existing = {"id": "server-1", **payload()}
    manager = AsyncMock()
    with patch("src.main.get_server", AsyncMock(return_value=existing)):
        with patch("src.main.save_server", AsyncMock()):
            with patch("src.main.collector_manager", manager):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.put("/api/servers/server-1", json=payload(enabled=False))

    assert response.status_code == 200
    applied = manager.replace.await_args.args[0]
    assert applied["id"] == "server-1"
    assert applied["enabled"] is False


@pytest.mark.asyncio
async def test_delete_server_stops_runtime_collector():
    manager = AsyncMock()
    with patch("src.main.delete_server", AsyncMock(return_value=True)):
        with patch("src.main.collector_manager", manager):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.delete("/api/servers/server-1")

    assert response.status_code == 200
    manager.stop.assert_awaited_once_with("server-1")


@pytest.mark.asyncio
async def test_runtime_apply_failure_returns_generic_error():
    manager = AsyncMock()
    manager.replace.side_effect = RuntimeError("synthetic-password upstream detail")
    with patch("src.main.save_server", AsyncMock()):
        with patch("src.main.collector_manager", manager):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "Saved configuration could not be applied"}
    assert "synthetic-password" not in response.text
