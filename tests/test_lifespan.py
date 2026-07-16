import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.main import POLL_INTERVAL, app, lifespan, polling_loop, runtime_state, session_tracker


@pytest.fixture
def synthetic_navidrome_env(monkeypatch):
    monkeypatch.setenv("NAVIDROME_URL", "http://navidrome.example.invalid:4533")
    monkeypatch.setenv("NAVIDROME_USER", "smoke_user")
    monkeypatch.setenv("NAVIDROME_PASS", "smoke_pass")


@pytest.fixture
def reset_runtime(monkeypatch, db_path):
    monkeypatch.setenv("DATABASE_URL", db_path)
    runtime_state.polling_task = None
    runtime_state.client_initialized = False
    runtime_state.poll_success_count = 0
    runtime_state.poll_failure_count = 0
    runtime_state.last_poll_at = None
    runtime_state.last_poll_ok = None
    runtime_state.last_upstream_error_code = None
    runtime_state.save_success_count = 0
    runtime_state.save_failure_count = 0
    session_tracker.active_sessions.clear()
    yield
    if runtime_state.polling_task is not None and not runtime_state.polling_task.done():
        runtime_state.polling_task.cancel()
    session_tracker.active_sessions.clear()


@pytest.mark.asyncio
async def test_lifespan_starts_polling_and_closes_client(
    synthetic_navidrome_env, reset_runtime, db_path
):
    mock_client = AsyncMock()
    mock_client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }

    with patch("src.main.NavidromeClient", return_value=mock_client):
        async with lifespan(app):
            assert runtime_state.client_initialized is True
            assert runtime_state.polling_task is not None
            assert runtime_state.polling_task_alive()

    mock_client.close.assert_awaited_once()
    assert runtime_state.polling_task is None or runtime_state.polling_task.done()


@pytest.mark.asyncio
async def test_lifespan_degraded_when_client_init_fails(reset_runtime, db_path):
    with patch("src.main.NavidromeClient", side_effect=ValueError("missing config")):
        async with lifespan(app):
            assert runtime_state.client_initialized is False
            assert runtime_state.polling_task is None


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
