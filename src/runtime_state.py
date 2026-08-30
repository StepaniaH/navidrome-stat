import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.schemas import SUBSONIC_AUTH_ERROR_CODES


@dataclass
class CollectorRuntimeState:
    task: Optional[asyncio.Task] = None
    poll_success_count: int = 0
    poll_failure_count: int = 0
    last_poll_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_poll_ok: Optional[bool] = None
    last_upstream_error_code: Optional[int] = None
    last_error_category: Optional[str] = None
    retry_at: Optional[datetime] = None
    song_history: Optional[bool] = None
    backfill_run_count: int = 0
    backfill_imported_total: int = 0
    backfill_error_count: int = 0
    last_backfill_at: Optional[datetime] = None
    last_save_at: Optional[datetime] = None
    last_save_ok: Optional[bool] = None

    def task_alive(self) -> bool:
        return self.task is not None and not self.task.done()


@dataclass
class QueryTiming:
    count: int = 0
    duration_seconds: float = 0.0
    max_duration_seconds: float = 0.0
    over_budget_count: int = 0


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
    last_save_at: Optional[datetime] = None
    last_save_ok: Optional[bool] = None
    dashboard_cache_hit_count: int = 0
    dashboard_cache_miss_count: int = 0
    dashboard_cache_shared_count: int = 0
    dashboard_build_count: int = 0
    dashboard_build_duration_seconds: float = 0.0
    sqlite_busy_count: int = 0
    sqlite_retry_count: int = 0
    import_count: int = 0
    import_duration_seconds: float = 0.0
    coverart_cache_hit_count: int = 0
    coverart_cache_miss_count: int = 0
    coverart_cache_bytes: int = 0
    coverart_cache_limit_bytes: int = 0
    stats_query_timings: dict[str, QueryTiming] = field(default_factory=dict)
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
        self.last_save_at = None
        self.last_save_ok = None
        self.dashboard_cache_hit_count = 0
        self.dashboard_cache_miss_count = 0
        self.dashboard_cache_shared_count = 0
        self.dashboard_build_count = 0
        self.dashboard_build_duration_seconds = 0.0
        self.sqlite_busy_count = 0
        self.sqlite_retry_count = 0
        self.import_count = 0
        self.import_duration_seconds = 0.0
        self.coverart_cache_hit_count = 0
        self.coverart_cache_miss_count = 0
        self.coverart_cache_bytes = 0
        self.coverart_cache_limit_bytes = 0
        self.stats_query_timings.clear()
        self.collectors.clear()

    def record_dashboard_cache_hit(self) -> None:
        self.dashboard_cache_hit_count += 1

    def record_dashboard_cache_miss(self) -> None:
        self.dashboard_cache_miss_count += 1

    def record_dashboard_cache_shared(self) -> None:
        self.dashboard_cache_shared_count += 1

    def record_dashboard_build(self, duration_seconds: float) -> None:
        self.dashboard_build_count += 1
        self.dashboard_build_duration_seconds += max(float(duration_seconds), 0.0)

    def record_sqlite_busy(self, *, retried: bool) -> None:
        self.sqlite_busy_count += 1
        if retried:
            self.sqlite_retry_count += 1

    def record_import(self, duration_seconds: float) -> None:
        self.import_count += 1
        self.import_duration_seconds += max(float(duration_seconds), 0.0)

    def record_stats_query(
        self,
        query: str,
        duration_seconds: float,
        *,
        budget_seconds: float,
    ) -> None:
        duration = max(float(duration_seconds), 0.0)
        timing = self.stats_query_timings.setdefault(query, QueryTiming())
        timing.count += 1
        timing.duration_seconds += duration
        timing.max_duration_seconds = max(timing.max_duration_seconds, duration)
        if duration > max(float(budget_seconds), 0.0):
            timing.over_budget_count += 1

    def set_coverart_cache_limit(self, limit_bytes: int) -> None:
        self.coverart_cache_limit_bytes = max(int(limit_bytes), 0)

    def record_coverart_cache_access(
        self,
        *,
        hit: bool,
        cache_bytes: int,
        limit_bytes: int,
    ) -> None:
        if hit:
            self.coverart_cache_hit_count += 1
        else:
            self.coverart_cache_miss_count += 1
        self.coverart_cache_bytes = max(int(cache_bytes), 0)
        self.set_coverart_cache_limit(limit_bytes)

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
        collector.last_success_at = at
        collector.last_poll_ok = True
        collector.last_upstream_error_code = None
        collector.last_error_category = None
        collector.retry_at = None

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
        collector.last_error_category = (
            "auth_failed"
            if error_code in SUBSONIC_AUTH_ERROR_CODES
            else "upstream_error"
        )

    def record_poll_exception(
        self,
        at: datetime,
        source_id: str = "legacy",
        category: str = "unknown",
    ) -> None:
        self.poll_failure_count += 1
        self.last_poll_at = at
        self.last_poll_ok = False
        self.last_upstream_error_code = None
        collector = self._collector(source_id)
        collector.poll_failure_count += 1
        collector.last_poll_at = at
        collector.last_poll_ok = False
        collector.last_upstream_error_code = None
        collector.last_error_category = category

    def set_collector_retry(
        self,
        source_id: str,
        retry_at: Optional[datetime],
    ) -> None:
        self._collector(source_id).retry_at = retry_at

    def set_song_history(self, source_id: str, supported: bool) -> None:
        self._collector(source_id).song_history = bool(supported)

    def record_backfill_result(self, source_id: str, imported: int) -> None:
        collector = self._collector(source_id)
        collector.backfill_run_count += 1
        collector.backfill_imported_total += max(imported, 0)
        collector.last_backfill_at = datetime.now(timezone.utc)

    def record_backfill_error(self, source_id: str) -> None:
        self._collector(source_id).backfill_error_count += 1

    def record_save_success(self, source_id: str = "legacy") -> None:
        self.save_success_count += 1
        now = datetime.now(timezone.utc)
        self.last_save_at = now
        self.last_save_ok = True
        collector = self.collectors.get(source_id)
        if collector is not None:
            collector.last_save_at = now
            collector.last_save_ok = True

    def record_save_failure(self, source_id: str = "legacy") -> None:
        self.save_failure_count += 1
        self.mark_save_failure(source_id)

    def mark_save_failure(self, source_id: str = "legacy") -> None:
        """Mark durable writes unhealthy without incrementing a known failure twice."""
        now = datetime.now(timezone.utc)
        self.last_save_at = now
        self.last_save_ok = False
        collector = self.collectors.get(source_id)
        if collector is not None:
            collector.last_save_at = now
            collector.last_save_ok = False

    def persistence_ok(self) -> Optional[bool]:
        """Return durable-write health without masking one source with another."""
        if self.collectors:
            states = [collector.last_save_ok for collector in self.collectors.values()]
            if any(state is False for state in states):
                return False
            if any(state is True for state in states):
                return True
            return None
        return self.last_save_ok

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
                "last_success_at": None,
                "last_error_category": None,
                "last_upstream_error_code": None,
                "retry_at": None,
                "song_history": None,
                "backfill": None,
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
            "last_success_at": collector.last_success_at,
            "last_error_category": collector.last_error_category,
            "last_upstream_error_code": collector.last_upstream_error_code,
            "retry_at": collector.retry_at,
            "song_history": collector.song_history,
            "backfill": self._backfill_summary(collector),
        }

    @staticmethod
    def _backfill_summary(
        collector: CollectorRuntimeState,
    ) -> Optional[dict]:
        if collector.backfill_run_count == 0 and collector.backfill_error_count == 0:
            return None
        return {
            "run_count": collector.backfill_run_count,
            "imported_total": collector.backfill_imported_total,
            "error_count": collector.backfill_error_count,
            "last_at": (
                collector.last_backfill_at.isoformat()
                if collector.last_backfill_at
                else None
            ),
        }


runtime_state = RuntimeState()
