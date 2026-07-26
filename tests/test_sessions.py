from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.sessions import PAUSE_GRACE_SEC, PLAY_THRESHOLD_SEC, PlaybackSessionTracker


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
async def test_paused_entry_keeps_session_in_grace(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    # A transient pause within the grace window must not finalize or double-save.
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


@pytest.mark.asyncio
async def test_pause_resume_same_track_continues_session(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active10 = t0 + timedelta(seconds=10)  # extra active interval -> 10s
    t_pause = t0 + timedelta(seconds=20)
    t_resume = t_pause + timedelta(seconds=30)  # idle gap, excluded
    t_resume_active = t_resume + timedelta(seconds=20)  # +20s active -> 30s total

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active10)
    await tracker.process_poll([_entry(is_playing=False)], t_pause)
    # Resume the same track within the grace window: session continues.
    await tracker.process_poll([_entry()], t_resume)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["last_active_at"] == t_resume
    assert tracker.active_sessions["p1"]["first_seen_at"] == t0
    assert tracker.active_sessions["p1"]["active_duration_sec"] == 10.0

    # Finalize after threshold is reached on active time only.
    await tracker.process_poll([_entry()], t_resume_active)
    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    # Duration counts only active observations: (t_active10 - t0)=10s
    # plus (t_resume_active - t_resume)=20s -> 30s. The 30s pause
    # at t_pause..t_resume is excluded.
    assert saved["duration_sec"] == PLAY_THRESHOLD_SEC


@pytest.mark.asyncio
async def test_mid_session_pause_excluded_from_duration(save_mock):
    # Spec example: active t0, active t=10, pause t=20, resume t=50,
    # finalize t=60 => active duration 20, not 60.
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
    # Active time: (t10 - t0)=10s plus (t60 - t50)=10s -> 20s.
    # The 30s pause (t20..t50) is excluded; wall-clock 60s is *not* recorded.
    assert saved["duration_sec"] == 20


@pytest.mark.asyncio
async def test_pause_does_not_advance_listen_duration(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_pause = t0 + timedelta(seconds=20)
    # Still within grace (PAUSE_GRACE_SEC default 30): 20s + 5s = 25s since
    # last active observation, so the in-memory session is kept. Wall-clock
    # advances but listen duration must not include the paused window.
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
    # Beyond PAUSE_GRACE_SEC (30) since last active observation.
    t_after_grace = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 5)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()  # early commit at threshold while playing
    save_mock.reset_mock()

    await tracker.process_poll([_entry(is_playing=False)], t_pause)
    await tracker.process_poll([], t_after_grace)

    # Already committed in-memory session is dropped once; no duplicate save.
    save_mock.assert_not_called()
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_missing_player_resumed_within_grace(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_missing = t0 + timedelta(seconds=10)
    # Within grace (last_active=t0, grace=30): 10 + 15 = 25s since active.
    t_resume = t_missing + timedelta(seconds=15)
    t_done = t_resume + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    # Player disappears entirely (no entry at all, not a paused entry).
    await tracker.process_poll([], t_missing)
    assert "p1" in tracker.active_sessions
    save_mock.assert_not_called()

    # Player comes back actively on the same track within grace.
    await tracker.process_poll([_entry()], t_resume)
    assert tracker.active_sessions["p1"]["last_active_at"] == t_resume

    await tracker.finalize_session("p1")
    # Active duration since first_seen: 0..15=15s + 30s = 45s? No — last_active
    # is t_resume (15s) then we finalize immediately after, duration = 15-0 = 15
    # which is below threshold; no save.
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_committed_missing_within_grace_remains_beyond_grace_dropped(
    tracker, save_mock
):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_missing_in = t_active + timedelta(seconds=5)  # within grace (30)
    t_beyond = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 1)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()  # early commit at threshold while playing

    # Player disappears but still inside the grace window: session kept,
    # no duplicate save.
    await tracker.process_poll([], t_missing_in)
    assert "p1" in tracker.active_sessions
    save_mock.assert_awaited_once()

    # Beyond grace: committed in-memory session is dropped once without a
    # duplicate save.
    await tracker.process_poll([], t_beyond)
    assert "p1" not in tracker.active_sessions
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_player_beyond_grace_finalizes(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    # Missing for longer than grace since last active observation.
    t_after_grace = t_active + timedelta(seconds=PLAY_THRESHOLD_SEC + 1)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()  # early commit at threshold
    save_mock.reset_mock()

    await tracker.process_poll([], t_after_grace)

    save_mock.assert_not_called()  # no double commit
    assert "p1" not in tracker.active_sessions


@pytest.mark.asyncio
async def test_no_duplicate_commit_on_repeated_active_polls(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t1)
    assert tracker.active_sessions["p1"]["committed"] is True

    # Continued active polls must not re-commit the same session.
    await tracker.process_poll([_entry()], t1 + timedelta(seconds=30))
    await tracker.process_poll([_entry()], t1 + timedelta(seconds=60))
    save_mock.assert_awaited_once()
    assert tracker.active_sessions["p1"]["committed"] is True


@pytest.mark.asyncio
async def test_different_active_track_finalizes_old_immediately(tracker, save_mock):
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)
    t_other = t_active + timedelta(seconds=5)

    await tracker.process_poll([_entry(track_id="t1")], t0)
    await tracker.process_poll([_entry(track_id="t1")], t_active)
    save_mock.assert_awaited_once()  # threshold reached
    save_mock.reset_mock()

    # Different actively-playing track on the same player: finalize (already
    # committed, just drops) and start fresh, no duplicate save.
    await tracker.process_poll(
        [_entry(track_id="t2", title="Song 2")], t_other
    )

    save_mock.assert_not_called()
    assert tracker.active_sessions["p1"]["track_id"] == "t2"


@pytest.mark.asyncio
async def test_threshold_and_grace_params_independent(tracker, save_mock):
    """The threshold and grace defaults are independent."""
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
    """Active session reaches threshold (committed), then Navidrome keeps
    reporting the same track as ``isPlaying=false``. The in-memory session
    must remain inside the grace window and be expired (dropped without a
    duplicate save) once grace elapses since the last active observation."""
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_awaited_once()  # early commit at threshold while playing
    save_mock.reset_mock()

    # Repeated matching paused polls well inside the grace window keep the
    # in-memory session alive and marked paused, without re-saving.
    t_pause_1 = t_active + timedelta(seconds=5)
    t_pause_2 = t_active + timedelta(seconds=20)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_1)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_2)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["paused"] is True
    assert tracker.active_sessions["p1"]["committed"] is True
    save_mock.assert_not_called()

    # A further repeated paused poll beyond grace expires the committed
    # in-memory session once, with no duplicate save.
    t_beyond = t_active + timedelta(seconds=PAUSE_GRACE_SEC + 1)
    await tracker.process_poll([_entry(is_playing=False)], t_beyond)
    assert "p1" not in tracker.active_sessions
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_paused_polls_finalize_uncommitted_after_grace(
    tracker, save_mock
):
    """An uncommitted (sub-threshold) session that Navidrome keeps reporting
    as ``isPlaying=false`` must be finalized once grace elapses, even when the
    pause is represented by repeated paused entries rather than a gap. Since
    accumulated active duration is below threshold, no save occurs."""
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Sub-threshold active observation: still below threshold, no commit.
    t_active = t0 + timedelta(seconds=PLAY_THRESHOLD_SEC - 10)

    await tracker.process_poll([_entry()], t0)
    await tracker.process_poll([_entry()], t_active)
    save_mock.assert_not_called()
    assert not tracker.active_sessions["p1"].get("committed")

    # Repeated matching paused polls within grace keep the session.
    t_pause_1 = t_active + timedelta(seconds=5)
    t_pause_2 = t_active + timedelta(seconds=20)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_1)
    await tracker.process_poll([_entry(is_playing=False)], t_pause_2)
    assert "p1" in tracker.active_sessions
    assert tracker.active_sessions["p1"]["paused"] is True
    save_mock.assert_not_called()

    # Beyond grace: uncommitted session finalizes once. Active duration is
    # below threshold, so no save; the session is removed.
    t_beyond = t_active + timedelta(seconds=PAUSE_GRACE_SEC + 1)
    await tracker.process_poll([_entry(is_playing=False)], t_beyond)
    assert "p1" not in tracker.active_sessions
    save_mock.assert_not_called()
