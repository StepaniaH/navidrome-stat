from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.sessions import PLAY_THRESHOLD_SEC, PlaybackSessionTracker


def _entry(
    *,
    player_id="p1",
    track_id="t1",
    is_playing=True,
    username="user_a",
    title="Song 1",
):
    entry = {
        "playerId": player_id,
        "id": track_id,
        "username": username,
        "playerName": "Test Player",
        "title": title,
        "artist": "Artist",
        "album": "Album",
    }
    if is_playing is not None:
        entry["isPlaying"] = is_playing
    return entry


@pytest.fixture
def save_mock():
    return AsyncMock()


@pytest.fixture
def tracker(save_mock):
    return PlaybackSessionTracker(save_mock)


@pytest.mark.asyncio
async def test_same_track_updates_last_seen(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=10)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)

    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["last_seen_at"] == t1
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_early_commit_at_threshold_while_still_playing(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)

    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["duration_sec"] == PLAY_THRESHOLD_SEC
    assert tracker.active_sessions["p1"]["committed"] is True


@pytest.mark.asyncio
async def test_track_change_after_early_commit_does_not_double_save(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t2 = t1 + timedelta(seconds=60)

    await tracker.process_poll([_entry(track_id="t1")], t0)
    await tracker.process_poll([_entry(track_id="t1")], t1)
    await tracker.process_poll([_entry(track_id="t2", title="Song 2")], t2)

    save_mock.assert_awaited_once()
    assert tracker.active_sessions["p1"]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_track_change_finalizes_old_session(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC - 5)
    t2 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t3 = t2 + timedelta(seconds=1)

    await tracker.process_poll([_entry(track_id="t1")], t0)
    await tracker.process_poll([_entry(track_id="t1")], t1)
    await tracker.process_poll([_entry(track_id="t1")], t2)
    await tracker.process_poll([_entry(track_id="t2", title="Song 2")], t3)

    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    assert saved["track_id"] == "t1"
    assert saved["duration_sec"] == PLAY_THRESHOLD_SEC
    assert tracker.active_sessions["p1"]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_short_session_discarded(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC - 1)

    await tracker.process_poll([_entry()], t0)
    await tracker.finalize_session("p1")

    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_exact_threshold_saved(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    await tracker.finalize_session("p1")

    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["duration_sec"] == PLAY_THRESHOLD_SEC


@pytest.mark.asyncio
async def test_paused_entry_finalizes_session(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    await tracker.process_poll([_entry(is_playing=False)], t1)

    save_mock.assert_awaited_once()
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_missing_player_id_skipped(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entry = _entry()
    del entry["playerId"]

    await tracker.process_poll([entry], t0)

    assert tracker.active_sessions == {}


@pytest.mark.asyncio
async def test_stale_player_finalized_after_threshold(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t2 = t1 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    await tracker.process_poll([], t2)

    save_mock.assert_awaited_once()
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_finalize_all_on_shutdown(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry(player_id="p1"), _entry(player_id="p2", track_id="t2")], t0)
    await tracker.process_poll([_entry(player_id="p1"), _entry(player_id="p2", track_id="t2")], t1)
    await tracker.finalize_all()

    assert save_mock.await_count == 2
    assert tracker.active_sessions == {}
