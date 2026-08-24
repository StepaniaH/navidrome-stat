import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import src.collectors as collectors
from src.collectors import POLL_INTERVAL, polling_loop, session_tracker
from src.main import app, lifespan
from src.runtime_state import runtime_state


@pytest.fixture
def synthetic_navidrome_env(monkeypatch):
    monkeypatch.setenv("NAVIDROME_URL", "http://navidrome.example.invalid:4533")
    monkeypatch.setenv("NAVIDROME_USER", "smoke_user")
    monkeypatch.setenv("NAVIDROME_PASS", "smoke_pass")


@pytest.fixture
def reset_runtime(monkeypatch, db_path):

    monkeypatch.setenv("DATABASE_URL", db_path)
    runtime_state.reset()
    session_tracker._sessions.clear()
    collectors._runtime_trackers.clear()
    yield
    if runtime_state.polling_task is not None and not runtime_state.polling_task.done():
        runtime_state.polling_task.cancel()
    session_tracker._sessions.clear()


@pytest.mark.asyncio
async def test_lifespan_starts_polling_and_closes_client(
    synthetic_navidrome_env, reset_runtime, db_path
):
    mock_client = AsyncMock()
    mock_client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }

    with patch("src.collectors.list_servers", AsyncMock(return_value=[])):
        with patch("src.collectors.NavidromeClient", return_value=mock_client):
            async with lifespan(app):
                assert runtime_state.client_initialized is True
                assert runtime_state.polling_task is not None
                assert runtime_state.polling_task_alive()

    mock_client.close.assert_awaited_once()
    assert runtime_state.polling_task is None or runtime_state.polling_task.done()


@pytest.mark.asyncio
async def test_lifespan_registers_and_cleans_up_runtime_trackers(
    reset_runtime, db_path
):

    configured_server = {
        "id": "synthetic-server",
        "display_name": "Synthetic Server",
        "url": "http://navidrome.example.invalid:4533",
        "username": "synthetic-user",
        "password": "synthetic-password",
        "enabled": True,
    }
    mock_client = AsyncMock()
    mock_client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }

    with patch("src.collectors.list_servers", AsyncMock(return_value=[configured_server])):
        with patch("src.collectors.NavidromeClient", return_value=mock_client):
            async with lifespan(app):
                assert len(collectors._runtime_trackers) == 1

    assert collectors._runtime_trackers == []


@pytest.mark.asyncio
async def test_lifespan_degraded_when_client_init_fails(reset_runtime, db_path):
    with patch("src.collectors.list_servers", AsyncMock(return_value=[])):
        with patch("src.collectors.NavidromeClient", side_effect=ValueError("missing config")):
            async with lifespan(app):
                assert runtime_state.client_initialized is False
                assert runtime_state.polling_task is None


@pytest.mark.asyncio
async def test_retention_task_starts_when_collector_reconcile_fails(reset_runtime):
    import src.main as main

    retention_started = asyncio.Event()
    retention_cancelled = asyncio.Event()

    async def retention_loop():
        retention_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            retention_cancelled.set()

    with patch.object(main, "init_db", AsyncMock()):
        with patch.object(main, "run_startup_retention_purge", AsyncMock()):
            with patch.object(
                collectors,
                "reconcile_collectors",
                AsyncMock(side_effect=RuntimeError("synthetic reconcile failure")),
            ):
                with patch.object(main, "retention_maintenance_loop", retention_loop):
                    with patch.object(collectors.collector_manager, "stop_all", AsyncMock()):
                        async with lifespan(app):
                            await retention_started.wait()
                            assert runtime_state.client_initialized is False

    assert retention_cancelled.is_set()


@pytest.mark.asyncio
async def test_polling_loop_applies_backoff_on_exception(reset_runtime):
    client = AsyncMock()
    client.get_now_playing.side_effect = ConnectionError("upstream unavailable")
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with pytest.raises(asyncio.CancelledError):
            await polling_loop(client)

    assert sleep_calls == [POLL_INTERVAL]


@pytest.mark.asyncio
async def test_polling_loop_doubles_backoff_after_repeated_failures(reset_runtime):
    client = AsyncMock()
    client.get_now_playing.side_effect = ConnectionError("upstream unavailable")
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with pytest.raises(asyncio.CancelledError):
            await polling_loop(client)

    assert sleep_calls[:2] == [POLL_INTERVAL, POLL_INTERVAL * 2]


@pytest.mark.asyncio
async def test_polling_loop_resets_backoff_after_success(reset_runtime):
    client = AsyncMock()
    client.get_now_playing.side_effect = [
        ConnectionError("upstream unavailable"),
        {"subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}},
    ]
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with pytest.raises(asyncio.CancelledError):
            await polling_loop(client)

    assert sleep_calls == [POLL_INTERVAL, POLL_INTERVAL]
