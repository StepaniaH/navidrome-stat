"""Probe-to-import wiring for getSongHistory in the polling loop."""

import asyncio
from unittest.mock import AsyncMock

import pytest

import src.collectors as collectors_module
from src.collectors import (
    _reset_song_history_import_guard,
    polling_loop_for_tracker,
)
from src.database import init_db
from src.importers.cursor_store import (
    load_song_history_cursor,
    save_song_history_cursor,
)
from src.runtime_state import RuntimeState
from src.sessions import PlaybackSessionTracker


@pytest.mark.asyncio
async def test_probe_true_triggers_single_initial_import(monkeypatch, isolated_db):
    await init_db(isolated_db)
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
async def test_initial_import_runs_once_per_process_per_source(monkeypatch, isolated_db):
    await init_db(isolated_db)
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
async def test_probe_false_does_not_start_import(monkeypatch, isolated_db):
    await init_db(isolated_db)
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


@pytest.mark.asyncio
async def test_partial_history_run_resumes_from_durable_cursor(monkeypatch, isolated_db):
    await init_db(isolated_db)
    _reset_song_history_import_guard()
    run_history = AsyncMock(
        side_effect=[
            {"imported": 200, "skipped": 0, "next_offset": 200, "complete": False},
            {"imported": 50, "skipped": 0, "next_offset": 250, "complete": True},
        ]
    )
    monkeypatch.setattr(collectors_module, "run_song_history", run_history)
    monkeypatch.setattr(
        collectors_module,
        "get_earliest_poller_played_at",
        AsyncMock(return_value=None),
    )
    client = AsyncMock()
    client.user = "resume-user"

    await collectors_module._run_initial_song_history("resume-src", "Resume", client)
    _reset_song_history_import_guard()
    await collectors_module._run_initial_song_history("resume-src", "Resume", client)

    assert run_history.await_count == 2
    assert run_history.await_args_list[0].kwargs["start_offset"] == 0
    assert run_history.await_args_list[1].kwargs["start_offset"] == 200
    cursor = await load_song_history_cursor("resume-src", "resume-user", isolated_db)
    assert cursor["next_offset"] == 250
    assert cursor["complete"] is True


@pytest.mark.asyncio
async def test_failed_history_run_retries_only_after_backoff(monkeypatch, isolated_db):
    await init_db(isolated_db)
    _reset_song_history_import_guard()
    run_history = AsyncMock(side_effect=RuntimeError("synthetic history failure"))
    monkeypatch.setattr(collectors_module, "run_song_history", run_history)
    monkeypatch.setattr(
        collectors_module,
        "get_earliest_poller_played_at",
        AsyncMock(return_value=None),
    )
    client = AsyncMock()
    client.user = "retry-user"

    await collectors_module._run_initial_song_history("retry-src", "Retry", client)
    cursor = await load_song_history_cursor("retry-src", "retry-user", isolated_db)
    assert cursor["failure_count"] == 1
    assert cursor["retry_at"] is not None

    await collectors_module._run_initial_song_history("retry-src", "Retry", client)
    assert run_history.await_count == 1

    cursor["retry_at"] = "2000-01-01T00:00:00+00:00"
    await save_song_history_cursor("retry-src", "retry-user", cursor, isolated_db)
    run_history.side_effect = None
    run_history.return_value = {
        "imported": 0,
        "skipped": 0,
        "next_offset": 0,
        "complete": True,
    }
    await collectors_module._run_initial_song_history("retry-src", "Retry", client)
    assert run_history.await_count == 2
