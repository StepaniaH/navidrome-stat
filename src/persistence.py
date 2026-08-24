"""Durable playback writes.

``save_play_session`` implements a monotonic upsert protocol: checkpoint
retries and final updates reuse the session ID so repeated saves never add
duplicate plays. Duration only grows, confidence escalates from estimated to
reported, and timestamps reconcile to the latest known value.
"""

from src import config
from src.schema import LEGACY_SOURCE_ID, LEGACY_SOURCE_NAME
from src.sqlite import connect_db


def _path(db_path: str | None = None) -> str:
    return config.DATABASE_PATH if db_path is None else db_path


async def save_play_session(session: dict, db_path: str | None = None):
    """Upsert a playback session by ID, or append when the ID is absent.

    Checkpoint retries and final updates reuse the ID to avoid duplicate rows.
    """
    path = _path(db_path)
    async with connect_db(path) as db:
        columns = (
            "played_at, username, client_name, track_id, title, artist, album, "
            "is_transcoding, listen_duration_sec, source, source_id, source_name, "
            "session_id, duration_confidence, finalized, finalized_at, checkpointed_at"
        )
        values = (
            session.get("last_seen_at"),
            session.get("username"),
            session.get("client_name"),
            session.get("track_id"),
            session.get("title"),
            session.get("artist"),
            session.get("album"),
            session.get("is_transcoding"),
            session.get("duration_sec"),
            session.get("source", "poller"),
            session.get("source_id", LEGACY_SOURCE_ID),
            session.get("source_name", LEGACY_SOURCE_NAME),
            session.get("session_id"),
            session.get("duration_confidence", "estimated"),
            int(bool(session.get("finalized", False))),
            session.get("finalized_at"),
            session.get("checkpointed_at", session.get("last_seen_at")),
        )
        if session.get("session_id"):
            await db.execute(
                f"""
                INSERT INTO play_history ({columns})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) WHERE session_id IS NOT NULL DO UPDATE SET
                    played_at=CASE
                        WHEN play_history.played_at IS NULL THEN excluded.played_at
                        WHEN excluded.played_at IS NULL THEN play_history.played_at
                        WHEN julianday(excluded.played_at)
                            >= julianday(play_history.played_at)
                            THEN excluded.played_at
                        ELSE play_history.played_at
                    END,
                    username=excluded.username,
                    client_name=excluded.client_name,
                    track_id=excluded.track_id,
                    title=excluded.title,
                    artist=excluded.artist,
                    album=excluded.album,
                    is_transcoding=excluded.is_transcoding,
                    listen_duration_sec=MAX(
                        COALESCE(play_history.listen_duration_sec, 0),
                        COALESCE(excluded.listen_duration_sec, 0)
                    ),
                    source=excluded.source,
                    source_id=excluded.source_id,
                    source_name=excluded.source_name,
                    duration_confidence=CASE
                        WHEN play_history.duration_confidence = 'reported'
                            OR excluded.duration_confidence = 'reported'
                            THEN 'reported'
                        ELSE COALESCE(
                            excluded.duration_confidence,
                            play_history.duration_confidence,
                            'estimated'
                        )
                    END,
                    finalized=MAX(
                        COALESCE(play_history.finalized, 0),
                        COALESCE(excluded.finalized, 0)
                    ),
                    finalized_at=CASE
                        WHEN play_history.finalized_at IS NULL
                            THEN excluded.finalized_at
                        WHEN excluded.finalized_at IS NULL
                            THEN play_history.finalized_at
                        WHEN julianday(excluded.finalized_at)
                            >= julianday(play_history.finalized_at)
                            THEN excluded.finalized_at
                        ELSE play_history.finalized_at
                    END,
                    checkpointed_at=CASE
                        WHEN play_history.checkpointed_at IS NULL
                            THEN excluded.checkpointed_at
                        WHEN excluded.checkpointed_at IS NULL
                            THEN play_history.checkpointed_at
                        WHEN julianday(excluded.checkpointed_at)
                            >= julianday(play_history.checkpointed_at)
                            THEN excluded.checkpointed_at
                        ELSE play_history.checkpointed_at
                    END
                """,
                values,
            )
        else:
            await db.execute(
                f"""
                INSERT INTO play_history ({columns})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        await db.commit()


async def save_play_attempt(attempt: dict, db_path: str | None = None):
    """Save a below-threshold playback attempt without counting it as a play."""
    path = _path(db_path)
    async with connect_db(path) as db:
        await db.execute("""
            INSERT INTO play_attempts (
                played_at, username, client_name, track_id, title, artist,
                album, is_transcoding, duration_sec, outcome, source_id, source_name,
                attempt_id, duration_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id) WHERE attempt_id IS NOT NULL DO UPDATE SET
                played_at=excluded.played_at,
                duration_sec=excluded.duration_sec,
                duration_confidence=excluded.duration_confidence
        """, (
            attempt.get("last_seen_at"), attempt.get("username"),
            attempt.get("client_name"), attempt.get("track_id"),
            attempt.get("title"), attempt.get("artist"), attempt.get("album"),
            attempt.get("is_transcoding"), int(attempt.get("duration_sec", 0)),
            attempt.get("outcome", "short_play"),
            attempt.get("source_id", LEGACY_SOURCE_ID),
            attempt.get("source_name", LEGACY_SOURCE_NAME),
            attempt.get("session_id"),
            attempt.get("duration_confidence", "estimated"),
        ))
        await db.commit()
