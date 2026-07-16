import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport

from src.database import init_db, save_play_session
from src.main import app


@pytest.mark.asyncio
async def test_privacy_settings_default_permanent(isolated_db):
    await init_db(isolated_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/privacy/settings")
    assert response.status_code == 200
    assert response.json() == {"retention_days": None, "permanent": True}


@pytest.mark.asyncio
async def test_privacy_retention_update_and_preview(isolated_db):
    await init_db(isolated_db)
    old_at = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    await save_play_session(
        {
            "last_seen_at": old_at,
            "username": "user1",
            "client_name": "Web",
            "track_id": "t1",
            "title": "Song",
            "artist": "A",
            "album": "B",
            "is_transcoding": 0,
            "duration_sec": 40,
        },
        db_path=isolated_db,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put = await ac.put("/api/privacy/settings", json={"retention_days": 90})
        assert put.status_code == 200
        preview = await ac.get("/api/privacy/retention/preview")
        assert preview.json()["records_to_delete"] == 1
        denied = await ac.post("/api/privacy/retention/apply", json={"confirm": False})
        assert denied.status_code == 400
        applied = await ac.post("/api/privacy/retention/apply", json={"confirm": True})
        assert applied.json()["deleted"] == 1


@pytest.mark.asyncio
async def test_privacy_user_export_import_delete(isolated_db):
    await init_db(isolated_db)
    await save_play_session(
        {
            "last_seen_at": "2025-03-01T10:00:00+00:00",
            "username": "export_user",
            "client_name": "App",
            "track_id": "track-99",
            "title": "Title",
            "artist": "Artist",
            "album": "Album",
            "is_transcoding": 0,
            "duration_sec": 60,
        },
        db_path=isolated_db,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        users = await ac.get("/api/privacy/users")
        assert users.json()[0]["username"] == "export_user"

        export = await ac.get("/api/privacy/users/export_user/export")
        payload = export.json()
        assert payload["record_count"] == 1

        deleted = await ac.post(
            "/api/privacy/users/export_user/delete",
            json={"confirm": True},
        )
        assert deleted.json()["deleted"] == 1

        imported = await ac.post(
            "/api/privacy/users/export_user/import",
            json={"payload": payload, "merge": True},
        )
        assert imported.json()["imported"] == 1
