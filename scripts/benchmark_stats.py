"""Reproducible synthetic benchmark for dashboard time-bucket queries."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.database import (
    get_daily_stats,
    get_hourly_stats,
    get_time_bucket_stats,
    get_weekday_hour_stats,
    init_db,
)


def seed(db_path: str, rows: int) -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = []
    for index in range(rows):
        played_at = start + timedelta(minutes=index % (366 * 24 * 60))
        payload.append(
            (
                played_at.isoformat(),
                f"synthetic-user-{index % 8}",
                f"synthetic-track-{index % 2_000}",
                30 + index % 270,
                "poller",
                "synthetic-source",
            )
        )
    with sqlite3.connect(db_path) as db:
        db.executemany(
            """
            INSERT INTO play_history (
                played_at, username, track_id, listen_duration_sec, source,
                source_id, finalized
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            payload,
        )


async def benchmark(rows: int) -> None:
    with tempfile.TemporaryDirectory(prefix="navidrome-stat-benchmark-") as tmp:
        db_path = str(Path(tmp) / "synthetic.db")
        await init_db(db_path)
        seed(db_path, rows)

        started = time.perf_counter()
        await asyncio.gather(
            get_hourly_stats(days=0, db_path=db_path),
            get_daily_stats(days=0, db_path=db_path),
            get_weekday_hour_stats(days=0, db_path=db_path),
        )
        separate_ms = (time.perf_counter() - started) * 1_000

        started = time.perf_counter()
        await get_time_bucket_stats(days=0, db_path=db_path)
        combined_ms = (time.perf_counter() - started) * 1_000

        print(
            f"rows={rows} separate_ms={separate_ms:.1f} "
            f"combined_ms={combined_ms:.1f} "
            f"speedup={separate_ms / combined_ms:.2f}x"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()
    if args.rows < 1 or args.rows > 1_000_000:
        parser.error("--rows must be between 1 and 1000000")
    asyncio.run(benchmark(args.rows))


if __name__ == "__main__":
    main()
