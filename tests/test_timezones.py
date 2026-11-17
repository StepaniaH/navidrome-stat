"""Timezone fallback with actual TZif files and no backward links."""

import shutil
import zoneinfo
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from src.windows import (
    _played_at_to_local_datetime,
    _window_predicate,
    resolve_timezone,
)

RENAMES = [
    ("Europe/Kiev", "Europe/Kyiv"),
    ("Asia/Calcutta", "Asia/Kolkata"),
    ("Asia/Saigon", "Asia/Ho_Chi_Minh"),
    ("Asia/Rangoon", "Asia/Yangon"),
    ("Asia/Katmandu", "Asia/Kathmandu"),
    ("Asia/Ulan_Bator", "Asia/Ulaanbaatar"),
    ("Asia/Macao", "Asia/Macau"),
]


@pytest.fixture
def canonical_tzdata(tmp_path, monkeypatch):
    """Use only seven canonical files; disable the optional PyPI fallback too."""
    original_path = zoneinfo.TZPATH
    for _, name in RENAMES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = next((Path(root) / name for root in original_path
                       if (Path(root) / name).is_file()), None)
        if source is not None:
            shutil.copyfile(source, destination)
        else:
            # Systems using only the optional tzdata package have no TZPATH files.
            with zoneinfo._common.load_tzdata(name) as stream:
                destination.write_bytes(stream.read())

    def no_package_fallback(key):
        raise ZoneInfoNotFoundError(f"No time zone found with key {key}")

    monkeypatch.setattr(zoneinfo._common, "load_tzdata", no_package_fallback)
    ZoneInfo.clear_cache()
    zoneinfo.reset_tzpath([str(tmp_path)])
    try:
        yield tmp_path
    finally:
        ZoneInfo.clear_cache()
        zoneinfo.reset_tzpath(original_path)


@pytest.mark.parametrize("old,current", RENAMES)
def test_renamed_timezone_without_backward_links(canonical_tzdata, old, current):
    # Prove that neither a cached object nor packaged tzdata masks a missing link.
    assert not (canonical_tzdata / old).exists()
    with pytest.raises(ZoneInfoNotFoundError):
        ZoneInfo(old)

    legacy = resolve_timezone(old)
    canonical = resolve_timezone(current)
    assert legacy.key == current
    # Local date/hour buckets and UTC bounds, including both Kyiv DST changes.
    for timestamp in (
        "2024-01-01T22:30:00Z", "2024-03-31T00:30:00Z",
        "2024-03-31T01:30:00Z", "2024-07-15T22:30:00Z",
        "2024-10-27T00:30:00Z", "2024-10-27T01:30:00Z",
    ):
        assert _played_at_to_local_datetime(timestamp, legacy).isoformat() == (
            _played_at_to_local_datetime(timestamp, canonical).isoformat()
        )
    for day in (date(2024, 3, 31), date(2024, 10, 27)):
        assert _window_predicate(0, old, day, day) == _window_predicate(
            0, current, day, day,
        )


def test_missing_canonical_timezone_still_fails(canonical_tzdata):
    (canonical_tzdata / "Europe/Kyiv").unlink()
    with pytest.raises(ValueError, match="Europe/Kyiv"):
        resolve_timezone("Europe/Kiev")


@pytest.mark.parametrize("name", ["Invalid/Zone", "Europe/Kieev", "US/Eastern"])
def test_unknown_or_unlisted_timezone_is_not_guessed(canonical_tzdata, name):
    with pytest.raises(ValueError, match=name):
        resolve_timezone(name)


def test_available_legacy_name_is_not_replaced(canonical_tzdata):
    shutil.copyfile(canonical_tzdata / "Europe/Kyiv", canonical_tzdata / "Europe/Kiev")
    assert resolve_timezone("Europe/Kiev").key == "Europe/Kiev"


@pytest.mark.parametrize("name", [None, "", "UTC"])
def test_default_timezone_unchanged(name):
    assert resolve_timezone(name).key == "UTC"


def test_non_lookup_errors_are_not_swallowed(monkeypatch):
    def broken_data(_name):
        raise OSError("unreadable tzdata")

    monkeypatch.setattr("src.windows.ZoneInfo", broken_data)
    with pytest.raises(OSError, match="unreadable tzdata"):
        resolve_timezone("Europe/Kiev")
