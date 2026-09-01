"""StatsService owns every playback write path and the snapshot cache."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

import src.stats_service as stats_module
from src.stats_query_entities import EntityIdentity
from src.stats_scope import StatsScope
from src.stats_service import StatsService


class FakeCache:
    def __init__(self):
        self.invalidations = 0
        self.builds = 0
        self.keys = []

    async def invalidate(self):
        self.invalidations += 1

    async def get_or_create(self, key, factory):
        self.builds += 1
        self.keys.append(key)
        return await factory()


@pytest.fixture
def cache():
    return FakeCache()


@pytest.fixture
def service(cache):
    return StatsService(cache=cache, retry_attempts=2, read_repository=Mock())


@pytest.fixture(autouse=True)
def restore_module_symbols():
    saved = {
        name: getattr(stats_module, name)
        for name in (
            "save_play_session",
            "save_play_attempt",
            "apply_retention_purge",
            "import_user_data",
            "delete_user_data",
            "save_server",
            "delete_server",
            "list_server_options",
        )
    }
    yield
    for name, value in saved.items():
        setattr(stats_module, name, value)


@pytest.fixture(autouse=True)
def restore_runtime_counters():
    saved = (
        stats_module.runtime_state.save_success_count,
        stats_module.runtime_state.save_failure_count,
        stats_module.runtime_state.last_save_at,
        stats_module.runtime_state.last_save_ok,
    )
    yield
    stats_module.runtime_state.save_success_count = saved[0]
    stats_module.runtime_state.save_failure_count = saved[1]
    stats_module.runtime_state.last_save_at = saved[2]
    stats_module.runtime_state.last_save_ok = saved[3]


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
async def test_sqlite_busy_retry_is_observable(cache, service, monkeypatch):
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(stats_module, "runtime_state", state)
    monkeypatch.setattr(stats_module.asyncio, "sleep", AsyncMock())
    stats_module.save_play_session = AsyncMock(
        side_effect=[sqlite3.OperationalError("database is locked"), None]
    )

    await service.record_session({"duration_sec": 30})

    assert state.sqlite_busy_count == 1
    assert state.sqlite_retry_count == 1


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
async def test_cache_failure_does_not_mark_successful_write_unhealthy(cache, service, caplog):
    stats_module.save_play_session = AsyncMock()
    cache.invalidate = AsyncMock(side_effect=RuntimeError("cache unavailable"))
    failures_before = stats_module.runtime_state.save_failure_count

    await service.record_session({"duration_sec": 30, "source_id": "source-a"})

    stats_module.save_play_session.assert_awaited_once()
    assert stats_module.runtime_state.last_save_ok is True
    assert stats_module.runtime_state.save_failure_count == failures_before
    assert "cache invalidation failed" in caplog.text


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
    stats_module.import_user_data = AsyncMock(return_value={"imported": 3, "attempts_imported": 0})
    await service.import_user("u", {}, merge=False)
    assert cache.invalidations == 1

    stats_module.import_user_data = AsyncMock(return_value={"imported": 0, "attempts_imported": 0})
    await service.import_user("u", {}, merge=True)
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_import_duration_is_observable(cache, service, monkeypatch):
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(stats_module, "runtime_state", state)
    stats_module.import_user_data = AsyncMock(return_value={"imported": 0, "attempts_imported": 0})

    await service.import_user("u", {}, merge=True)

    assert state.import_count == 1
    assert state.import_duration_seconds >= 0

@pytest.mark.asyncio
async def test_delete_user_invalidates_only_when_rows_deleted(cache, service):
    stats_module.delete_user_data = AsyncMock(return_value={"deleted": 0})
    await service.delete_user("u")
    assert cache.invalidations == 0

    stats_module.delete_user_data = AsyncMock(return_value={"deleted": 4})
    await service.delete_user("u")
    assert cache.invalidations == 1


@pytest.mark.asyncio
async def test_delete_user_suppresses_already_queued_session_write(cache, service):
    delete_started = asyncio.Event()
    release_delete = asyncio.Event()

    async def blocked_delete(_username):
        delete_started.set()
        await release_delete.wait()
        return {"deleted": 1}

    stats_module.delete_user_data = AsyncMock(side_effect=blocked_delete)
    stats_module.save_play_session = AsyncMock()
    service.set_session_discarder(lambda _username: {"deleted-session"})

    delete_task = asyncio.create_task(service.delete_user("alice"))
    await delete_started.wait()
    write_task = asyncio.create_task(
        service.record_session(
            {
                "session_id": "deleted-session",
                "source_id": "source-a",
                "duration_sec": 30,
            }
        )
    )
    await asyncio.sleep(0)
    assert not write_task.done()

    release_delete.set()
    await delete_task
    await write_task

    stats_module.save_play_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_user_failure_keeps_active_sessions(cache, service):
    stats_module.delete_user_data = AsyncMock(side_effect=ConnectionError("unavailable"))
    discard = Mock(return_value={"active-session"})
    service.set_session_discarder(discard)

    with pytest.raises(ConnectionError):
        await service.delete_user("alice")

    discard.assert_not_called()
    assert "active-session" not in service._suppressed_session_ids


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
    service._read_repository.dashboard = AsyncMock(
        return_value={
            "summary": {},
            "players": [],
            "transcoding": [],
            "time_buckets": {"hourly": [], "daily": [], "heatmap": []},
            "history": [],
            "servers": [],
            "available_servers": [],
            "top_artists": [],
            "top_albums": [],
        }
    )

    scope = StatsScope.create(days=7, timezone_name="UTC", metric="plays")
    await service.dashboard(scope)
    first = await service.dashboard(scope)

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


@pytest.mark.asyncio
async def test_entity_detail_uses_scope_and_identity_in_cache_key(cache, service):
    payload = {"entity_type": "artist", "name": "Artist A"}
    service._read_repository.entity_detail = AsyncMock(return_value=payload)
    scope = StatsScope.create(days=7, timezone_name="UTC", metric="plays")
    identity = EntityIdentity.create(entity_type="artist", name="Artist A")

    result = await service.entity_detail(scope, identity)

    assert result == payload
    assert cache.keys == [("entity_detail", scope, identity)]
    service._read_repository.entity_detail.assert_awaited_once_with(scope, identity)


@pytest.mark.asyncio
async def test_data_relations_uses_scope_and_dimension_in_cache_key(cache, service):
    payload = {"dimension": "client", "trend": []}
    service._read_repository.data_relations = AsyncMock(return_value=payload)
    scope = StatsScope.create(days=30, timezone_name="UTC", metric="listen_time")

    result = await service.data_relations(scope, "client")

    assert result == payload
    assert cache.keys == [("data_relations", scope, "client")]
    service._read_repository.data_relations.assert_awaited_once_with(scope, "client")


@pytest.mark.asyncio
async def test_dashboard_build_duration_is_observable(cache, service, monkeypatch):
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(stats_module, "runtime_state", state)
    service._build_snapshot = AsyncMock(return_value={"summary": {}})

    result = await service.dashboard(StatsScope.create(days=30))

    assert result == {"summary": {}}
    assert state.dashboard_build_count == 1
    assert state.dashboard_build_duration_seconds >= 0


@pytest.mark.asyncio
async def test_dashboard_keeps_local_stats_when_album_art_lookup_fails(cache, service, monkeypatch):
    service._read_repository.dashboard = AsyncMock(
        return_value={
            "summary": {"total_plays": 7},
            "players": [],
            "transcoding": [],
            "time_buckets": {"hourly": [], "daily": [], "heatmap": []},
            "history": [],
            "servers": [],
            "available_servers": [{"id": "server-1", "display_name": "Synthetic Server"}],
            "top_artists": [],
            "top_albums": [
                {"album": "Local Album", "count": 3, "total_listen_sec": 120, "value": 3}
            ],
        }
    )
    lookup = AsyncMock(side_effect=ValueError("upstream credentials unavailable"))
    monkeypatch.setattr(stats_module.cover_art_service, "resolve_album_id", lookup)

    result = await service.dashboard(StatsScope.create(
        days=30,
        timezone_name="UTC",
        metric="plays",
        source_id=None,
    ))

    assert result["summary"] == {"total_plays": 7}
    assert result["top_albums"] == [
        {
            "album": "Local Album",
            "count": 3,
            "total_listen_sec": 120,
            "value": 3,
            "album_id": None,
        }
    ]
    lookup.assert_awaited_once_with("server-1", "Local Album", None)
