import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_server, init_db, list_servers, save_server
from src.main import app


def payload(*, enabled=True):
    return {
        "display_name": "Synthetic Server",
        "url": "http://navidrome.example.invalid:4533",
        "username": "synthetic-user",
        "password": "synthetic-password",
        "enabled": enabled,
    }


@pytest.mark.asyncio
async def test_create_server_applies_runtime_config_immediately():
    reconcile = AsyncMock()
    with patch("src.stats_service.save_server", AsyncMock()) as save:
        with patch("src.collectors.reconcile_collectors", reconcile):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 200
    assert save.await_count == 1
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_server_applies_disabled_state_immediately():
    existing = {"id": "server-1", **payload()}
    reconcile = AsyncMock()
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        with patch("src.stats_service.save_server", AsyncMock()):
            with patch("src.collectors.reconcile_collectors", reconcile):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.put("/api/servers/server-1", json=payload(enabled=False))

    assert response.status_code == 200
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_server_rejects_whitespace_identity_fields():
    existing = {"id": "server-1", **payload()}
    invalid = payload()
    invalid["display_name"] = "   "
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.put("/api/servers/server-1", json=invalid)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_server_stops_runtime_collector():
    reconcile = AsyncMock()
    existing = {"id": "server-1", **payload()}
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        with patch("src.stats_service.delete_server", AsyncMock(return_value=True)):
            with patch("src.collectors.reconcile_collectors", reconcile):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.delete("/api/servers/server-1")

    assert response.status_code == 200
    reconcile.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_runtime_apply_failure_rolls_back_created_server(isolated_db):
    await init_db(isolated_db)
    reconcile = AsyncMock(
        side_effect=[RuntimeError("synthetic-password upstream detail"), None]
    )
    with patch("src.collectors.reconcile_collectors", reconcile):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/servers", json=payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "Saved configuration could not be applied"}
    assert "synthetic-password" not in response.text
    assert await list_servers(isolated_db) == []
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_runtime_apply_failure_restores_updated_server(isolated_db):
    await init_db(isolated_db)
    original = {"id": "server-1", **payload()}
    await save_server(original, isolated_db)
    changed = payload(enabled=False)
    changed["display_name"] = "Changed Server"
    reconcile = AsyncMock(side_effect=[RuntimeError("synthetic failure"), None])

    with patch("src.collectors.reconcile_collectors", reconcile):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.put("/api/servers/server-1", json=changed)

    assert response.status_code == 503
    restored = await get_server("server-1", isolated_db)
    assert restored["display_name"] == original["display_name"]
    assert restored["url"] == original["url"]
    assert restored["username"] == original["username"]
    assert restored["password"] == original["password"]
    assert restored["enabled"] == 1
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_runtime_apply_failure_restores_deleted_server(isolated_db):
    await init_db(isolated_db)
    original = {"id": "server-1", **payload()}
    await save_server(original, isolated_db)
    reconcile = AsyncMock(side_effect=[RuntimeError("synthetic failure"), None])

    with patch("src.collectors.reconcile_collectors", reconcile):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete("/api/servers/server-1")

    assert response.status_code == 503
    restored = await get_server("server-1", isolated_db)
    assert restored is not None
    assert restored["display_name"] == original["display_name"]
    assert restored["password"] == original["password"]
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_server_mutations_are_serialized(isolated_db):
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

    first_payload = payload()
    second_payload = {
        **payload(),
        "display_name": "Second Server",
        "url": "http://second.example.invalid:4533",
        "username": "second-user",
    }
    with patch("src.collectors.reconcile_collectors", side_effect=reconcile):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            first = asyncio.create_task(ac.post("/api/servers", json=first_payload))
            await first_reconcile_started.wait()
            second = asyncio.create_task(ac.post("/api/servers", json=second_payload))
            await asyncio.sleep(0)
            try:
                assert reconcile_calls == 1
                assert len(await list_servers(isolated_db)) == 1
            finally:
                release_first_reconcile.set()
            first_response, second_response = await asyncio.gather(first, second)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert reconcile_calls == 2
    assert len(await list_servers(isolated_db)) == 2


@pytest.mark.asyncio
async def test_cancelled_server_mutation_rolls_back_and_releases_lock(isolated_db):
    await init_db(isolated_db)
    reconcile_started = asyncio.Event()
    reconcile_calls = 0

    async def reconcile():
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls == 1:
            reconcile_started.set()
            await asyncio.Event().wait()

    with patch("src.collectors.reconcile_collectors", side_effect=reconcile):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            cancelled_request = asyncio.create_task(
                ac.post("/api/servers", json=payload())
            )
            await reconcile_started.wait()
            cancelled_request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled_request

            assert await list_servers(isolated_db) == []
            replacement = await ac.post(
                "/api/servers",
                json={**payload(), "display_name": "Replacement"},
            )

    assert replacement.status_code == 200
    assert reconcile_calls == 3
    assert len(await list_servers(isolated_db)) == 1


@pytest.mark.asyncio
async def test_server_connection_test_uses_submitted_fields_and_checks_status():
    existing = {"id": "server-1", **payload()}
    client = AsyncMock()
    client.get_now_playing.return_value = {
        "subsonic-response": {"status": "failed", "error": {"code": 40}}
    }
    client_type = patch("src.routes.servers.NavidromeClient").start()
    client_type.return_value = client
    client_type.response_is_ok.return_value = False
    try:
        with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                response = await ac.post(
                    "/api/servers/server-1/test",
                    json={
                        "display_name": "Edited",
                        "url": "https://edited.example.invalid",
                        "username": "edited-user",
                        "password": "edited-password",
                        "enabled": True,
                    },
                )
    finally:
        patch.stopall()

    assert response.status_code == 200
    assert response.json()["ok"] is False
    client_type.assert_called_once_with(
        url="https://edited.example.invalid",
        user="edited-user",
        password="edited-password",
    )


@pytest.mark.asyncio
async def test_server_view_reports_song_history_capability(isolated_db):
    await init_db(isolated_db)
    existing = {"id": "server-1", **payload()}
    await save_server(existing, isolated_db)

    from src.runtime_state import runtime_state

    runtime_state.reset()
    runtime_state.client_initialized = True
    state = runtime_state._collector("server-1")
    state.song_history = True

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/servers")
        body = response.json()
        assert response.status_code == 200
        entry = next(item for item in body if item["id"] == "server-1")
        assert entry["song_history_ready"] is True
    finally:
        runtime_state.reset()


def _payload_with_playlist(playlist="pl-9", **overrides):
    body = payload(**overrides)
    body["backfill_playlist_id"] = playlist
    return body


@pytest.mark.asyncio
async def test_create_and_update_persist_backfill_playlist_id(isolated_db):
    await init_db(isolated_db)
    reconcile = AsyncMock()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch("src.collectors.reconcile_collectors", reconcile):
            created = await ac.post(
                "/api/servers", json=_payload_with_playlist()
            )
            assert created.status_code == 200
            body = created.json()
            assert body["backfill_playlist_id"] == "pl-9"
            created_id = body["id"]

            updated = await ac.put(
                f"/api/servers/{created_id}",
                json=_payload_with_playlist("pl-10"),
            )

    assert updated.status_code == 200
    assert updated.json()["backfill_playlist_id"] == "pl-10"
    stored = await get_server(created_id, isolated_db)
    assert stored["backfill_playlist_id"] == "pl-10"


@pytest.mark.asyncio
async def test_backfill_run_returns_counts(isolated_db):
    existing = {"id": "server-1", **_payload_with_playlist(), "password": "pw"}
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        with patch(
            "src.routes.servers.backfill_runner"
        ) as runner:
            runner.run_once = AsyncMock(return_value={"imported": 2, "skipped": 1})
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post("/api/servers/server-1/backfill/run")

    assert response.status_code == 200
    assert response.json() == {"imported": 2, "skipped": 1}
    called_server = runner.run_once.await_args.args[0]
    assert called_server["backfill_playlist_id"] == "pl-9"


@pytest.mark.asyncio
async def test_backfill_run_conflicts_without_playlist():
    existing = {"id": "server-1", **payload(), "password": "pw"}
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post("/api/servers/server-1/backfill/run")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_backfill_run_maps_failure_to_502_without_details():
    existing = {"id": "server-1", **_payload_with_playlist(), "password": "pw"}
    with patch("src.routes.servers.get_server", AsyncMock(return_value=existing)):
        with patch("src.routes.servers.backfill_runner") as runner:
            runner.run_once = AsyncMock(
                side_effect=RuntimeError("secret upstream detail")
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post("/api/servers/server-1/backfill/run")

    assert response.status_code == 502
    assert "secret upstream detail" not in response.text


@pytest.mark.asyncio
async def test_readiness_metrics_model_exposes_backfill_counters(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/health/ready")

    assert response.status_code == 200
    assert {"backfill_run_total", "backfill_imported_total",
            "backfill_error_total"} <= set(response.json()["metrics"])


@pytest.mark.asyncio
async def test_server_view_includes_backfill_runtime_summary(isolated_db):
    from src.database import init_db
    from src.runtime_state import runtime_state

    await init_db(isolated_db)
    existing = {"id": "bf-view", **_payload_with_playlist(), "password": "pw"}
    await save_server(existing, isolated_db)
    try:
        runtime_state.record_backfill_result("bf-view", 7)
        runtime_state.record_backfill_error("bf-view")
        with patch(
            "src.routes.servers.get_server", AsyncMock(return_value=existing)
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get("/api/servers")

        entry = next(s for s in response.json() if s["id"] == "bf-view")
        assert entry["backfill_summary"]["imported_total"] == 7
        assert entry["backfill_summary"]["error_count"] == 1
        assert entry["backfill_summary"]["last_at"] is not None
    finally:
        runtime_state.reset()
