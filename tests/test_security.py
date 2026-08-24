
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


@pytest.mark.asyncio
async def test_persistence_error_log_does_not_include_exception_text(
    caplog,
    monkeypatch,
):
    import src.stats_service as main

    async def fail():
        raise RuntimeError(
            "http://navidrome.example.invalid/rest/getNowPlaying?u=private&t=derived"
        )

    monkeypatch.setattr(main, "SAVE_RETRY_ATTEMPTS", 1)
    with pytest.raises(RuntimeError):
        await main.retry_save(fail, kind="synthetic", attempts=1)

    assert "RuntimeError" in caplog.text
    assert "private" not in caplog.text
    assert "getNowPlaying" not in caplog.text
