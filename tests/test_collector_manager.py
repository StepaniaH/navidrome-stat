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
async def test_finalize_failure_still_closes_old_and_replacement_clients():
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

    with pytest.raises(RuntimeError, match="synthetic finalize failure"):
        await manager.replace(server_config(password="replacement-password"))

    clients[0].close.assert_awaited_once()
    clients[1].close.assert_awaited_once()
    assert old.task.cancelled()
    assert manager.collectors == {}
