import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.collectors import polling_loop_for_tracker
from src.database import init_db, save_play_session
from src.sessions import PlaybackPersistenceError, PlaybackSessionTracker


@pytest.mark.asyncio
async def test_advertised_playback_report_polling_persists_reported_checkpoint(
    db_path,
    monkeypatch,
):
    await init_db(db_path)

    async def save(payload):
        await save_play_session(payload, db_path=db_path)

    tracker = PlaybackSessionTracker(
        save,
        play_threshold_sec=5,
        checkpoint_interval_sec=60,
        source_id="synthetic-source",
        source_name="Synthetic Source",
    )
    client = AsyncMock()
    client.supports_playback_report.return_value = True
    entry = {
        "playerId": "synthetic-player",
        "id": "synthetic-track",
        "username": "synthetic-user",
        "playerName": "Synthetic Player",
        "title": "Synthetic Song",
        "artist": "Synthetic Artist",
        "album": "Synthetic Album",
        "state": "playing",
        "playbackRate": 1,
    }
    client.get_now_playing.side_effect = [
        {
            "subsonic-response": {
                "status": "ok",
                "nowPlaying": {"entry": [{**entry, "positionMs": 0}]},
            }
        },
        {
            "subsonic-response": {
                "status": "ok",
                "nowPlaying": {"entry": [{**entry, "positionMs": 10_000}]},
            }
        },
    ]
    t0 = datetime(2024, 3, 24, 12, 0, tzinfo=timezone.utc)
    fake_datetime = MagicMock()
    fake_datetime.now.side_effect = [t0, t0 + timedelta(seconds=10)]
    monkeypatch.setattr("src.collectors.datetime", fake_datetime)
    sleep_count = 0

    async def stop_after_second_poll(_seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr("src.collectors.asyncio.sleep", stop_after_second_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT COUNT(*), listen_duration_sec, duration_confidence, finalized,
               source_id
        FROM play_history
        """
    ).fetchone()
    conn.close()

    assert row == (1, 10, "reported", 0, "synthetic-source")


@pytest.mark.asyncio
async def test_ok_null_now_playing_is_empty_success(monkeypatch):
    import src.collectors as main
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(main, "runtime_state", state)
    tracker = PlaybackSessionTracker(AsyncMock())
    client = AsyncMock()
    client.supports_playback_report.return_value = False
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": None}
    }

    async def stop_after_first_poll(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main.asyncio, "sleep", stop_after_first_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    assert state.poll_success_count == 1
    assert state.poll_failure_count == 0
    assert tracker._sessions == {}


@pytest.mark.asyncio
async def test_ok_poll_records_success_when_persistence_fails(monkeypatch):
    import src.collectors as main
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(main, "runtime_state", state)
    tracker = PlaybackSessionTracker(AsyncMock())
    tracker.process_poll = AsyncMock(
        side_effect=PlaybackPersistenceError("synthetic save failure")
    )
    client = AsyncMock()
    client.supports_playback_report.return_value = False
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }
    slept = []

    async def stop_after_first_poll(seconds):
        slept.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(main.asyncio, "sleep", stop_after_first_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    assert state.poll_success_count == 1
    assert state.poll_failure_count == 0
    assert state.last_save_ok is False
    assert slept == [main.POLL_INTERVAL]
    tracker.process_poll.assert_awaited_once()

    alive = asyncio.create_task(asyncio.Event().wait())
    state.client_initialized = True
    state.set_collector_task(tracker.source_id, alive)
    monkeypatch.setattr(main, "ping_db", AsyncMock(return_value=True))
    try:
        report = await main.build_readiness_report()
    finally:
        alive.cancel()
        await asyncio.gather(alive, return_exceptions=True)

    assert report["checks"]["upstream"] == "ok"
    assert report["checks"]["persistence"] == "error"
    assert report["status"] == "not_ready"


@pytest.mark.asyncio
async def test_ok_poll_treats_tracker_failure_as_cycle_failure(monkeypatch):
    import src.collectors as main
    from src.runtime_state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(main, "runtime_state", state)
    tracker = PlaybackSessionTracker(AsyncMock())
    tracker.process_poll = AsyncMock(side_effect=RuntimeError("synthetic tracker failure"))
    client = AsyncMock()
    client.supports_playback_report.return_value = False
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}
    }
    slept = []

    async def stop_after_second_poll(seconds):
        slept.append(seconds)
        if len(slept) == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(main.asyncio, "sleep", stop_after_second_poll)

    with pytest.raises(asyncio.CancelledError):
        await polling_loop_for_tracker(client, tracker)

    assert state.poll_success_count == 0
    assert state.poll_failure_count == 2
    assert slept == [main.POLL_INTERVAL, main.POLL_INTERVAL * 2]
    assert tracker.process_poll.await_count == 2
