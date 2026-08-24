import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CollectorRuntimeState:
    task: Optional[asyncio.Task] = None
    poll_success_count: int = 0
    poll_failure_count: int = 0
    last_poll_at: Optional[datetime] = None
    last_poll_ok: Optional[bool] = None
    last_upstream_error_code: Optional[int] = None
    song_history: Optional[bool] = None

    def task_alive(self) -> bool:
        return self.task is not None and not self.task.done()


@dataclass
class RuntimeState:
    polling_task: Optional[asyncio.Task] = None
    client_initialized: bool = False
    poll_success_count: int = 0
    poll_failure_count: int = 0
    last_poll_at: Optional[datetime] = None
    last_poll_ok: Optional[bool] = None
    last_upstream_error_code: Optional[int] = None
    save_success_count: int = 0
    save_failure_count: int = 0
    collectors: dict[str, CollectorRuntimeState] = field(default_factory=dict)

    def reset(self) -> None:
        """Clear every counter and collector entry; used between test runs."""
        self.polling_task = None
        self.client_initialized = False
        self.poll_success_count = 0
        self.poll_failure_count = 0
        self.last_poll_at = None
        self.last_poll_ok = None
        self.last_upstream_error_code = None
        self.save_success_count = 0
        self.save_failure_count = 0
        self.collectors.clear()

    def _collector(self, source_id: str) -> CollectorRuntimeState:
        return self.collectors.setdefault(source_id, CollectorRuntimeState())

    def set_collector_task(
        self,
        source_id: str,
        task: Optional[asyncio.Task],
    ) -> None:
        if task is None:
            self.collectors.pop(source_id, None)
        else:
            self._collector(source_id).task = task

    def record_poll_success(self, at: datetime, source_id: str = "legacy") -> None:
        self.poll_success_count += 1
        self.last_poll_at = at
        self.last_poll_ok = True
        self.last_upstream_error_code = None
        collector = self._collector(source_id)
        collector.poll_success_count += 1
        collector.last_poll_at = at
        collector.last_poll_ok = True
        collector.last_upstream_error_code = None

    def record_poll_upstream_error(
        self,
        at: datetime,
        error_code: Optional[int],
        source_id: str = "legacy",
    ) -> None:
        self.poll_failure_count += 1
        self.last_poll_at = at
        self.last_poll_ok = False
        self.last_upstream_error_code = error_code
        collector = self._collector(source_id)
        collector.poll_failure_count += 1
        collector.last_poll_at = at
        collector.last_poll_ok = False
        collector.last_upstream_error_code = error_code

    def record_poll_exception(self, at: datetime, source_id: str = "legacy") -> None:
        self.poll_failure_count += 1
        self.last_poll_at = at
        self.last_poll_ok = False
        collector = self._collector(source_id)
        collector.poll_failure_count += 1
        collector.last_poll_at = at
        collector.last_poll_ok = False

    def set_song_history(self, source_id: str, supported: bool) -> None:
        self._collector(source_id).song_history = bool(supported)

    def record_save_success(self) -> None:
        self.save_success_count += 1

    def record_save_failure(self) -> None:
        self.save_failure_count += 1

    def polling_task_alive(self) -> bool:
        if self.collectors:
            return all(collector.task_alive() for collector in self.collectors.values())
        return self.polling_task is not None and not self.polling_task.done()

    def collector_snapshot(self, source_id: str) -> dict:
        collector = self.collectors.get(source_id)
        if collector is None:
            return {
                "status": "not_running",
                "last_poll_ok": None,
                "last_poll_at": None,
                "song_history": None,
            }
        if not collector.task_alive():
            status = "stopped"
        elif collector.last_poll_ok is False:
            status = "degraded"
        elif collector.last_poll_ok is True:
            status = "running"
        else:
            status = "starting"
        return {
            "status": status,
            "last_poll_ok": collector.last_poll_ok,
            "last_poll_at": collector.last_poll_at,
            "song_history": collector.song_history,
        }


runtime_state = RuntimeState()
