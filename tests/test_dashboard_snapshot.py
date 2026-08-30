import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.dashboard_cache import DashboardSnapshotCache, dashboard_snapshot_cache
from src.main import app
from src.stats_scope import StatsScope


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
    with patch("src.stats_service.StatsService._build_snapshot", build):
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
    with patch("src.stats_service.StatsService._build_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.get("/api/stats/dashboard?days=30&timezone=UTC")
            await dashboard_snapshot_cache.invalidate()
            await client.get("/api/stats/dashboard?days=30&timezone=UTC")
    assert build.await_count == 2


@pytest.mark.asyncio
async def test_dashboard_custom_range_is_validated_and_forwarded():
    await dashboard_snapshot_cache.invalidate()
    build = AsyncMock(return_value=_snapshot())
    with patch("src.stats_service.StatsService._build_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/stats/dashboard",
                params={
                    "days": 30,
                    "timezone": "Asia/Shanghai",
                    "start_date": "2026-01-02",
                    "end_date": "2026-01-31",
                },
            )

    assert response.status_code == 200
    build.assert_awaited_once_with(StatsScope.create(
        days=30,
        timezone_name="Asia/Shanghai",
        metric="plays",
        source_id=None,
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 31),
        username=None,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"start_date": "2026-01-01"}, "provided together"),
        (
            {"start_date": "2026-02-01", "end_date": "2026-01-01"},
            "must not be after",
        ),
        (
            {"start_date": "2024-01-01", "end_date": "2026-01-01"},
            "must not exceed 366",
        ),
    ],
)
async def test_dashboard_rejects_invalid_custom_ranges(params, detail):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/stats/dashboard", params=params)

    assert response.status_code == 422
    assert detail in response.json()["detail"]


@pytest.mark.asyncio
async def test_dashboard_username_changes_cache_key():
    await dashboard_snapshot_cache.invalidate()
    build = AsyncMock(return_value=_snapshot())
    with patch("src.stats_service.StatsService._build_snapshot", build):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.get("/api/stats/dashboard?days=30&username=alice")
            await client.get("/api/stats/dashboard?days=30&username=alice")
            await client.get("/api/stats/dashboard?days=30&username=bob")

    assert build.await_count == 2


@pytest.mark.asyncio
async def test_cache_single_flight_deduplicates_same_key():
    cache = DashboardSnapshotCache()
    release = asyncio.Event()
    build = AsyncMock()

    async def factory():
        await release.wait()
        return {"value": 1}

    build.side_effect = factory
    first = asyncio.create_task(cache.get_or_create(("same",), build))
    second = asyncio.create_task(cache.get_or_create(("same",), build))
    await asyncio.sleep(0)
    release.set()

    assert await first == {"value": 1}
    assert await second == {"value": 1}
    build.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_records_hits_misses_and_shared_builds(monkeypatch):
    import src.dashboard_cache as cache_module
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(cache_module, "runtime_state", state)
    cache = DashboardSnapshotCache()
    release = asyncio.Event()

    async def factory():
        await release.wait()
        return {"value": 1}

    first = asyncio.create_task(cache.get_or_create(("observed",), factory))
    second = asyncio.create_task(cache.get_or_create(("observed",), factory))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    await cache.get_or_create(("observed",), factory)

    assert state.dashboard_cache_miss_count == 1
    assert state.dashboard_cache_shared_count == 1
    assert state.dashboard_cache_hit_count == 1


@pytest.mark.asyncio
async def test_cache_different_keys_do_not_block_each_other():
    cache = DashboardSnapshotCache()
    slow_release = asyncio.Event()

    async def slow():
        await slow_release.wait()
        return {"value": "slow"}

    slow_task = asyncio.create_task(cache.get_or_create(("slow",), slow))
    await asyncio.sleep(0)
    fast = await asyncio.wait_for(
        cache.get_or_create(("fast",), lambda: asyncio.sleep(0, result={"value": "fast"})),
        timeout=0.1,
    )
    slow_release.set()

    assert fast == {"value": "fast"}
    assert await slow_task == {"value": "slow"}


@pytest.mark.asyncio
async def test_invalidation_during_build_does_not_cache_stale_value():
    cache = DashboardSnapshotCache()
    release = asyncio.Event()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            await release.wait()
        return {"generation": calls}

    first = asyncio.create_task(cache.get_or_create(("key",), factory))
    await asyncio.sleep(0)
    await cache.invalidate()
    release.set()
    assert await first == {"generation": 1}
    assert await cache.get_or_create(("key",), factory) == {"generation": 2}
    assert calls == 2
