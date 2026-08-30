from datetime import date

import pytest

from src.stats_scope import StatsScope


def test_scope_is_hashable_and_query_kwargs_match_cache_identity():
    scope = StatsScope.create(
        days=30,
        timezone_name="Asia/Shanghai",
        metric="listen_time",
        source_id="server-1",
        username="alice",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert hash(scope)
    assert scope.query_kwargs() == {
        "days": 30,
        "timezone_name": "Asia/Shanghai",
        "source_id": "server-1",
        "username": "alice",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
    }
    assert scope != StatsScope.create(
        days=30,
        timezone_name="Asia/Shanghai",
        metric="listen_time",
        source_id="server-1",
        username="bob",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"days": 1}, "days must be"),
        ({"days": 30, "timezone_name": "Not/AZone"}, "valid IANA"),
        ({"days": 30, "metric": "duration"}, "metric must be"),
        (
            {"days": 30, "start_date": date(2026, 1, 1)},
            "must be provided together",
        ),
    ],
)
def test_scope_rejects_invalid_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        StatsScope.create(**kwargs)
