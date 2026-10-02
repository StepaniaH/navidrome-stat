"""Preview or apply missing artist credits to an offline Navidrome Stat database.

Run with ``python -m src.artist_backfill --help``. Stop the application before
applying changes so active sessions and process-local caches are not stale.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from src import config
from src.artist_credits import encode_artists
from src.artist_metadata import ArtistMetadataResolver
from src.client import NavidromeClient
from src.server_registry import get_server
from src.sqlite import connect_db

# ListenBrainz recording IDs are not Navidrome song IDs, even when source IDs
# happen to match. Never use them for getSong or update those rows by track ID.
_HISTORY_FILTER = "source IN ('poller', 'backfill', 'song_history')"


async def preview_artist_backfill(
    db_path: str,
    source_id: str,
    resolver: ArtistMetadataResolver,
    *,
    limit: int = 100,
    after_track_id: str = "",
) -> dict:
    """Read one bounded page and resolve credits without changing history."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    async with connect_db(db_path) as db:
        async with db.execute(
            f"""
            SELECT track_id, SUM(history_rows), SUM(attempt_rows) FROM (
                SELECT track_id, COUNT(*) AS history_rows, 0 AS attempt_rows
                FROM play_history
                WHERE source_id = ? AND {_HISTORY_FILTER}
                    AND artists IS NULL AND track_id > ? AND length(track_id) <= 128
                GROUP BY track_id
                UNION ALL
                SELECT track_id, 0 AS history_rows, COUNT(*) AS attempt_rows
                FROM play_attempts
                WHERE source_id = ? AND artists IS NULL
                    AND track_id > ? AND length(track_id) <= 128
                GROUP BY track_id
            ) GROUP BY track_id ORDER BY track_id LIMIT ?
            """,
            (source_id, after_track_id, source_id, after_track_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    changes = []
    for track_id, history_rows, attempt_rows in rows:
        artists = await resolver.get_artists(track_id)
        if artists:
            changes.append({
                "track_id": track_id,
                "artists": artists,
                "history_rows": history_rows,
                "attempt_rows": attempt_rows,
            })
    return {
        "source_id": source_id,
        "tracks_checked": len(rows),
        "tracks_resolved": len(changes),
        "unresolved_tracks": len(rows) - len(changes),
        "history_rows": sum(change["history_rows"] for change in changes),
        "attempt_rows": sum(change["attempt_rows"] for change in changes),
        "next_after_track_id": rows[-1][0] if len(rows) == limit else None,
        "changes": changes,
    }


async def apply_artist_backfill(db_path: str, preview: dict) -> dict[str, int]:
    """Fill only still-missing credits; preserve identities, durations and counts."""
    updated = {"history_rows": 0, "attempt_rows": 0}
    async with connect_db(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for change in preview["changes"]:
                artists = encode_artists(change["artists"])
                if not artists:
                    continue
                for table, key, condition in (
                    ("play_history", "history_rows", _HISTORY_FILTER),
                    ("play_attempts", "attempt_rows", "1 = 1"),
                ):
                    cursor = await db.execute(
                        f"UPDATE {table} SET artists = ? "
                        f"WHERE source_id = ? AND track_id = ? AND {condition} "
                        "AND artists IS NULL",
                        (artists, preview["source_id"], change["track_id"]),
                    )
                    updated[key] += cursor.rowcount
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return updated


async def _run(args) -> dict:
    if not Path(args.database).is_file():
        raise ValueError("database must already exist")
    if args.source_id == "legacy":
        client = NavidromeClient()
    else:
        server = await get_server(args.source_id, args.database)
        if not server or not all(server.get(key) for key in ("url", "username", "password")):
            raise ValueError("source must have a saved connection with readable credentials")
        client = NavidromeClient(server["url"], server["username"], server["password"])
    try:
        preview = await preview_artist_backfill(
            args.database, args.source_id, ArtistMetadataResolver(client),
            limit=args.limit, after_track_id=args.after_track_id,
        )
        result = {"mode": "apply" if args.apply else "preview", **preview}
        if args.apply:
            result["updated"] = await apply_artist_backfill(args.database, preview)
        return result
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-id", required=True, help="Saved source ID, or legacy for env configuration",
    )
    parser.add_argument("--database", default=os.getenv("DATABASE_URL") or config.DATABASE_PATH)
    parser.add_argument("--limit", type=int, default=100, help="Maximum tracks to check (1–1000)")
    parser.add_argument(
        "--after-track-id", default="", help="Continue after a previous page's next_after_track_id",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes after previewing; stop the app first",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    try:
        result = asyncio.run(_run(args))
    except Exception as exc:
        # Upstream errors and local paths may carry sensitive connection data.
        print(json.dumps({"error": type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
