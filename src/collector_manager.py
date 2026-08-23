"""Lifecycle coordination for independent Navidrome collectors."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class Collector:
    client: object
    tracker: object
    task: asyncio.Task
    config_key: tuple


class CollectorCleanupError(RuntimeError):
    """Redacted lifecycle cleanup failure."""


class CollectorManager:
    """Converge running collectors to a desired multi-server configuration."""

    def __init__(
        self,
        client_factory: Callable,
        poller: Callable,
        tracker_registry: list,
        *,
        tracker_factory: Callable,
        runtime_state,
    ):
        self._client_factory = client_factory
        self._poller = poller
        self._tracker_registry = tracker_registry
        self._tracker_factory = tracker_factory
        self._runtime_state = runtime_state
        self._lock = asyncio.Lock()
        self.collectors: dict[str, Collector] = {}

    def _build(self, server: dict):
        config = {
            "url": server.get("url"),
            "user": server.get("username", server.get("user")),
            "password": server.get("password"),
        }
        if not all(config.values()):
            raise ValueError("Incomplete server configuration")
        tracker = self._tracker_factory(server)
        client = self._client_factory(**config)
        return client, tracker

    @staticmethod
    def _config_key(server: dict) -> tuple:
        return (
            server.get("url"),
            server.get("username", server.get("user")),
            server.get("password"),
            server.get("display_name"),
            bool(server.get("enabled", True)),
        )

    @staticmethod
    def _raise_errors(errors: list[Exception], label: str) -> None:
        if errors:
            raise CollectorCleanupError(
                f"Failed to {label} ({len(errors)} errors)"
            )

    def _sync_runtime_state(self) -> None:
        state = self._runtime_state
        state.client_initialized = bool(self.collectors)
        state.polling_task = next(
            (collector.task for collector in self.collectors.values()),
            None,
        )
        active_ids = set(self.collectors)
        for source_id, collector in self.collectors.items():
            state.set_collector_task(source_id, collector.task)
        for source_id in tuple(state.collectors):
            if source_id not in active_ids:
                state.set_collector_task(source_id, None)

    async def _activate_unlocked(
        self,
        server_id: str,
        client,
        tracker,
        config_key: tuple,
    ) -> None:
        task = asyncio.create_task(self._poller(client, tracker))
        self.collectors[server_id] = Collector(client, tracker, task, config_key)
        self._tracker_registry.append(tracker)
        self._sync_runtime_state()

    async def _stop_unlocked(self, server_id: str) -> None:
        collector = self.collectors.pop(server_id, None)
        if collector is None:
            self._sync_runtime_state()
            return
        finalize_error = None
        try:
            await collector.tracker.finalize_all()
        except Exception as exc:
            finalize_error = exc
        collector.task.cancel()
        try:
            await collector.task
        except asyncio.CancelledError:
            pass
        try:
            await collector.client.close()
        finally:
            if collector.tracker in self._tracker_registry:
                self._tracker_registry.remove(collector.tracker)
            self._sync_runtime_state()
        if finalize_error is not None:
            raise CollectorCleanupError(
                "Failed to finalize collector sessions (1 error)"
            )

    async def _stop_for_replace(self, server_id: str) -> None:
        """Tear down a collector without aborting the replacement that follows."""
        try:
            await self._stop_unlocked(server_id)
        except CollectorCleanupError:
            logger.error("Collector session finalization failed during replace")

    async def start(self, server: dict) -> None:
        async with self._lock:
            if not server.get("enabled", True):
                return
            client, tracker = self._build(server)
            try:
                await self._stop_for_replace(server["id"])
                await self._activate_unlocked(
                    server["id"],
                    client,
                    tracker,
                    self._config_key(server),
                )
            except Exception:
                await client.close()
                raise

    async def replace(self, server: dict) -> None:
        async with self._lock:
            if not server.get("enabled", True):
                await self._stop_for_replace(server["id"])
                return
            client, tracker = self._build(server)
            try:
                await self._stop_for_replace(server["id"])
                await self._activate_unlocked(
                    server["id"],
                    client,
                    tracker,
                    self._config_key(server),
                )
            except Exception:
                await client.close()
                raise

    async def reconcile(self, servers: list[dict]) -> None:
        desired = {
            server["id"]: server
            for server in servers
            if server.get("enabled", True)
        }
        async with self._lock:
            replacements: dict[str, tuple] = {}
            try:
                for source_id, server in desired.items():
                    existing = self.collectors.get(source_id)
                    config_key = self._config_key(server)
                    if existing is not None and existing.config_key == config_key:
                        continue
                    client, tracker = self._build(server)
                    replacements[source_id] = (client, tracker, config_key)
            except Exception:
                for client, _tracker, _key in replacements.values():
                    await client.close()
                raise

            remove_ids = set(self.collectors) - set(desired)
            change_ids = set(replacements) & set(self.collectors)
            try:
                for source_id in sorted(remove_ids | change_ids):
                    await self._stop_for_replace(source_id)
                for source_id, (client, tracker, config_key) in replacements.items():
                    await self._activate_unlocked(
                        source_id,
                        client,
                        tracker,
                        config_key,
                    )
            except Exception:
                for source_id, (client, _tracker, _key) in replacements.items():
                    if source_id not in self.collectors:
                        await client.close()
                raise

    async def stop(self, server_id: str) -> None:
        async with self._lock:
            await self._stop_unlocked(server_id)

    async def stop_all(self) -> None:
        async with self._lock:
            errors = []
            for server_id in list(self.collectors):
                try:
                    await self._stop_unlocked(server_id)
                except Exception as exc:
                    errors.append(exc)
            self._raise_errors(errors, "stop collectors")
