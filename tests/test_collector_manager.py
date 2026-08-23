import asyncio
from unittest.mock import AsyncMock

import pytest


def server_config(server_id="server-1", *, enabled=True, password="synthetic-password"):
    return {
        "id": server_id,
        "display_name": "Synthetic Server",
        "url": "http://navidrome.example.invalid:4533",
        "username": "synthetic-user",
        "password": password,
        "enabled": enabled,
    }


@pytest.mark.asyncio
async def test_start_registers_collector_and_tracker():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    trackers = []
    manager = CollectorManager(client_factory, poller, trackers)
    await manager.start(server_config())

    assert list(manager.collectors) == ["server-1"]
    assert trackers == [manager.collectors["server-1"].tracker]
    assert len(clients) == 1

    await manager.stop_all()


@pytest.mark.asyncio
async def test_replace_finalizes_and_closes_old_collector():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = CollectorManager(client_factory, poller, [])
    await manager.start(server_config())
    old = manager.collectors["server-1"]
    old.tracker.finalize_all = AsyncMock()

    await manager.replace(server_config(password="replacement-password"))

    old.tracker.finalize_all.assert_awaited_once()
    clients[0].close.assert_awaited_once()
    assert old.task.cancelled()
    assert manager.collectors["server-1"].client is clients[1]

    await manager.stop_all()


@pytest.mark.asyncio
async def test_disabled_replacement_stops_existing_collector():
    from src.main import CollectorManager

    client = AsyncMock()

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = CollectorManager(lambda **_config: client, poller, [])
    await manager.start(server_config())

    await manager.replace(server_config(enabled=False))

    assert manager.collectors == {}
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_replacement_keeps_old_collector_running():
    from src.main import CollectorManager

    old_client = AsyncMock()
    calls = 0

    def client_factory(**_config):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("synthetic construction failure")
        return old_client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = CollectorManager(client_factory, poller, [])
    await manager.start(server_config())
    old = manager.collectors["server-1"]

    with pytest.raises(ValueError, match="synthetic construction failure"):
        await manager.replace(server_config(password="replacement-password"))

    assert manager.collectors["server-1"] is old
    assert not old.task.done()
    old_client.close.assert_not_awaited()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_stop_only_removes_selected_collector():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    trackers = []
    manager = CollectorManager(client_factory, poller, trackers)
    await manager.start(server_config("server-1"))
    await manager.start(server_config("server-2"))

    await manager.stop("server-1")

    assert list(manager.collectors) == ["server-2"]
    assert trackers == [manager.collectors["server-2"].tracker]
    clients[0].close.assert_awaited_once()
    clients[1].close.assert_not_awaited()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_finalize_failure_still_closes_old_and_starts_replacement():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = CollectorManager(client_factory, poller, [])
    await manager.start(server_config())
    old = manager.collectors["server-1"]
    old.tracker.finalize_all = AsyncMock(
        side_effect=RuntimeError("synthetic finalize failure")
    )

    await manager.replace(server_config(password="replacement-password"))

    clients[0].close.assert_awaited_once()
    clients[1].close.assert_not_awaited()
    assert old.task.cancelled()
    assert list(manager.collectors) == ["server-1"]
    assert manager.collectors["server-1"].client is clients[1]
    assert not manager.collectors["server-1"].task.done()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_stop_cleans_up_after_poller_task_has_failed():
    import src.main as main

    client = AsyncMock()

    async def failed_poller(_client, _tracker):
        raise RuntimeError("synthetic poller failure")

    trackers = []
    manager = main.CollectorManager(lambda **_config: client, failed_poller, trackers)
    await manager.start(server_config())
    await asyncio.sleep(0)
    assert manager.collectors["server-1"].task.done()

    with pytest.raises(RuntimeError, match="Failed to clean up collector"):
        await manager.stop("server-1")

    assert manager.collectors == {}
    assert trackers == []
    assert "server-1" not in main.runtime_state.collectors
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_starts_new_collector_after_old_poller_task_failed():
    from src.main import CollectorManager

    clients = []
    poller_calls = 0

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        nonlocal poller_calls
        poller_calls += 1
        if poller_calls == 1:
            raise RuntimeError("synthetic poller failure")
        await asyncio.Event().wait()

    trackers = []
    manager = CollectorManager(client_factory, poller, trackers)
    await manager.start(server_config())
    old = manager.collectors["server-1"]
    await asyncio.sleep(0)
    assert old.task.done()

    await manager.replace(server_config(password="replacement-password"))

    assert clients[0].close.await_count == 1
    assert old.tracker not in trackers
    assert trackers == [manager.collectors["server-1"].tracker]
    assert manager.collectors["server-1"].client is clients[1]
    assert not manager.collectors["server-1"].task.done()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_stop_all_continues_after_one_collector_finalize_fails():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    trackers = []
    manager = CollectorManager(client_factory, poller, trackers)
    await manager.start(server_config("server-1"))
    await manager.start(server_config("server-2"))
    manager.collectors["server-1"].tracker.finalize_all = AsyncMock(
        side_effect=RuntimeError("synthetic finalize failure")
    )

    with pytest.raises(RuntimeError, match="Failed to stop collectors"):
        await manager.stop_all()

    assert manager.collectors == {}
    assert trackers == []
    for client in clients:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_activates_replacements_after_finalize_failure():
    from src.main import CollectorManager

    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = CollectorManager(client_factory, poller, [])
    await manager.start(server_config("server-1"))
    await manager.start(server_config("server-2"))
    manager.collectors["server-1"].tracker.finalize_all = AsyncMock(
        side_effect=RuntimeError("synthetic finalize failure")
    )
    replacements = [
        server_config("server-1", password="replacement-password"),
        server_config("server-2", password="replacement-password"),
    ]

    await manager.reconcile(replacements)

    assert list(manager.collectors) == ["server-1", "server-2"]
    clients[0].close.assert_awaited_once()
    clients[1].close.assert_awaited_once()
    clients[2].close.assert_not_awaited()
    clients[3].close.assert_not_awaited()
    assert manager.collectors["server-1"].client is clients[2]
    assert manager.collectors["server-2"].client is clients[3]
    assert not manager.collectors["server-1"].task.done()
    assert not manager.collectors["server-2"].task.done()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_reconcile_replaces_legacy_with_configured_server():
    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = __import__(
        "src.main", fromlist=["CollectorManager"]
    ).CollectorManager(client_factory, poller, [])
    legacy = server_config("legacy")
    legacy["display_name"] = "Legacy environment source"
    await manager.reconcile([legacy])
    await manager.reconcile([server_config("server-1")])

    assert list(manager.collectors) == ["server-1"]
    clients[0].close.assert_awaited_once()
    await manager.stop_all()


@pytest.mark.asyncio
async def test_reconcile_unchanged_configuration_keeps_running_collector():
    clients = []

    def client_factory(**_config):
        client = AsyncMock()
        clients.append(client)
        return client

    async def poller(_client, _tracker):
        await asyncio.Event().wait()

    manager = __import__(
        "src.main", fromlist=["CollectorManager"]
    ).CollectorManager(client_factory, poller, [])
    desired = server_config("server-1")
    await manager.reconcile([desired])
    original = manager.collectors["server-1"]
    await manager.reconcile([desired])

    assert manager.collectors["server-1"] is original
    assert len(clients) == 1
    await manager.stop_all()
