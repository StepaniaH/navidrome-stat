from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.sessions import (
    PAUSE_GRACE_SEC,
    PLAY_THRESHOLD_SEC,
    PlaybackPersistenceError,
    PlaybackSessionTracker,
)


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
async def test_track_change_updates_early_checkpoint_with_final_duration(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t2 = t1 + timedelta(seconds=60)

    await tracker.process_poll([_entry(track_id="t1")], t0)
    await tracker.process_poll([_entry(track_id="t1")], t1)
    await tracker.process_poll([_entry(track_id="t1")], t2)
    await tracker.process_poll(
        [_entry(track_id="t2", title="Song 2")],
        t2 + timedelta(seconds=1),
    )

    assert save_mock.await_count == 3
    checkpoint, refreshed, final = [
        call.args[0] for call in save_mock.await_args_list
    ]
    assert checkpoint["session_id"] == final["session_id"]
    assert refreshed["session_id"] == final["session_id"]
    assert checkpoint["duration_sec"] == PLAY_THRESHOLD_SEC
    assert checkpoint["finalized"] is False
    assert refreshed["duration_sec"] == PLAY_THRESHOLD_SEC + 60
    assert refreshed["finalized"] is False
    assert final["duration_sec"] == PLAY_THRESHOLD_SEC + 60
    assert final["finalized"] is True
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

    assert save_mock.await_count == 2
    saved = save_mock.await_args_list[-1].args[0]
    assert saved["track_id"] == "t1"
    assert saved["duration_sec"] == PLAY_THRESHOLD_SEC
    assert tracker.active_sessions["p1"]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_short_session_discarded(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

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

    assert save_mock.await_count == 2
    assert save_mock.await_args_list[-1].args[0]["duration_sec"] == PLAY_THRESHOLD_SEC
    assert save_mock.await_args_list[-1].args[0]["finalized"] is True


@pytest.mark.asyncio
async def test_paused_entry_keeps_session_in_grace(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    # A pause inside the grace window keeps the committed session open.
    await tracker.process_poll([_entry(is_playing=False)], t1)

    save_mock.assert_awaited_once()
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["paused"] is True


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

    assert save_mock.await_count == 2
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_finalize_all_on_shutdown(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry(player_id="p1"), _entry(player_id="p2", track_id="t2")], t0)
    await tracker.process_poll([_entry(player_id="p1"), _entry(player_id="p2", track_id="t2")], t1)
    await tracker.finalize_all()

    assert save_mock.await_count == 4
    assert tracker.active_sessions == {}


@pytest.mark.asyncio
async def test_finalize_all_continues_after_one_session_fails():
    save = AsyncMock(
        side_effect=[
            RuntimeError("synthetic persistence failure"),
            None,
        ]
    )
    tracker = PlaybackSessionTracker(save, play_threshold_sec=1)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for player_id in ("p1", "p2"):
        await tracker.process_poll([_entry(player_id=player_id)], t0)
        tracker.active_sessions[player_id]["active_duration_sec"] = 1

    with pytest.raises(RuntimeError, match="Failed to finalize 1 playback sessions"):
        await tracker.finalize_all()

    assert "p1" in tracker.active_sessions
    assert "p2" not in tracker.active_sessions
    assert save.await_count == 2


@pytest.mark.asyncio
async def test_pause_resume_same_track_continues_session(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active10 = t0 + timedelta(seconds=10)
    t_pause = t0 + timedelta(seconds=20)
    t_resume = t_pause + timedelta(seconds=30)
    t_resume_active = t_resume + timedelta(seconds=20)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active10)
    await tracker.process_poll([_entry(is_playing=False)], t_pause)
    await tracker.process_poll([_entry()], t_resume)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["last_active_at"] == t_resume
    assert tracker.active_sessions["p1"]["first_seen_at"] == t0
    assert tracker.active_sessions["p1"]["active_duration_sec"] == 10.0

    await tracker.process_poll([_entry()], t_resume_active)
    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    # The two active intervals total 30 seconds; the pause is excluded.
    assert saved["duration_sec"] == PLAY_THRESHOLD_SEC


@pytest.mark.asyncio
async def test_mid_session_pause_excluded_from_duration(save_mock):
    tracker = PlaybackSessionTracker(save_mock, play_threshold_sec=15)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t10 = t0 + timedelta(seconds=10)
    t20 = t0 + timedelta(seconds=20)
    t50 = t0 + timedelta(seconds=50)
    t60 = t0 + timedelta(seconds=60)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t10)
    await tracker.process_poll([_entry(is_playing=False)], t20)
    await tracker.process_poll([_entry()], t50)
    await tracker.process_poll([_entry()], t60)

    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    # Two ten-second active intervals exclude the paused wall-clock time.
    assert saved["duration_sec"] == 20


@pytest.mark.asyncio
async def test_pause_does_not_advance_listen_duration(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_pause = t0 + timedelta(seconds=20)
    # The paused poll remains inside grace without adding listen time.
    t_still_paused = t_pause + timedelta(seconds=5)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry(is_playing=False)], t_pause)
    await tracker.process_poll([_entry(is_playing=False)], t_still_paused)

    session = tracker.active_sessions["p1"]
    assert session["last_active_at"] == t0
    assert session["first_seen_at"] == t0
    assert session["active_duration_sec"] == 0.0
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_long_pause_finalizes_session_once(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_pause = t_active + timedelta(seconds=1)
    t_after_grace = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 5)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()
    save_mock.reset_mock()

    await tracker.process_poll([_entry(is_playing=False)], t_pause)
    await tracker.process_poll([], t_after_grace)

    # Finalization reuses the checkpoint ID so the upsert remains idempotent.
    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["finalized"] is True
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_missing_player_resumed_within_grace(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_missing = t0 + timedelta(seconds=10)
    t_resume = t_missing + timedelta(seconds=15)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([], t_missing)
    assert "p1" in tracker.active_sessions
    save_mock.assert_not_called()

    await tracker.process_poll([_entry()], t_resume)
    assert tracker.active_sessions["p1"]["last_active_at"] == t_resume

    await tracker.finalize_session("p1")
    # Immediate finalization after resume leaves active time below threshold.
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_committed_missing_within_grace_remains_beyond_grace_dropped(
    tracker, save_mock
):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_missing_in = t_active + timedelta(seconds=5)
    t_beyond = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 1)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()

    # A temporary disappearance does not duplicate the checkpoint.
    await tracker.process_poll([], t_missing_in)
    assert "p1" in tracker.active_sessions
    save_mock.assert_awaited_once()

    await tracker.process_poll([], t_beyond)
    assert "p1" not in tracker.active_sessions
    assert save_mock.await_count == 2
    first, final = [call.args[0] for call in save_mock.await_args_list]
    assert first["session_id"] == final["session_id"]
    assert final["finalized"] is True


@pytest.mark.asyncio
async def test_missing_player_beyond_grace_finalizes(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_after_grace = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 1)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()
    save_mock.reset_mock()

    await tracker.process_poll([], t_after_grace)

    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["finalized"] is True
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_periodic_checkpoint_refresh_does_not_duplicate_identity(save_mock):
    tracker = PlaybackSessionTracker(save_mock, checkpoint_interval_sec=60)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    assert tracker.active_sessions["p1"]["committed"] is True

    # Checkpoint refreshes update the same durable session ID.
    await tracker.process_poll([_entry()], t1 + timedelta(seconds=30))
    assert save_mock.await_count == 1
    await tracker.process_poll([_entry()], t1 + timedelta(seconds=60))
    assert save_mock.await_count == 2
    first, refreshed = [call.args[0] for call in save_mock.await_args_list]
    assert first["session_id"] == refreshed["session_id"]
    assert refreshed["duration_sec"] == 90
    assert refreshed["finalized"] is False
    assert tracker.active_sessions["p1"]["committed"] is True


@pytest.mark.asyncio
async def test_different_active_track_finalizes_old_immediately(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_other = t_active + timedelta(seconds=5)

    await tracker.process_poll([_entry(track_id="t1")], t0)
    await tracker.process_poll([_entry(track_id="t1")], t_active)
    save_mock.assert_awaited_once()
    save_mock.reset_mock()

    await tracker.process_poll(
        [_entry(track_id="t2", title="Song 2")], t_other
    )

    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["finalized"] is True
    assert tracker.active_sessions["p1"]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_threshold_and_grace_params_independent(tracker, save_mock):
    custom = PlaybackSessionTracker(
        save_mock, play_threshold_sec=15, pause_grace_sec=10
    )
    assert custom.play_threshold_sec == 15
    assert custom.pause_grace_sec == 10


@pytest.mark.asyncio
async def test_custom_play_threshold_shortens_required_listen(save_mock):
    custom = PlaybackSessionTracker(save_mock, play_threshold_sec=5)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=5)

    await custom.process_poll([_entry()], t0)
    await custom.process_poll([_entry()], t1)

    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["duration_sec"] == 5


@pytest.mark.asyncio
async def test_repeated_paused_polls_expire_committed_after_grace(tracker, save_mock):
    """Repeated paused polls expire a committed session after grace."""
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()
    save_mock.reset_mock()

    # Paused polls inside grace do not rewrite the checkpoint.
    t_pause_1 = t_active + timedelta(seconds=5)
    t_pause_2 = t_active + timedelta(seconds=20)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_1)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_2)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["paused"] is True
    assert tracker.active_sessions["p1"]["committed"] is True
    save_mock.assert_not_called()

    t_beyond = t_active + timedelta(seconds=PAUSE_GRACE_SEC + 1)
    await tracker.process_poll([_entry(is_playing=False)], t_beyond)
    assert "p1" not in tracker.active_sessions
    save_mock.assert_awaited_once()
    assert save_mock.await_args.args[0]["finalized"] is True


@pytest.mark.asyncio
async def test_failed_threshold_checkpoint_remains_retryable():
    save = AsyncMock(side_effect=[RuntimeError("synthetic persistence failure"), None])
    tracker = PlaybackSessionTracker(save)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    await tracker.process_poll([_entry()], t0)
    with pytest.raises(PlaybackPersistenceError) as exc_info:
        await tracker.process_poll(
            [_entry()],
            t0 + timedelta(seconds=PLAY_THRESHOLD_SEC),
        )
    assert isinstance(exc_info.value.__cause__, RuntimeError)

    session = tracker.active_sessions["p1"]
    session_id = session["session_id"]
    assert session.get("committed") is not True

    await tracker.process_poll(
        [_entry()],
        t0 + timedelta(seconds=PLAY_THRESHOLD_SEC + 10),
    )
    assert tracker.active_sessions["p1"]["committed"] is True
    assert save.await_args.args[0]["session_id"] == session_id


@pytest.mark.asyncio
async def test_failed_final_update_keeps_session_for_retry():
    save = AsyncMock()
    tracker = PlaybackSessionTracker(save)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll(
        [_entry()],
        t0 + timedelta(seconds=PLAY_THRESHOLD_SEC),
    )
    save.side_effect = RuntimeError("synthetic finalization failure")

    with pytest.raises(PlaybackPersistenceError) as exc_info:
        await tracker.finalize_session("p1")
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "p1" in tracker.active_sessions

    save.side_effect = None
    await tracker.finalize_session("p1")
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_playback_report_state_and_position_exclude_pause():
    save = AsyncMock()
    tracker = PlaybackSessionTracker(
        save,
        play_threshold_sec=15,
        pause_grace_sec=60,
        supports_playback_report=True,
    )
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    await tracker.process_poll(
        [{**_entry(), "state": "playing", "positionMs": 0, "playbackRate": 1}],
        t0,
    )
    await tracker.process_poll(
        [{**_entry(), "state": "playing", "positionMs": 10_000, "playbackRate": 1}],
        t0 + timedelta(seconds=10),
    )
    await tracker.process_poll(
        [{**_entry(), "state": "paused", "positionMs": 10_000}],
        t0 + timedelta(seconds=20),
    )
    await tracker.process_poll(
        [{**_entry(), "state": "playing", "positionMs": 10_000}],
        t0 + timedelta(seconds=40),
    )
    await tracker.process_poll(
        [{**_entry(), "state": "playing", "positionMs": 15_000}],
        t0 + timedelta(seconds=45),
    )

    saved = save.await_args.args[0]
    assert saved["duration_sec"] == 15
    assert saved["duration_confidence"] == "reported"


@pytest.mark.asyncio
async def test_legacy_mode_ignores_unadvertised_playback_report_fields():
    save = AsyncMock()
    tracker = PlaybackSessionTracker(save, play_threshold_sec=10)
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    await tracker.process_poll(
        [{**_entry(), "state": "paused", "positionMs": 0}],
        t0,
    )
    await tracker.process_poll(
        [{**_entry(), "state": "paused", "positionMs": 10_000}],
        t0 + timedelta(seconds=10),
    )

    saved = save.await_args.args[0]
    assert saved["duration_confidence"] == "estimated"


@pytest.mark.asyncio
async def test_repeated_paused_polls_finalize_uncommitted_after_grace(
    tracker, save_mock
):
    """Repeated paused polls discard a sub-threshold session after grace."""
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC - 10)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_not_called()
    assert not tracker.active_sessions["p1"].get("committed")

    t_pause_1 = t_active + timedelta(seconds=5)
    t_pause_2 = t_active + timedelta(seconds=20)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_1)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_2)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["paused"] is True
    save_mock.assert_not_called()

    t_beyond = t_active + timedelta(seconds=PAUSE_GRACE_SEC + 1)
    await tracker.process_poll([_entry(is_playing=False)], t_beyond)
    assert "p1" not in tracker.active_sessions
    save_mock.assert_not_called()
