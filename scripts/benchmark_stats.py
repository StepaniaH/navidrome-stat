"""Reproducible synthetic performance baseline for dashboard queries."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard_cache import DashboardSnapshotCache  # noqa: E402
from src.database import (  # noqa: E402
    get_data_relations,
    get_playback_history,
    get_summary,
    get_time_bucket_stats,
    init_db,
)
from src.persistence import save_play_session  # noqa: E402
from src.stats_read_repository import StatsReadRepository  # noqa: E402
from src.stats_scope import StatsScope  # noqa: E402
from src.stats_service import StatsService  # noqa: E402

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
        int(played_at.timestamp()),
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
            played_at, played_at_epoch, username, client_name, track_id, title, artist, album,
            is_transcoding, listen_duration_sec, source, source_id, source_name,
            finalized
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
              AND played_at_epoch >= ? AND played_at_epoch < ?
            GROUP BY COALESCE(source_id, 'legacy'), username, track_id
            """,
            (
                "synthetic-source-0",
                "synthetic-user-0",
                1_704_067_200,
                1_735_689_600,
            ),
        ).fetchall()
    details = [str(row[3]) for row in rows]
    expected = "idx_play_history_source_user_epoch"
    return {
        "details": details,
        "expected_index": expected,
        "uses_expected_index": any(expected in detail for detail in details),
    }


async def measure_write_load(db_path: str, scope: StatsScope, samples: int) -> dict:
    query_timings = {}

    class MeasuredRepository(StatsReadRepository):
        async def _timed(self, query, operation):
            started = time.perf_counter()
            try:
                return await super()._timed(query, operation)
            finally:
                query_timings[query] = round((time.perf_counter() - started) * 1_000, 2)

    service = StatsService(
        cache=DashboardSnapshotCache(), read_repository=MeasuredRepository(db_path),
    )
    stop = asyncio.Event()
    writes = 0

    async def writer():
        nonlocal writes
        while not stop.is_set():
            await save_play_session({
                "last_seen_at": "2024-07-01T12:00:00+00:00",
                "username": "synthetic-writer", "client_name": "benchmark",
                "track_id": f"write-{writes}", "title": "Synthetic write",
                "artist": "Synthetic writer", "album": "Synthetic album",
                "duration_sec": 60, "source_id": "synthetic-source-0",
            }, db_path=db_path)
            # This is the same write -> invalidation boundary as StatsService,
            # with an explicit temporary path instead of application config.
            await service.invalidate()
            writes += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.1)
            except TimeoutError:
                pass

    task = asyncio.create_task(writer())
    timings = []
    try:
        for _ in range(samples):
            await service.invalidate()
            query_timings.clear()
            dashboard, relations = await asyncio.gather(
                measure(lambda: service.dashboard(scope)),
                measure(lambda: service.data_relations(scope, "artist")),
            )
            timings.append({
                "dashboard_ms": round(dashboard, 2),
                "relations_ms": round(relations, 2),
                "queries_ms": dict(query_timings),
            })
    finally:
        stop.set()
        await task
    return {"samples": timings, "successful_writes": writes, "write_interval_ms": 100}


async def benchmark_size(rows: int, write_samples: int = 0) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="navidrome-stat-benchmark-") as tmp:
        db_path = str(Path(tmp) / "synthetic.db")
        await init_db(db_path)
        seed_ms = seed(db_path, rows)
        window = {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 12, 31),
        }
        relation_scope = StatsScope.create(
            days=0,
            timezone_name="UTC",
            metric="plays",
            **window,
        )
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
                    **window,
                )
            ),
            "history_filtered": await measure(
                lambda: get_playback_history(
                    limit=50,
                    days=0,
                    source_id="synthetic-source-0",
                    username="synthetic-user-0",
                    db_path=db_path,
                    **window,
                )
            ),
            "relations_artist_all": await measure(
                lambda: get_data_relations(
                    relation_scope,
                    "artist",
                    db_path=db_path,
                )
            ),
            "relations_album_all": await measure(
                lambda: get_data_relations(
                    relation_scope,
                    "album",
                    db_path=db_path,
                )
            ),
            "relations_client_all": await measure(
                lambda: get_data_relations(
                    relation_scope,
                    "client",
                    db_path=db_path,
                )
            ),
        }
        filtered_scope = StatsScope.create(
            days=0, timezone_name="UTC", source_id="synthetic-source-0",
            username="synthetic-user-0", **window,
        )
        return {
            "write_load": await measure_write_load(db_path, relation_scope, write_samples) if write_samples else None,
            "write_load_filtered": await measure_write_load(db_path, filtered_scope, write_samples) if write_samples else None,
            "rows": rows,
            "seed_ms": round(seed_ms, 2),
            "queries_ms": {name: round(value, 2) for name, value in scenarios.items()},
            "query_plan": filtered_history_plan(db_path),
        }


async def run(sizes: list[int], max_query_ms: float | None = None, write_samples: int = 0) -> dict[str, object]:
    results = [await benchmark_size(size, write_samples) for size in sizes]
    failures = []
    for result in results:
        if not result["query_plan"]["uses_expected_index"]:
            failures.append(f"{result['rows']} rows: filtered history index not used")
        if max_query_ms is not None:
            failures.extend(
                f"{result['rows']} rows: {name} took {elapsed} ms (budget {max_query_ms} ms)"
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
            f"{name}_ms={elapsed:.2f}" for name, elapsed in result["queries_ms"].items()
        )
        print(
            f"rows={result['rows']} seed_ms={result['seed_ms']:.2f} "
            f"{timings} index_ok={str(result['query_plan']['uses_expected_index']).lower()}"
        )
        if result.get("write_load"):
            print("write_load=" + json.dumps(result["write_load"]))
            print("write_load_filtered=" + json.dumps(result["write_load_filtered"]))
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
    parser.add_argument("--write-samples", type=int, default=0, choices=range(0, 21), help="optional repeated dashboard/relations reads during writes (0-20)")
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
    report = asyncio.run(run(sizes, args.max_query_ms, args.write_samples))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
