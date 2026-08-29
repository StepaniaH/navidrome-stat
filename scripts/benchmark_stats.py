"""Reproducible synthetic performance baseline for dashboard queries."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (  # noqa: E402
    get_playback_history,
    get_summary,
    get_time_bucket_stats,
    init_db,
)

MAX_ROWS = 1_000_000
SEED_BATCH_SIZE = 10_000


def parse_sizes(raw: str) -> list[int]:
    try:
        sizes = [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from exc
    if not sizes or any(value < 1 or value > MAX_ROWS for value in sizes):
        raise argparse.ArgumentTypeError(f"sizes must be between 1 and {MAX_ROWS}")
    return list(dict.fromkeys(sizes))


def _seed_row(index: int, start: datetime) -> tuple:
    played_at = start + timedelta(minutes=index % (366 * 24 * 60))
    source_number = index % 4
    return (
        played_at.isoformat(),
        f"synthetic-user-{index % 8}",
        f"client-{index % 5}",
        f"synthetic-track-{index % 2_000}",
        f"Synthetic track {index % 2_000}",
        f"Synthetic artist {index % 120}",
        f"Synthetic album {index % 400}",
        index % 6 == 0,
        30 + index % 270,
        "poller",
        f"synthetic-source-{source_number}",
        f"Synthetic source {source_number}",
    )


def seed(db_path: str, rows: int) -> float:
    started = time.perf_counter()
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    statement = """
        INSERT INTO play_history (
            played_at, username, client_name, track_id, title, artist, album,
            is_transcoding, listen_duration_sec, source, source_id, source_name,
            finalized
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """
    with sqlite3.connect(db_path) as db:
        for batch_start in range(0, rows, SEED_BATCH_SIZE):
            batch_end = min(rows, batch_start + SEED_BATCH_SIZE)
            db.executemany(
                statement,
                (_seed_row(index, start) for index in range(batch_start, batch_end)),
            )
        db.execute("ANALYZE")
    return (time.perf_counter() - started) * 1_000


async def measure(operation: Callable[[], Awaitable[object]]) -> float:
    started = time.perf_counter()
    await operation()
    return (time.perf_counter() - started) * 1_000


def filtered_history_plan(db_path: str) -> dict[str, object]:
    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT COALESCE(source_id, 'legacy'), username, track_id, MAX(id)
            FROM play_history
            WHERE source_id = ? AND username = ?
            GROUP BY COALESCE(source_id, 'legacy'), username, track_id
            """,
            ("synthetic-source-0", "synthetic-user-0"),
        ).fetchall()
    details = [str(row[3]) for row in rows]
    expected = "idx_play_history_source_user_track"
    return {
        "details": details,
        "expected_index": expected,
        "uses_expected_index": any(expected in detail for detail in details),
    }


async def benchmark_size(rows: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="navidrome-stat-benchmark-") as tmp:
        db_path = str(Path(tmp) / "synthetic.db")
        await init_db(db_path)
        seed_ms = seed(db_path, rows)
        scenarios = {
            "time_buckets_all": await measure(
                lambda: get_time_bucket_stats(days=0, db_path=db_path)
            ),
            "summary_filtered": await measure(
                lambda: get_summary(
                    days=0,
                    source_id="synthetic-source-0",
                    username="synthetic-user-0",
                    db_path=db_path,
                )
            ),
            "history_filtered": await measure(
                lambda: get_playback_history(
                    limit=50,
                    days=0,
                    source_id="synthetic-source-0",
                    username="synthetic-user-0",
                    db_path=db_path,
                )
            ),
        }
        return {
            "rows": rows,
            "seed_ms": round(seed_ms, 2),
            "queries_ms": {name: round(value, 2) for name, value in scenarios.items()},
            "query_plan": filtered_history_plan(db_path),
        }


async def run(sizes: list[int], max_query_ms: float | None = None) -> dict[str, object]:
    results = [await benchmark_size(size) for size in sizes]
    failures = []
    for result in results:
        if not result["query_plan"]["uses_expected_index"]:
            failures.append(f'{result["rows"]} rows: filtered history index not used')
        if max_query_ms is not None:
            failures.extend(
                f'{result["rows"]} rows: {name} took {elapsed} ms (budget {max_query_ms} ms)'
                for name, elapsed in result["queries_ms"].items()
                if elapsed > max_query_ms
            )
    return {
        "schema_version": 1,
        "max_query_ms": max_query_ms,
        "results": results,
        "failures": failures,
        "passed": not failures,
    }


def print_human(report: dict[str, object]) -> None:
    for result in report["results"]:
        timings = " ".join(
            f"{name}_ms={elapsed:.2f}"
            for name, elapsed in result["queries_ms"].items()
        )
        print(
            f'rows={result["rows"]} seed_ms={result["seed_ms"]:.2f} '
            f'{timings} index_ok={str(result["query_plan"]["uses_expected_index"]).lower()}'
        )
    for failure in report["failures"]:
        print(f"FAIL: {failure}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        type=parse_sizes,
        default=parse_sizes("100000"),
        help="comma-separated history sizes, up to 1000000 (default: 100000)",
    )
    parser.add_argument("--rows", type=int, help="deprecated single-size alias for --sizes")
    parser.add_argument(
        "--max-query-ms",
        type=float,
        help="fail when any measured query exceeds this duration",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()
    sizes = args.sizes
    if args.rows is not None:
        try:
            sizes = parse_sizes(str(args.rows))
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    if args.max_query_ms is not None and args.max_query_ms <= 0:
        parser.error("--max-query-ms must be greater than zero")
    report = asyncio.run(run(sizes, args.max_query_ms))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
