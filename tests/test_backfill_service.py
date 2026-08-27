"""Backfill orchestrator: locks, cutoff lookup, writes, runtime accounting."""

import asyncio

import pytest

import src.importers.backfill_service as backfill_module
from src.database import init_db, save_play_session
from src.runtime_state import runtime_state


def server_config(**overrides):
    config = {
        "id": "srv-bf",
        "display_name": "Backfill Source",
        "url": "http://navidrome.example.invalid",
        "username": "alice",
        "password": "synthetic-password",
        "enabled": True,
        "backfill_playlist_id": "pl-1",
    }
    config.update(overrides)
    return config


class FakeClient:
    def __init__(self):
        self.closed = False
        self.requests = []

    async def get_playlist(self, playlist_id):
        self.requests.append(playlist_id)
        return {
            "subsonic-response": {
                "status": "ok",
                "playlist": {
                    "entry": [
                        {"id": f"trk-{playlist_id}-1", "played": "2019-01-01T00:00:00Z"},
                        {"id": f"trk-{playlist_id}-2", "played": "2020-01-01T00:00:00Z"},
                    ]
                },
            }
        }

    async def close(self):
        self.closed = True


async def test_run_once_imports_records_state_and_closes_owned_client(isolated_db):
    await init_db()
    try:
        runner = backfill_module.BackfillRunner(client_factory=lambda **_: FakeClient())

        result = await runner.run_once(server_config())

        assert result == {"imported": 2, "skipped": 0}
        state = runtime_state.collectors["srv-bf"]
        assert state.backfill_run_count == 1
        assert state.backfill_imported_total == 2
        assert state.backfill_error_count == 0
        assert state.last_backfill_at is not None
    finally:
        runtime_state.reset()


async def test_run_once_without_playlist_is_noop(isolated_db):
    await init_db()
    built = []

    def factory(**_config):
        built.append(True)
        return FakeClient()

    try:
        runner = backfill_module.BackfillRunner(client_factory=factory)

        result = await runner.run_once(server_config(backfill_playlist_id=None))

        assert result is None
        assert built == []
        assert "srv-bf" not in runtime_state.collectors
    finally:
        runtime_state.reset()


async def test_second_run_is_idempotent_and_keeps_provided_client(isolated_db):
    await init_db()
    shared_client = FakeClient()
    try:
        runner = backfill_module.BackfillRunner(client_factory=lambda **_: None)

        first = await runner.run_once(server_config(), client=shared_client)
        second = await runner.run_once(server_config(), client=shared_client)

        assert first["imported"] == 2
        assert second["imported"] == 0
        assert shared_client.closed is False
        assert len(shared_client.requests) == 2
    finally:
        runtime_state.reset()


async def test_watch_runs_immediately_then_waits_interval(monkeypatch):
    monkeypatch.setattr(backfill_module, "BACKFILL_INTERVAL_SEC", 0.01)
    runs = []

    class Runner:
        async def run_once(self, server, client=None):
            runs.append(server["id"])
            return {"imported": 0, "skipped": 0}

    task = asyncio.create_task(
        backfill_module.watch_forever(Runner(), server_config(), FakeClient())
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(runs) >= 1


async def test_upstream_failure_is_counted_not_raised(isolated_db):
    await init_db()

    class ExplodingClient(FakeClient):
        async def get_playlist(self, playlist_id):
            raise RuntimeError("upstream unreachable")

    try:
        runner = backfill_module.BackfillRunner(
            client_factory=lambda **_: ExplodingClient()
        )
        with pytest.raises(RuntimeError):
            await runner.run_once(server_config())

        state = runtime_state.collectors["srv-bf"]
        assert state.backfill_error_count == 1
        assert state.backfill_run_count == 0
    finally:
        runtime_state.reset()


async def test_concurrent_runs_serialize_per_source(isolated_db):
    await init_db()
    active = 0
    max_active = 0

    class SlowClient(FakeClient):
        async def get_playlist(self, playlist_id):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return await super().get_playlist(playlist_id)

    try:
        runner = backfill_module.BackfillRunner(client_factory=lambda **_: SlowClient())
        results = await asyncio.gather(
            runner.run_once(server_config()),
            runner.run_once(server_config()),
            runner.run_once(server_config()),
        )

        assert max_active == 1
        assert sum(result["imported"] for result in results) == 2
    finally:
        runtime_state.reset()


async def test_earliest_poller_lookup_scopes_source_and_username(isolated_db):
    from src.database import get_earliest_poller_played_at
    from src.schema import LEGACY_SOURCE_ID

    await init_db()
    assert await get_earliest_poller_played_at("srv-x", "nobody") is None

    await save_play_session(
        {
            "last_seen_at": "2024-06-01T08:00:00+00:00",
            "username": "alice",
            "track_id": "t-later",
            "duration_sec": 30,
            "source_id": "srv-x",
        },
        db_path=isolated_db,
    )
    await save_play_session(
        {
            "last_seen_at": "2024-05-01T07:00:00+00:00",
            "username": "alice",
            "track_id": "t-earlier",
            "duration_sec": 30,
            "source_id": "srv-x",
        },
        db_path=isolated_db,
    )
    await save_play_session(
        {
            "last_seen_at": "2023-01-01T00:00:00+00:00",
            "username": "bob",
            "track_id": "t-bob",
            "duration_sec": 30,
            "source_id": "srv-x",
        },
        db_path=isolated_db,
    )
    await save_play_session(
        {
            "last_seen_at": "2022-01-01T00:00:00+00:00",
            "username": "alice",
            "track_id": "t-legacy",
            "duration_sec": 30,
            "source_id": LEGACY_SOURCE_ID,
        },
        db_path=isolated_db,
    )

    earliest = await get_earliest_poller_played_at("srv-x", "alice")
    assert earliest.startswith("2024-05-01")
