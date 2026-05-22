from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import signal
from time import sleep
from typing import Any, Iterator

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


RuntimeEventHandler = Callable[[RuntimeQueueEvent], dict[str, Any] | None]


class RuntimeWorkerResult(str, Enum):
    IDLE = "idle"
    PROCESSED = "processed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"


@dataclass(frozen=True)
class RuntimeWorkerConfig:
    worker_id: str = field(default_factory=lambda: f"runtime-worker-{os.getpid()}")
    worker_kind: str = "runtime"
    event_types: list[str] = field(default_factory=list)
    lock_timeout_seconds: int = 300
    retry_delay_seconds: int = 60
    task_timeout_seconds: int | None = None
    statement_timeout_seconds: int | None = None
    poll_interval_seconds: float = 5.0
    max_iterations: int | None = None

    def __post_init__(self) -> None:
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive.")
        if self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive.")
        if self.task_timeout_seconds is not None and self.task_timeout_seconds <= 0:
            raise ValueError("task_timeout_seconds must be positive when provided.")
        if self.statement_timeout_seconds is not None and self.statement_timeout_seconds <= 0:
            raise ValueError("statement_timeout_seconds must be positive when provided.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")


class RuntimeWorker:
    def __init__(
        self,
        *,
        queue_repository: Any,
        config: RuntimeWorkerConfig,
        handlers: dict[str, RuntimeEventHandler] | None = None,
        redis_helper: Any | None = None,
    ) -> None:
        self._queue = queue_repository
        self._config = config
        self._handlers = dict(handlers or {})
        self._redis_helper = redis_helper

    def run_once(self) -> RuntimeWorkerResult:
        event_types = self._claim_event_types()
        if not event_types:
            self._record_heartbeat("idle", {"reason": "no_registered_event_types"})
            return RuntimeWorkerResult.IDLE

        self._record_heartbeat("polling", {"event_types": event_types})
        event = self._queue.claim_next(
            self._config.worker_id,
            event_types=event_types,
            lock_timeout_seconds=self._config.lock_timeout_seconds,
        )
        if event is None:
            self._record_heartbeat("idle", {"event_types": event_types})
            return RuntimeWorkerResult.IDLE

        handler = self._handlers.get(event.event_type)
        if handler is None:
            message = f"No runtime worker handler registered for event type {event.event_type!r}."
            self._queue.fail(event.event_id, self._config.worker_id, message, retry=False)
            self._record_heartbeat("failed", {"event_id": event.event_id, "error": message})
            self._log("runtime_worker.event_failed", event=event, retry=False, error=message)
            return RuntimeWorkerResult.FAILED_PERMANENT

        self._record_heartbeat(
            "processing",
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "scope_type": event.scope_type,
                "scope_key": event.scope_key,
                "attempts": event.attempts,
            },
        )
        self._set_statement_timeout(self._config.statement_timeout_seconds)
        try:
            with self._task_timeout(self._config.task_timeout_seconds):
                result_payload = handler(event)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._queue.fail(
                event.event_id,
                self._config.worker_id,
                error,
                retry=True,
                retry_delay_seconds=self._config.retry_delay_seconds,
            )
            self._record_heartbeat("failed", {"event_id": event.event_id, "retry": True, "error": error})
            self._log("runtime_worker.event_failed", event=event, retry=True, error=error)
            return RuntimeWorkerResult.FAILED_RETRYABLE
        finally:
            self._set_statement_timeout(None)

        self._queue.complete(event.event_id, self._config.worker_id, result_payload=result_payload)
        self._record_heartbeat("idle", {"event_id": event.event_id, "processed": True})
        self._log("runtime_worker.event_processed", event=event)
        return RuntimeWorkerResult.PROCESSED

    def run_forever(self) -> None:
        iterations = 0
        while self._config.max_iterations is None or iterations < self._config.max_iterations:
            result = self.run_once()
            iterations += 1
            if result is RuntimeWorkerResult.IDLE:
                sleep(self._config.poll_interval_seconds)

    def _claim_event_types(self) -> list[str]:
        configured = [event_type for event_type in self._config.event_types if str(event_type).strip()]
        if configured:
            return configured
        return sorted(self._handlers)

    def _record_heartbeat(self, status: str, payload: dict[str, Any]) -> None:
        record = getattr(self._queue, "record_worker_heartbeat", None)
        if callable(record):
            record(self._config.worker_id, self._config.worker_kind, status, payload=payload)

    def _set_statement_timeout(self, seconds: int | None) -> None:
        setter = getattr(self._queue, "set_statement_timeout_seconds", None)
        if callable(setter):
            setter(seconds)

    @contextmanager
    def _task_timeout(self, seconds: int | None) -> Iterator[None]:
        if seconds is None:
            yield
            return
        if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
            yield
            return

        def timeout_handler(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"runtime worker task exceeded {seconds}s timeout")

        previous_handler = signal.getsignal(signal.SIGALRM)
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, float(seconds))
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _log(self, event_name: str, *, event: RuntimeQueueEvent, retry: bool | None = None, error: str | None = None) -> None:
        payload: dict[str, Any] = {
            "event": event_name,
            "worker_id": self._config.worker_id,
            "queue_event_id": event.event_id,
            "event_type": event.event_type,
            "attempts": event.attempts,
        }
        if retry is not None:
            payload["retry"] = retry
        if error:
            payload["error"] = error
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
