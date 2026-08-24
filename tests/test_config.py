"""Tests for ``src.config`` safe env-int parsing and clamping."""

from pathlib import Path

import pytest

from src.config import env_flag, env_int, parse_clamped_int


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


COLLECTOR_ENV_CONTRACT = {
    # variable: (default, min, max)
    "POLL_INTERVAL": (10, 5, 300),
    "MAX_POLL_BACKOFF_SEC": (60, 1, 3600),
    "PLAY_THRESHOLD_SEC": (30, 1, 3600),
    "PAUSE_GRACE_SEC": (30, 0, 3600),
    "CHECKPOINT_INTERVAL_SEC": (60, 10, 3600),
}


def test_collector_constants_match_the_declared_env_contract():
    collectors_source = (
        Path(__file__).resolve().parent.parent / "src" / "collectors.py"
    ).read_text(encoding="utf-8")
    for name, (default, mn, mx) in COLLECTOR_ENV_CONTRACT.items():
        contract = f'"{name}", default={default}, min_value={mn}, max_value={mx}'
        assert contract in collectors_source, name


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("POLL_INTERVAL", "not-a-number", 10),
        ("POLL_INTERVAL", "3", 5),
        ("POLL_INTERVAL", "9999", 300),
        ("MAX_POLL_BACKOFF_SEC", "0", 1),
        ("PLAY_THRESHOLD_SEC", "0", 1),
        ("PLAY_THRESHOLD_SEC", "7200", 3600),
        ("PAUSE_GRACE_SEC", "0", 0),
        ("CHECKPOINT_INTERVAL_SEC", "5", 10),
    ],
)
def test_collector_settings_clamp_like_their_contract(monkeypatch, name, raw, expected):
    default, mn, mx = COLLECTOR_ENV_CONTRACT[name]
    monkeypatch.setenv(name, raw)
    assert env_int(name, default=default, min_value=mn, max_value=mx) == expected
    monkeypatch.delenv(name, raising=False)


def test_env_flag_defaults_and_truthy_values(monkeypatch):
    monkeypatch.delenv("NDS_TEST_FLAG", raising=False)
    assert env_flag("NDS_TEST_FLAG", default=True) is True
    assert env_flag("NDS_TEST_FLAG", default=False) is False
    monkeypatch.setenv("NDS_TEST_FLAG", "true")
    assert env_flag("NDS_TEST_FLAG", default=False) is True
    monkeypatch.setenv("NDS_TEST_FLAG", "YES")
    assert env_flag("NDS_TEST_FLAG", default=False) is True
    monkeypatch.setenv("NDS_TEST_FLAG", "0")
    assert env_flag("NDS_TEST_FLAG", default=True) is False
    monkeypatch.setenv("NDS_TEST_FLAG", "nope")
    assert env_flag("NDS_TEST_FLAG", default=True) is False
