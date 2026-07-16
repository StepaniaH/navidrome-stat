from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import asyncio


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

    def record_poll_success(self, at: datetime) -> None:
        self.poll_success_count += 1
        self.last_poll_at = at
        self.last_poll_ok = True
        self.last_upstream_error_code = None

    def record_poll_upstream_error(self, at: datetime, error_code: Optional[int]) -> None:
        self.poll_failure_count += 1
        self.last_poll_at = at
        self.last_poll_ok = False
        self.last_upstream_error_code = error_code

    def record_poll_exception(self, at: datetime) -> None:
        self.poll_failure_count += 1
        self.last_poll_at = at
        self.last_poll_ok = False

    def record_save_success(self) -> None:
        self.save_success_count += 1

    def record_save_failure(self) -> None:
        self.save_failure_count += 1

    def polling_task_alive(self) -> bool:
        return self.polling_task is not None and not self.polling_task.done()


runtime_state = RuntimeState()
