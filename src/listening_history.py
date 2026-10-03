"""Searchable individual listens with stable, bounded keyset pagination."""

import base64
import binascii

import aiosqlite

from src import config
from src.core_types import classify_history_duration_quality
from src.sqlite import connect_db
from src.stats_query_common import scope_predicate
from src.stats_scope import StatsScope


def decode_cursor(cursor: str | None) -> tuple[int, int] | None:
    if cursor is None:
        return None
    try:
        value = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True).decode(
            "ascii"
        )
        epoch, row_id = (int(part) for part in value.split(":"))
        if not -(2**63) <= epoch < 2**63 or not 0 < row_id < 2**63:
            raise ValueError
        return epoch, row_id
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Invalid history cursor") from exc


async def get_listening_history(
    scope: StatsScope,
    *,
    search: str = "",
    cursor: str | None = None,
    limit: int = 50,
    db_path: str | None = None,
) -> dict:
    """Return recordings, never grouped tracks; search treats wildcards literally."""
    position = decode_cursor(cursor)
    predicate, params = scope_predicate(scope)
    predicate += " AND played_at_epoch IS NOT NULL"
    if search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        predicate += " AND (title LIKE ? ESCAPE '\\' OR artist LIKE ? ESCAPE '\\' OR album LIKE ? ESCAPE '\\')"
        params.extend([f"%{term}%"] * 3)
    if position:
        predicate += " AND (played_at_epoch, id) < (?, ?)"
        params.extend(position)
    async with connect_db(db_path or config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""SELECT id, played_at_epoch, played_at, username, client_name,
                       track_id, title, artist, album, album_id,
                       COALESCE(source_id, 'legacy') AS source_id, source_name,
                       listen_duration_sec, source, session_id, finalized, duration_confidence
                FROM play_history WHERE {predicate}
                ORDER BY played_at_epoch DESC, id DESC LIMIT ?""",
            [*params, limit + 1],
        ) as query:
            rows = await query.fetchall()
    items = []
    for row in rows[:limit]:
        item = dict(row)
        item["duration_quality"] = classify_history_duration_quality(
            **{
                key: item[key]
                for key in (
                    "listen_duration_sec",
                    "source",
                    "session_id",
                    "finalized",
                    "duration_confidence",
                )
            }
        )
        for key in ("id", "played_at_epoch", "session_id", "finalized", "duration_confidence"):
            item.pop(key)
        items.append(item)
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            f"{last['played_at_epoch']}:{last['id']}".encode("ascii")
        ).decode("ascii")
    return {"items": items, "next_cursor": next_cursor}
