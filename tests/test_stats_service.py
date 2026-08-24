"""StatsService owns every playback write path and the snapshot cache."""

from unittest.mock import AsyncMock

import pytest

import src.stats_service as stats_module
from src.stats_service import StatsService


class FakeCache:
    def __init__(self):
        self.invalidations = 0
        self.builds = 0

    async def invalidate(self):
        self.invalidations += 1

    async def get_or_create(self, key, factory):
        self.builds += 1
        return await factory()


@pytest.fixture
def cache():
    return FakeCache()


@pytest.fixture
def service(cache):
    return StatsService(cache=cache, retry_attempts=2)


@pytest.fixture
def restore_runtime_counters():
    saved = (
        stats_module.runtime_state.save_success_count,
        stats_module.runtime_state.save_failure_count,
    )
    yield
    stats_module.runtime_state.save_success_count = saved[0]
    stats_module.runtime_state.save_failure_count = saved[1]


@pytest.mark.asyncio
async def test_record_session_retries_then_invalidates(cache, service):
    writes = AsyncMock(side_effect=[ConnectionError("boom"), None])
    stats_module.save_play_session = writes
    try:
        await service.record_session({"duration_sec": 30})
    finally:
        pass
    assert writes.await_count == 2
    assert cache.invalidations == 1
    assert stats_module.runtime_state.save_success_count >= 1


@pytest.mark.asyncio
async def test_record_session_exhausted_retries_records_failure_and_skips_invalidation(
    cache, service, restore_runtime_counters
):
    writes = AsyncMock(side_effect=ConnectionError("down"))
    stats_module.save_play_session = writes
    failures_before = stats_module.runtime_state.save_failure_count
    with pytest.raises(ConnectionError):
        await service.record_session({"duration_sec": 30})
    assert writes.await_count == 2
    assert cache.invalidations == 0
    assert stats_module.runtime_state.save_failure_count == failures_before + 1


@pytest.mark.asyncio
async def test_record_attempt_invalidates(cache, service):
    writes = AsyncMock()
    stats_module.save_play_attempt = writes
    await service.record_attempt({"duration_sec": 5})
    assert writes.await_count == 1
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_purge_invalidates_only_when_rows_deleted(cache, service):
    stats_module.apply_retention_purge = AsyncMock(return_value={"deleted": 0})
    await service.purge_retention()
    assert cache.invalidations == 0

    stats_module.apply_retention_purge = AsyncMock(
        return_value={"deleted": 7, "history_deleted": 5, "attempts_deleted": 2}
    )
    await service.purge_retention()
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_import_invalidates_on_written_rows(cache, service):
    stats_module.import_user_data = AsyncMock(
        return_value={"imported": 3, "attempts_imported": 0}
    )
    await service.import_user("u", {}, merge=False)
    assert cache.invalidations == 1

    stats_module.import_user_data = AsyncMock(
        return_value={"imported": 0, "attempts_imported": 0}
    )
    await service.import_user("u", {}, merge=True)
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_delete_user_invalidates_only_when_rows_deleted(cache, service):
    stats_module.delete_user_data = AsyncMock(return_value={"deleted": 0})
    await service.delete_user("u")
    assert cache.invalidations == 0

    stats_module.delete_user_data = AsyncMock(return_value={"deleted": 4})
    await service.delete_user("u")
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_server_mutations_always_invalidate(cache, service):
    stats_module.save_server = AsyncMock()
    stats_module.delete_server = AsyncMock(return_value=True)

    await service.create_server({"id": "s1"})
    await service.update_server({"id": "s1"})
    await service.remove_server("s1")

    assert cache.invalidations == 3


@pytest.mark.asyncio
async def test_dashboard_builds_through_cache(cache, service):
    stats_module.get_summary = AsyncMock(return_value={})
    stats_module.get_player_stats = AsyncMock(return_value=[])
    stats_module.get_transcoding_stats = AsyncMock(return_value=[])
    stats_module.get_time_bucket_stats = AsyncMock(
        return_value={"hourly": [], "daily": [], "heatmap": []}
    )
    stats_module.get_playback_history = AsyncMock(return_value=[])
    stats_module.get_server_stats = AsyncMock(return_value=[])
    stats_module.list_servers = AsyncMock(return_value=[])
    stats_module.get_top_artists = AsyncMock(return_value=[])
    stats_module.get_top_albums = AsyncMock(return_value=[])

    query = {
        "days": 7,
        "timezone_name": "UTC",
        "metric": "plays",
        "source_id": None,
    }
    await service.dashboard(**query)
    first = await service.dashboard(**query)

    assert cache.builds == 2  # FakeCache has no dedup; both calls build through it
    assert set(first) == {
        "summary",
        "players",
        "transcoding",
        "hourly",
        "daily",
        "heatmap",
        "history",
        "servers",
        "available_servers",
        "top_artists",
        "top_albums",
    }
