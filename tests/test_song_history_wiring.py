"""Probe-to-import wiring for the getSongHistory seam in the polling loop."""

import asyncio
from unittest.mock import AsyncMock

import pytest

import src.collectors as collectors_module
from src.collectors import (
    _reset_song_history_import_guard,
    polling_loop_for_tracker,
)
from src.runtime_state import RuntimeState
from src.sessions import PlaybackSessionTracker


@pytest.mark.asyncio
async def test_probe_true_triggers_single_initial_import(monkeypatch):
    _reset_song_history_import_guard()
    state = RuntimeState()
    monkeypatch.setattr(collectors_module, "runtime_state", state)

    run_history = AsyncMock(return_value={"imported": 4, "skipped": 0})
    monkeypatch.setattr(collectors_module, "run_song_history", run_history)
    earliest = AsyncMock(return_value=None)
    monkeypatch.setattr(
        collectors_module, "get_earliest_poller_played_at", earliest
    )

    tracker = PlaybackSessionTracker(
        AsyncMock(), source_id="gsh-src", source_name="History Source"
    )
    client = AsyncMock()
    client.user = "history-user"
    client.supports_playback_report.return_value = False
    client.supports_song_history.return_value = True
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }

    async def stop_after_first_poll(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(collectors_module.asyncio, "sleep", stop_after_first_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    run_history.assert_awaited_once()
    kwargs = run_history.await_args.kwargs
    assert kwargs["username"] == "history-user"
    assert kwargs["source_id"] == "gsh-src"
    assert earliest.assert_awaited_once is not None
    assert state.collectors["gsh-src"].backfill_run_count == 1


@pytest.mark.asyncio
async def test_initial_import_runs_once_per_process_per_source(monkeypatch):
    _reset_song_history_import_guard()
    run_history = AsyncMock(return_value={"imported": 0, "skipped": 0})
    monkeypatch.setattr(collectors_module, "run_song_history", run_history)

    class Tracker:
        source_id = "once-src"
        source_name = "Once Source"

    client = AsyncMock()
    client.user = "u"

    await collectors_module._run_initial_song_history(
        Tracker.source_id, Tracker.source_name, client
    )
    await collectors_module._run_initial_song_history(
        Tracker.source_id, Tracker.source_name, client
    )

    assert run_history.await_count == 1


@pytest.mark.asyncio
async def test_probe_false_keeps_seam_inert(monkeypatch):
    _reset_song_history_import_guard()
    state = RuntimeState()
    monkeypatch.setattr(collectors_module, "runtime_state", state)
    run_history = AsyncMock()
    monkeypatch.setattr(collectors_module, "run_song_history", run_history)

    tracker = PlaybackSessionTracker(AsyncMock())
    client = AsyncMock()
    client.supports_playback_report.return_value = False
    client.supports_song_history.return_value = False
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }

    async def stop_after_first_poll(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(collectors_module.asyncio, "sleep", stop_after_first_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    run_history.assert_not_awaited()
