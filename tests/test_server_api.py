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
    reconcile = AsyncMock()
    with patch("src.main.save_server", AsyncMock()) as save:
        with patch("src.main._reconcile_collectors", reconcile):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 200
    assert save.await_count == 1
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_server_applies_disabled_state_immediately():
    existing = {"id": "server-1", **payload()}
    reconcile = AsyncMock()
    with patch("src.main.get_server", AsyncMock(return_value=existing)):
        with patch("src.main.save_server", AsyncMock()):
            with patch("src.main._reconcile_collectors", reconcile):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.put("/api/servers/server-1", json=payload(enabled=False))

    assert response.status_code == 200
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_server_rejects_whitespace_identity_fields():
    existing = {"id": "server-1", **payload()}
    invalid = payload()
    invalid["display_name"] = "   "
    with patch("src.main.get_server", AsyncMock(return_value=existing)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.put("/api/servers/server-1", json=invalid)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_server_stops_runtime_collector():
    reconcile = AsyncMock()
    with patch("src.main.delete_server", AsyncMock(return_value=True)):
        with patch("src.main._reconcile_collectors", reconcile):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.delete("/api/servers/server-1")

    assert response.status_code == 200
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_runtime_apply_failure_returns_generic_error():
    reconcile = AsyncMock(
        side_effect=RuntimeError("synthetic-password upstream detail")
    )
    with patch("src.main.save_server", AsyncMock()):
        with patch("src.main._reconcile_collectors", reconcile):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "Saved configuration could not be applied"}
    assert "synthetic-password" not in response.text


@pytest.mark.asyncio
async def test_server_connection_test_uses_submitted_fields_and_checks_status():
    existing = {"id": "server-1", **payload()}
    client = AsyncMock()
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "failed", "error": {"code": 40}}
    }
    client_type = patch("src.main.NavidromeClient").start()
    client_type.return_value = client
    client_type.response_is_ok.return_value = False
    try:
        with patch("src.main.get_server", AsyncMock(return_value=existing)):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                response = await ac.post(
                    "/api/servers/server-1/test",
                    json={
                        "display_name": "Edited",
                        "url": "https://edited.example.invalid",
                        "username": "edited-user",
                        "password": "edited-password",
                        "enabled": True,
                    },
                )
    finally:
        patch.stopall()

    assert response.status_code == 200
    assert response.json()["ok"] is False
    client_type.assert_called_once_with(
        url="https://edited.example.invalid",
        user="edited-user",
        password="edited-password",
    )
