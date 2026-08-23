import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_summary, init_db, save_play_session
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
        body = preview.json()
        assert body["records_to_delete"] == 1
        assert body["database_bytes"] > 0
        assert "estimated_database_bytes_after" in body
        denied = await ac.post(
            "/api/privacy/retention/apply",
            json={"confirm": False, "expected_retention_days": 90},
        )
        assert denied.status_code == 400
        applied = await ac.post(
            "/api/privacy/retention/apply",
            json={"confirm": True, "expected_retention_days": 90},
        )
        assert applied.json()["deleted"] == 1


@pytest.mark.asyncio
async def test_retention_apply_rejects_changed_policy_without_deleting(isolated_db):
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
        assert (
            await ac.put("/api/privacy/settings", json={"retention_days": 90})
        ).status_code == 200
        assert (
            await ac.get("/api/privacy/retention/preview")
        ).json()["retention_days"] == 90
        assert (
            await ac.put("/api/privacy/settings", json={"retention_days": 30})
        ).status_code == 200
        response = await ac.post(
            "/api/privacy/retention/apply",
            json={"confirm": True, "expected_retention_days": 90},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Retention policy changed; preview again"}
    assert (await get_summary(db_path=isolated_db))["total_plays"] == 1


@pytest.mark.asyncio
async def test_retention_apply_accepts_expected_permanent_policy(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/retention/apply",
            json={"confirm": True, "expected_retention_days": None},
        )

    assert response.status_code == 200
    assert response.json() == {
        "deleted": 0,
        "history_deleted": 0,
        "attempts_deleted": 0,
        "retention_days": None,
    }


@pytest.mark.asyncio
async def test_retention_apply_requires_expected_policy(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/retention/apply",
            json={"confirm": True},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retention_policy_update_waits_for_matching_apply(isolated_db):
    await init_db(isolated_db)
    purge_started = asyncio.Event()
    release_purge = asyncio.Event()

    async def blocked_purge():
        purge_started.set()
        await release_purge.wait()
        return {
            "deleted": 0,
            "history_deleted": 0,
            "attempts_deleted": 0,
            "retention_days": 90,
        }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.put("/api/privacy/settings", json={"retention_days": 90})
        with patch("src.main.apply_retention_purge", side_effect=blocked_purge):
            apply_task = asyncio.create_task(
                ac.post(
                    "/api/privacy/retention/apply",
                    json={"confirm": True, "expected_retention_days": 90},
                )
            )
            await purge_started.wait()
            update_task = asyncio.create_task(
                ac.put("/api/privacy/settings", json={"retention_days": 30})
            )
            await asyncio.sleep(0)
            try:
                assert not update_task.done()
            finally:
                release_purge.set()
            apply_response, update_response = await asyncio.gather(
                apply_task,
                update_task,
            )

    assert apply_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["retention_days"] == 30


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


@pytest.mark.asyncio
async def test_export_filename_does_not_embed_username(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/privacy/users/synthetic%22name/export",
        )
    disposition = response.headers["content-disposition"]
    assert disposition == 'attachment; filename="navidrome-stat-export.json"'
    assert "synthetic" not in disposition


@pytest.mark.asyncio
async def test_import_rejects_oversized_content_length_before_parsing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/users/synthetic-user/import",
            headers={"Content-Length": str(6 * 1024 * 1024)},
            content=b"{}",
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "Import payload is too large"}
    assert "X-Content-Type-Options" in response.headers


@pytest.mark.asyncio
async def test_import_rejects_invalid_content_length_header():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/users/synthetic-user/import",
            headers={"Content-Length": "not-a-number"},
            content=b"{}",
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "Import payload is too large"}


@pytest.mark.asyncio
async def test_empty_replace_import_invalidates_dashboard_cache(monkeypatch):
    import src.main as main

    import_user = AsyncMock(return_value={"imported": 0, "attempts_imported": 0})
    invalidate = AsyncMock()
    monkeypatch.setattr(main, "import_user_data", import_user)
    monkeypatch.setattr(main.dashboard_snapshot_cache, "invalidate", invalidate)
    request_body = {
        "payload": {
            "format_version": 2,
            "username": "synthetic-user",
            "records": [],
            "attempts": [],
        },
        "merge": False,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/users/synthetic-user/import",
            json=request_body,
        )

    assert response.status_code == 200
    import_user.assert_awaited_once_with(
        "synthetic-user",
        request_body["payload"],
        merge=False,
    )
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_rejects_non_object_attempt_as_validation_error():
    payload = {
        "format_version": 2,
        "username": "synthetic-user",
        "records": [],
        "attempts": ["not-an-object"],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/users/synthetic-user/import",
            json={"payload": payload, "merge": True},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Import attempts must be objects"}
