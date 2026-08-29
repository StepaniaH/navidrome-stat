import argparse

import pytest

from scripts.benchmark_stats import parse_sizes, run


def test_parse_sizes_accepts_multiple_unique_scales():
    assert parse_sizes("1000, 5000,1000") == [1000, 5000]
    with pytest.raises(argparse.ArgumentTypeError):
        parse_sizes("0")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_sizes("1000001")


@pytest.mark.asyncio
async def test_benchmark_report_includes_scenarios_and_index_plan():
    report = await run([250])
    result = report["results"][0]
    assert report["schema_version"] == 1
    assert report["passed"] is True
    assert set(result["queries_ms"]) == {
        "time_buckets_all",
        "summary_filtered",
        "history_filtered",
    }
    assert result["query_plan"]["uses_expected_index"] is True


@pytest.mark.asyncio
async def test_benchmark_budget_can_fail_the_run():
    report = await run([100], max_query_ms=0.0001)
    assert report["passed"] is False
    assert report["failures"]
