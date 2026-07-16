import asyncio

import pytest

from src.database import get_playback_history, init_db, save_play_session


MALICIOUS_TITLE = '<img src=x onerror="alert(1)">'
MALICIOUS_USER = '"><script>evil()</script>'


@pytest.mark.asyncio
async def test_history_preserves_untrusted_metadata_verbatim(db_path):
    await init_db(db_path)
    await save_play_session(
        {
            "last_seen_at": "2026-01-01T12:00:00+00:00",
            "username": MALICIOUS_USER,
            "client_name": "Web",
            "track_id": "track-1",
            "title": MALICIOUS_TITLE,
            "artist": "Artist & Co",
            "album": "Album <b>bold</b>",
            "is_transcoding": 0,
            "duration_sec": 45,
        },
        db_path=db_path,
    )

    rows = await get_playback_history(limit=10, db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["title"] == MALICIOUS_TITLE
    assert rows[0]["username"] == MALICIOUS_USER
