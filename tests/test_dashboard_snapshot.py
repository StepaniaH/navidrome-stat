from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.dashboard_cache import dashboard_snapshot_cache
from src.main import app


def _snapshot():
    return {
        "summary": {
            "total_plays": 1,
            "total_listen_sec": 120,
            "unique_tracks": 1,
            "client_count": 1,
        },
        "players": [],
        "transcoding": [],
        "hourly": [],
        "daily": [],
        "heatmap": [],
        "history": [],
        "servers": [],
        "available_servers": [
            {"id": "server-1", "display_name": "Synthetic Server"},
        ],
        "top_artists": [],
        "top_albums": [],
    }


@pytest.mark.asyncio
async def test_dashboard_snapshot_is_cached_and_redacts_connection_fields():
    await dashboard_snapshot_cache.invalidate()
    build = AsyncMock(return_value=_snapshot())
    with patch("src.main._build_dashboard_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.get("/api/stats/dashboard?days=30&timezone=UTC")
            second = await client.get("/api/stats/dashboard?days=30&timezone=UTC")

    assert first.status_code == 200
    assert second.status_code == 200
    build.assert_awaited_once()
    option = first.json()["available_servers"][0]
    assert option == {"id": "server-1", "display_name": "Synthetic Server"}
    assert set(option) == {"id", "display_name"}


@pytest.mark.asyncio
async def test_dashboard_cache_invalidation_rebuilds_snapshot():
    await dashboard_snapshot_cache.invalidate()
    build = AsyncMock(return_value=_snapshot())
    with patch("src.main._build_dashboard_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.get("/api/stats/dashboard?days=30&timezone=UTC")
            await dashboard_snapshot_cache.invalidate()
            await client.get("/api/stats/dashboard?days=30&timezone=UTC")
    assert build.await_count == 2
