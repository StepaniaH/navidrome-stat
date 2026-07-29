"""Tests for ``src.config`` safe env-int parsing and clamping."""

import importlib

import pytest

from src.config import env_int, parse_clamped_int


@pytest.mark.parametrize(
    "raw,default,mn,mx,expected",
    [
        ("10", 5, 1, 20, 10),
        ("abc", 7, 1, 100, 7),
        ("", 7, 1, 100, 7),
        (None, 7, 1, 100, 7),
        ("  12 ", 5, 1, 20, 12),
        ("3", 10, 5, 300, 5),       # below min -> clamp to min
        ("400", 10, 5, 300, 300),   # above max -> clamp to max
        ("5", 10, 5, 300, 5),
        ("300", 10, 5, 300, 300),
        ("-5", 10, 5, 300, 5),
        ("1.5", 10, 1, 100, 10),    # float string is not an int -> default
    ],
)
def test_parse_clamped_int(raw, default, mn, mx, expected):
    assert parse_clamped_int(
        raw, default=default, min_value=mn, max_value=mx
    ) == expected


def test_env_int_reads_environment(monkeypatch):
    monkeypatch.setenv("NDS_TEST_INT", "42")
    assert env_int("NDS_TEST_INT", default=10, min_value=1, max_value=100) == 42


def test_env_int_missing_returns_default(monkeypatch):
    monkeypatch.delenv("NDS_TEST_INT", raising=False)
    assert env_int("NDS_TEST_INT", default=10, min_value=1, max_value=100) == 10


def test_env_int_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("NDS_TEST_INT", "not-a-number")
    assert env_int("NDS_TEST_INT", default=10, min_value=1, max_value=100) == 10


def test_env_int_clamps_below_min(monkeypatch):
    monkeypatch.setenv("NDS_TEST_INT", "0")
    assert env_int("NDS_TEST_INT", default=10, min_value=5, max_value=300) == 5


def test_env_int_clamps_above_max(monkeypatch):
    monkeypatch.setenv("NDS_TEST_INT", "1000")
    assert env_int("NDS_TEST_INT", default=10, min_value=5, max_value=300) == 300


def test_main_poll_interval_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("POLL_INTERVAL", "not-a-number")
    import src.main as main_module
    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.POLL_INTERVAL == 10
        assert reloaded.PLAY_THRESHOLD_SEC == 30
        assert reloaded.PAUSE_GRACE_SEC == 30
        assert reloaded.MAX_POLL_BACKOFF_SEC == 60
        assert reloaded.CHECKPOINT_INTERVAL_SEC == 60
    finally:
        monkeypatch.delenv("POLL_INTERVAL", raising=False)
        importlib.reload(main_module)


def test_main_poll_interval_clamped_to_bounds(monkeypatch):
    monkeypatch.setenv("POLL_INTERVAL", "3")
    import src.main as main_module
    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.POLL_INTERVAL == 5  # clamped to min
    finally:
        monkeypatch.delenv("POLL_INTERVAL", raising=False)
        importlib.reload(main_module)


def test_main_play_threshold_clamped_to_max(monkeypatch):
    monkeypatch.setenv("PLAY_THRESHOLD_SEC", "99999")
    import src.main as main_module
    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.PLAY_THRESHOLD_SEC == 3600
        assert reloaded.session_tracker.play_threshold_sec == 3600
    finally:
        monkeypatch.delenv("PLAY_THRESHOLD_SEC", raising=False)
        importlib.reload(main_module)


def test_main_pause_grace_clamped_to_min_zero(monkeypatch):
    monkeypatch.setenv("PAUSE_GRACE_SEC", "-5")
    import src.main as main_module
    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.PAUSE_GRACE_SEC == 0
        assert reloaded.session_tracker.pause_grace_sec == 0
    finally:
        monkeypatch.delenv("PAUSE_GRACE_SEC", raising=False)
        importlib.reload(main_module)


def test_main_checkpoint_interval_clamped_to_min(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_INTERVAL_SEC", "1")
    import src.main as main_module

    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.CHECKPOINT_INTERVAL_SEC == 10
        assert reloaded.session_tracker.checkpoint_interval_sec == 10
    finally:
        monkeypatch.delenv("CHECKPOINT_INTERVAL_SEC", raising=False)
        importlib.reload(main_module)
