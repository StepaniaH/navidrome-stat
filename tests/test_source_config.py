"""Tests for Navidrome source config persistence, resolution, and API endpoints.

All credentials here are synthetic. No real deployment values are used.
"""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import src.source_config as source_config
from src.database import init_db, list_servers
from src.main import app
from src.source_config import (
    get_saved_source_config,
    replace_saved_source_config,
    resolve_source_config,
    set_saved_source_config,
    validate_source_url,
)
from src.sqlite import connect_db


@pytest.mark.asyncio
async def test_get_config_returns_empty_when_unsaved(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch.dict("os.environ", {}, clear=False):
            for var in ("NAVIDROME_URL", "NAVIDROME_USER", "NAVIDROME_PASS"):
                import os
                os.environ.pop(var, None)
            response = await ac.get("/api/source/config")
    assert response.status_code == 200
    body = response.json()
    assert body["url"] is None
    assert body["username"] is None
    assert body["password_configured"] is False
    assert "password" not in body


@pytest.mark.asyncio
async def test_put_config_persists_and_redacts(isolated_db):
    await init_db(isolated_db)
    payload = {
        "url": "http://navidrome.example.invalid:4533",
        "username": "example_user",
        "password": "synthetic_password_123",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put = await ac.put("/api/source/config", json=payload)
        assert put.status_code == 200
        body = put.json()
        assert body["url"] == "http://navidrome.example.invalid:4533"
        assert body["username"] == "example_user"
        assert body["password_configured"] is True
        assert "password" not in body

        get = await ac.get("/api/source/config")
        assert get.json() == body

    saved = await get_saved_source_config(isolated_db)
    assert saved["url"] == "http://navidrome.example.invalid:4533"
    assert saved["user"] == "example_user"
    assert saved["password"] == "synthetic_password_123"


@pytest.mark.asyncio
async def test_source_config_write_rolls_back_all_fields_on_failure(isolated_db):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://old.example.invalid",
        user="old-user",
        password="old-password",
        db_path=isolated_db,
    )
    async with connect_db(isolated_db) as db:
        await db.execute(
            """
            CREATE TRIGGER fail_source_user_update
            BEFORE INSERT ON schema_meta
            WHEN NEW.key = 'source_user'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic source config failure');
            END
            """
        )
        await db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="synthetic source config failure"):
        await set_saved_source_config(
            url="http://new.example.invalid",
            user="new-user",
            password="new-password",
            db_path=isolated_db,
        )

    assert await get_saved_source_config(isolated_db) == {
        "url": "http://old.example.invalid",
        "user": "old-user",
        "password": "old-password",
    }


@pytest.mark.asyncio
async def test_source_config_reads_and_concurrent_writes_are_atomic(
    isolated_db, monkeypatch
):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://old.example.invalid",
        user="old-user",
        password="old-password",
        db_path=isolated_db,
    )
    first_field_written = asyncio.Event()
    release_first_writer = asyncio.Event()
    original_set_meta = source_config.set_meta_value

    async def pause_first_writer(db, key, value):
        await original_set_meta(db, key, value)
        if key == source_config.SOURCE_URL_KEY and value == "http://first.example.invalid":
            first_field_written.set()
            await release_first_writer.wait()

    monkeypatch.setattr(source_config, "set_meta_value", pause_first_writer)
    first = asyncio.create_task(
        set_saved_source_config(
            url="http://first.example.invalid",
            user="first-user",
            password="first-password",
            db_path=isolated_db,
        )
    )
    await first_field_written.wait()
    second = asyncio.create_task(
        set_saved_source_config(
            url="http://second.example.invalid",
            user="second-user",
            password="second-password",
            db_path=isolated_db,
        )
    )
    try:
        assert await get_saved_source_config(isolated_db) == {
            "url": "http://old.example.invalid",
            "user": "old-user",
            "password": "old-password",
        }
    finally:
        release_first_writer.set()
        await asyncio.gather(first, second)

    assert await get_saved_source_config(isolated_db) == {
        "url": "http://second.example.invalid",
        "user": "second-user",
        "password": "second-password",
    }


@pytest.mark.asyncio
async def test_replace_source_config_can_restore_an_unsaved_tuple(isolated_db):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://temporary.example.invalid",
        user="temporary-user",
        password="temporary-password",
        db_path=isolated_db,
    )

    await replace_saved_source_config(
        url=None,
        user=None,
        password=None,
        db_path=isolated_db,
    )

    assert await get_saved_source_config(isolated_db) == {
        "url": None,
        "user": None,
        "password": None,
    }


@pytest.mark.asyncio
async def test_put_config_hot_reloads_legacy_when_no_servers(isolated_db):
    await init_db(isolated_db)
    manager = AsyncMock()
    payload = {
        "url": "http://navidrome.example.invalid:4533",
        "username": "example_user",
        "password": "synthetic_password_123",
    }
    with patch("src.main.list_servers", AsyncMock(return_value=[])):
        with patch("src.main.collector_manager", manager):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.put("/api/source/config", json=payload)

    assert response.status_code == 200
    desired = manager.reconcile.await_args.args[0]
    assert len(desired) == 1
    applied = desired[0]
    assert applied["id"] == "legacy"
    assert applied["password"] == "synthetic_password_123"


@pytest.mark.asyncio
async def test_put_config_reconcile_failure_restores_saved_tuple(isolated_db):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://old.example.invalid",
        user="old-user",
        password="old-password",
        db_path=isolated_db,
    )
    reconcile = AsyncMock(side_effect=[RuntimeError("synthetic failure"), None])

    with patch("src.main._reconcile_collectors", reconcile):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.put(
                "/api/source/config",
                json={
                    "url": "http://new.example.invalid",
                    "username": "new-user",
                    "password": "new-password",
                },
            )

    assert response.status_code == 503
    assert response.json() == {"detail": "Saved configuration could not be applied"}
    assert await get_saved_source_config(isolated_db) == {
        "url": "http://old.example.invalid",
        "user": "old-user",
        "password": "old-password",
    }
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_fallback_and_server_mutations_share_one_lock(isolated_db):
    await init_db(isolated_db)
    first_reconcile_started = asyncio.Event()
    release_first_reconcile = asyncio.Event()
    reconcile_calls = 0

    async def reconcile():
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls == 1:
            first_reconcile_started.set()
            await release_first_reconcile.wait()

    with patch("src.main._reconcile_collectors", side_effect=reconcile):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            fallback = asyncio.create_task(
                ac.put(
                    "/api/source/config",
                    json={
                        "url": "http://fallback.example.invalid",
                        "username": "fallback-user",
                        "password": "fallback-password",
                    },
                )
            )
            await first_reconcile_started.wait()
            server = asyncio.create_task(
                ac.post(
                    "/api/servers",
                    json={
                        "display_name": "Saved Server",
                        "url": "http://saved.example.invalid",
                        "username": "saved-user",
                        "password": "saved-password",
                        "enabled": True,
                    },
                )
            )
            await asyncio.sleep(0)
            try:
                assert reconcile_calls == 1
                assert await list_servers(isolated_db) == []
            finally:
                release_first_reconcile.set()
            fallback_response, server_response = await asyncio.gather(fallback, server)

    assert fallback_response.status_code == 200
    assert server_response.status_code == 200
    assert reconcile_calls == 2
    assert len(await list_servers(isolated_db)) == 1


@pytest.mark.asyncio
async def test_put_config_does_not_reload_legacy_when_servers_exist(isolated_db):
    await init_db(isolated_db)
    manager = AsyncMock()
    payload = {
        "url": "http://navidrome.example.invalid:4533",
        "username": "example_user",
        "password": "synthetic_password_123",
    }
    with patch("src.main.list_servers", AsyncMock(return_value=[{"id": "server-1"}])):
        with patch("src.main.collector_manager", manager):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.put("/api/source/config", json=payload)

    assert response.status_code == 200
    manager.reconcile.assert_awaited_once_with([{"id": "server-1"}])


@pytest.mark.asyncio
async def test_put_config_blank_password_keeps_existing(isolated_db):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://navidrome.example.invalid:4533",
        user="example_user",
        password="original_password",
        db_path=isolated_db,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put = await ac.put(
            "/api/source/config",
            json={"url": "http://navidrome.example.invalid:9999", "username": "renamed_user"},
        )
        assert put.status_code == 200
        body = put.json()
        assert body["username"] == "renamed_user"
        assert body["password_configured"] is True

    saved = await get_saved_source_config(isolated_db)
    assert saved["password"] == "original_password"
    assert saved["user"] == "renamed_user"


@pytest.mark.asyncio
async def test_put_config_rejects_invalid_url_scheme(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put = await ac.put(
            "/api/source/config",
            json={"url": "ftp://navidrome.example.invalid", "username": "u"},
        )
    assert put.status_code == 422
    import os
    os.environ.pop("NAVIDROME_PASS", None)


@pytest.mark.asyncio
async def test_put_config_rejects_empty_username(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put = await ac.put(
            "/api/source/config",
            json={"url": "http://navidrome.example.invalid", "username": "   "},
        )
    assert put.status_code == 422


@pytest.mark.asyncio
async def test_env_vars_override_saved_on_get(isolated_db, monkeypatch):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://saved.example.invalid:4533",
        user="saved_user",
        password="saved_pass",
        db_path=isolated_db,
    )
    monkeypatch.setenv("NAVIDROME_URL", "http://env.example.invalid")
    monkeypatch.setenv("NAVIDROME_USER", "env_user")
    monkeypatch.setenv("NAVIDROME_PASS", "env_pass")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/source/config")
    body = response.json()
    assert body["url"] == "http://env.example.invalid"
    assert body["username"] == "env_user"
    assert body["password_configured"] is True
    assert "password" not in body


@pytest.mark.asyncio
async def test_resolve_overrides_take_priority_over_env_over_saved(isolated_db, monkeypatch):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://saved.example.invalid",
        user="saved_user",
        password="saved_pass",
        db_path=isolated_db,
    )
    monkeypatch.setenv("NAVIDROME_URL", "http://env.example.invalid")
    monkeypatch.setenv("NAVIDROME_USER", "env_user")
    monkeypatch.setenv("NAVIDROME_PASS", "env_pass")

    saved = await get_saved_source_config(isolated_db)
    resolved = resolve_source_config(
        overrides={"url": "http://override.example.invalid", "user": "override_u", "password": "override_p"},
        saved=saved,
    )
    assert resolved["url"] == "http://override.example.invalid"
    assert resolved["user"] == "override_u"
    assert resolved["password"] == "override_p"


@pytest.mark.asyncio
async def test_resolve_blank_overrides_fall_back_to_env_then_saved(isolated_db, monkeypatch):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://saved.example.invalid",
        user="saved_user",
        password="saved_pass",
        db_path=isolated_db,
    )
    monkeypatch.setenv("NAVIDROME_URL", "http://env.example.invalid")
    monkeypatch.delenv("NAVIDROME_USER", raising=False)
    monkeypatch.delenv("NAVIDROME_PASS", raising=False)

    saved = await get_saved_source_config(isolated_db)
    resolved = resolve_source_config(overrides={"url": "", "user": None, "password": ""}, saved=saved)
    assert resolved["url"] == "http://env.example.invalid"
    assert resolved["user"] == "saved_user"
    assert resolved["password"] == "saved_pass"


def test_validate_source_url_strips_trailing_slash():
    assert validate_source_url("http://navidrome.example.invalid:4533/") == "http://navidrome.example.invalid:4533"


def test_validate_source_url_rejects_missing_scheme():
    with pytest.raises(ValueError):
        validate_source_url("navidrome.example.invalid")


def test_validate_source_url_rejects_empty():
    with pytest.raises(ValueError):
        validate_source_url("")
    with pytest.raises(ValueError):
        validate_source_url("   ")


@pytest.mark.asyncio
async def test_source_test_success_with_mocked_client(isolated_db, monkeypatch):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://navidrome.example.invalid:4533",
        user="example_user",
        password="synthetic_password_123",
        db_path=isolated_db,
    )
    for var in ("NAVIDROME_URL", "NAVIDROME_USER", "NAVIDROME_PASS"):
        import os
        os.environ.pop(var, None)

    mock_client = AsyncMock()
    mock_client.get_now_playing.return_value = {"subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}}

    with patch("src.main.NavidromeClient", return_value=mock_client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/source/test", json={})

    body = response.json()
    assert body["ok"] is True
    assert "成功" in body["message"]
    mock_client.get_now_playing.assert_awaited_once()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_test_failure_returns_generic_message(isolated_db):
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://navidrome.example.invalid:4533",
        user="example_user",
        password="synthetic_password_123",
        db_path=isolated_db,
    )
    for var in ("NAVIDROME_URL", "NAVIDROME_USER", "NAVIDROME_PASS"):
        import os
        os.environ.pop(var, None)

    mock_client = AsyncMock()
    mock_client.get_now_playing.side_effect = ConnectionError("upstream unreachable")
    mock_client.close = AsyncMock()

    with patch("src.main.NavidromeClient", return_value=mock_client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/source/test", json={})

    body = response.json()
    assert body["ok"] is False
    assert "upstream" not in body["message"].lower()
    assert "ConnectionError" not in body["message"]
    assert "password" not in body["message"]
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_test_incomplete_config_returns_generic(isolated_db):
    await init_db(isolated_db)
    for var in ("NAVIDROME_URL", "NAVIDROME_USER", "NAVIDROME_PASS"):
        import os
        os.environ.pop(var, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/source/test", json={})
    body = response.json()
    assert body["ok"] is False
    assert "不完整" in body["message"]


@pytest.mark.asyncio
async def test_source_test_uses_supplied_overrides(isolated_db, monkeypatch):
    await init_db(isolated_db)
    monkeypatch.delenv("NAVIDROME_URL", raising=False)

    mock_client = AsyncMock()
    mock_client.get_now_playing.return_value = {"subsonic-response": {"status": "ok", "nowPlaying": {"entry": []}}}

    with patch("src.main.NavidromeClient", return_value=mock_client) as ctor:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/source/test",
                json={
                    "url": "http://supplied.example.invalid:4533",
                    "username": "supplied_user",
                    "password": "supplied_pass",
                },
            )
    assert response.json()["ok"] is True
    ctor.assert_called_once_with(
        url="http://supplied.example.invalid:4533",
        user="supplied_user",
        password="supplied_pass",
    )
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_endpoints_protected_when_auth_enabled(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value="synthetic-secret-token"):
            get = await ac.get("/api/source/config")
            put = await ac.put("/api/source/config", json={"url": "http://x.example.invalid", "username": "u"})
            test = await ac.post("/api/source/test", json={})
    assert get.status_code == 401
    assert put.status_code == 401
    assert test.status_code == 401


@pytest.mark.asyncio
async def test_source_endpoints_accessible_when_auth_disabled(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("src.auth.get_stats_api_token", return_value=None):
            get = await ac.get("/api/source/config")
            test = await ac.post("/api/source/test", json={})
    assert get.status_code == 200
    assert test.status_code == 200


@pytest.mark.asyncio
async def test_source_config_saved_when_partial_env_present(isolated_db, monkeypatch):
    """Env vars take precedence per-field; saved values fill missing fields."""
    await init_db(isolated_db)
    await set_saved_source_config(
        url="http://saved.example.invalid",
        user="saved_user",
        password="saved_pass",
        db_path=isolated_db,
    )
    monkeypatch.setenv("NAVIDROME_URL", "http://env.example.invalid")
    monkeypatch.delenv("NAVIDROME_USER", raising=False)
    monkeypatch.delenv("NAVIDROME_PASS", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/source/config")
    body = response.json()
    assert body["url"] == "http://env.example.invalid"
    assert body["username"] == "saved_user"
    assert body["password_configured"] is True
