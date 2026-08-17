from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import signal
from time import monotonic, sleep
from typing import Any, Iterator

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


RuntimeEventHandler = Callable[[RuntimeQueueEvent], dict[str, Any] | None]
DEFAULT_RUNTIME_WORKER_POLL_INTERVAL_SECONDS = 0.05
DEFAULT_RUNTIME_WORKER_HEARTBEAT_MIN_INTERVAL_SECONDS = 1.0
FORCED_HEARTBEAT_STATUSES = frozenset({"processing", "deferred", "failed", "stopping", "stopped"})


class RuntimeWorkerResult(str, Enum):
    IDLE = "idle"
    PROCESSED = "processed"
    DEFERRED = "deferred"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"


class RuntimeWorkerShutdownRequested(BaseException):
    def __init__(self, signum: int | None = None) -> None:
        self.signum = signum
        reason = f"shutdown_signal_{signum}" if signum is not None else "shutdown_requested"
        super().__init__(reason)


@dataclass(frozen=True)
class RuntimeWorkerConfig:
    worker_id: str = field(default_factory=lambda: f"runtime-worker-{os.getpid()}")
    worker_kind: str = "runtime"
    worker_instance: str | None = None
    event_types: list[str] = field(default_factory=list)
    lock_timeout_seconds: int = 300
    retry_delay_seconds: int = 60
    task_timeout_seconds: int | None = None
    statement_timeout_seconds: int | None = None
    poll_interval_seconds: float = DEFAULT_RUNTIME_WORKER_POLL_INTERVAL_SECONDS
    max_iterations: int | None = None
    max_attempts: int = 5
    max_events_per_iteration: int = 1
    heartbeat_min_interval_seconds: float = DEFAULT_RUNTIME_WORKER_HEARTBEAT_MIN_INTERVAL_SECONDS
    claim_scope_keys: list[str] = field(default_factory=list)
    exclude_claim_scope_keys: list[str] = field(default_factory=list)

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
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.max_events_per_iteration <= 0:
            raise ValueError("max_events_per_iteration must be positive.")
        if self.heartbeat_min_interval_seconds <= 0:
            raise ValueError("heartbeat_min_interval_seconds must be positive.")


class RuntimeWorker:
    def __init__(
        self,
        *,
        queue_repository: Any,
        config: RuntimeWorkerConfig,
        handlers: dict[str, RuntimeEventHandler] | None = None,
    ) -> None:
        self._queue = queue_repository
        self._config = config
        self._handlers = dict(handlers or {})
        self._last_heartbeat_at: float | None = None

    def run_once(self) -> RuntimeWorkerResult:
        event_types = self._claim_event_types()
        if not event_types:
            self._record_heartbeat("idle", {"reason": "no_registered_event_types"})
            return RuntimeWorkerResult.IDLE

        event = self._queue.claim_next(
            self._config.worker_id,
            event_types=event_types,
            lock_timeout_seconds=self._config.lock_timeout_seconds,
            **self._claim_scope_filters(),
        )
        if event is None:
            self._record_heartbeat("idle", {"event_types": event_types})
            return RuntimeWorkerResult.IDLE

        return self.process_claimed_event(event)

    def process_claimed_event(self, event: RuntimeQueueEvent) -> RuntimeWorkerResult:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            message = f"No runtime worker handler registered for event type {event.event_type!r}."
            failed = self._queue.fail(event.event_id, self._config.worker_id, message, retry=False)
            if not failed:
                raise RuntimeError(f"PostgreSQL fail update did not match event {event.event_id}.")
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
            started_at = monotonic()
            with self._task_timeout(self._config.task_timeout_seconds):
                result_payload = handler(event)
        except RuntimeWorkerShutdownRequested as exc:
            reason = str(exc) or "shutdown_requested"
            self._release_event(event, reason)
            self._record_heartbeat("stopping", {"event_id": event.event_id, "reason": reason})
            self._log("runtime_worker.event_released", event=event, retry=True, error=reason)
            raise
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._fail_event(event, error)
            self._record_heartbeat("failed", {"event_id": event.event_id, "retry": True, "error": error})
            self._log("runtime_worker.event_failed", event=event, retry=True, error=error)
            return RuntimeWorkerResult.FAILED_RETRYABLE
        finally:
            self._set_statement_timeout(None)

        ack_payload = dict(result_payload) if isinstance(result_payload, dict) else {}
        ack_payload.setdefault("duration_ms", round((monotonic() - started_at) * 1000, 3))
        self._ack_event(event, ack_payload)
        self._record_heartbeat("idle", {"event_id": event.event_id, "processed": True}, force=True)
        self._log("runtime_worker.event_processed", event=event)
        return RuntimeWorkerResult.PROCESSED

    def run_forever(self) -> None:
        iterations = 0
        with self._shutdown_signal_handlers():
            try:
                while self._config.max_iterations is None or iterations < self._config.max_iterations:
                    result = RuntimeWorkerResult.IDLE
                    for _ in range(self._config.max_events_per_iteration):
                        result = self.run_once()
                        if result is RuntimeWorkerResult.IDLE:
                            break
                    iterations += 1
                    if result is RuntimeWorkerResult.IDLE:
                        sleep(self._config.poll_interval_seconds)
            except RuntimeWorkerShutdownRequested as exc:
                self._record_heartbeat("stopped", {"reason": str(exc) or "shutdown_requested"})

    def _claim_event_types(self) -> list[str]:
        configured = [event_type for event_type in self._config.event_types if str(event_type).strip()]
        if configured:
            return configured
        return sorted(self._handlers)

    def claim_scope_filters(self) -> dict[str, list[str]]:
        return self._claim_scope_filters()

    def _claim_scope_filters(self) -> dict[str, list[str]]:
        filters: dict[str, list[str]] = {}
        claim_scope_keys = [scope_key for scope_key in self._config.claim_scope_keys if str(scope_key).strip()]
        exclude_scope_keys = [
            scope_key for scope_key in self._config.exclude_claim_scope_keys if str(scope_key).strip()
        ]
        if claim_scope_keys:
            filters["scope_keys"] = claim_scope_keys
        if exclude_scope_keys:
            filters["exclude_scope_keys"] = exclude_scope_keys
        return filters

    def record_heartbeat(self, status: str, payload: dict[str, Any]) -> None:
        self._record_heartbeat(status, payload, force=True)

    def _record_heartbeat(self, status: str, payload: dict[str, Any], *, force: bool = False) -> None:
        record = getattr(self._queue, "record_worker_heartbeat", None)
        if callable(record):
            now = monotonic()
            if not force and status not in FORCED_HEARTBEAT_STATUSES:
                last_heartbeat_at = self._last_heartbeat_at
                if (
                    last_heartbeat_at is not None
                    and now - last_heartbeat_at < self._config.heartbeat_min_interval_seconds
                ):
                    return
            heartbeat_payload = dict(payload)
            if self._config.worker_instance:
                heartbeat_payload.setdefault("worker_instance", self._config.worker_instance)
            if self._config.event_types:
                heartbeat_payload.setdefault("configured_event_types", list(self._config.event_types))
            if self._config.claim_scope_keys:
                heartbeat_payload.setdefault("claim_scope_keys", list(self._config.claim_scope_keys))
            if self._config.exclude_claim_scope_keys:
                heartbeat_payload.setdefault("exclude_claim_scope_keys", list(self._config.exclude_claim_scope_keys))
            record(self._config.worker_id, self._config.worker_kind, status, payload=heartbeat_payload)
            self._last_heartbeat_at = now

    def _set_statement_timeout(self, seconds: int | None) -> None:
        setter = getattr(self._queue, "set_statement_timeout_seconds", None)
        if callable(setter):
            setter(seconds)

    def _ack_event(self, event: RuntimeQueueEvent, result_payload: dict[str, Any]) -> None:
        ack = getattr(self._queue, "ack_event", None)
        if callable(ack):
            if not ack(event.event_id, self._config.worker_id, result_payload=result_payload):
                raise RuntimeError(f"PostgreSQL ack update did not match event {event.event_id}.")
            return
        if not self._queue.complete(event.event_id, self._config.worker_id, result_payload=result_payload):
            raise RuntimeError(f"PostgreSQL complete update did not match event {event.event_id}.")

    def _fail_event(self, event: RuntimeQueueEvent, error: str) -> None:
        retry_delay = self._retry_delay_for_attempt(event.attempts)
        fail_event = getattr(self._queue, "fail_event", None)
        if callable(fail_event):
            if not fail_event(
                event.event_id,
                self._config.worker_id,
                error,
                retryable=True,
                retry_delay_seconds=retry_delay,
                max_attempts=self._config.max_attempts,
            ):
                raise RuntimeError(f"PostgreSQL fail update did not match event {event.event_id}.")
            return
        if not self._queue.fail(
            event.event_id,
            self._config.worker_id,
            error,
            retry=True,
            retry_delay_seconds=retry_delay,
        ):
            raise RuntimeError(f"PostgreSQL retry update did not match event {event.event_id}.")

    def _release_event(self, event: RuntimeQueueEvent, reason: str) -> None:
        release_event = getattr(self._queue, "release_event", None)
        if callable(release_event):
            if not release_event(event.event_id, self._config.worker_id, reason=reason):
                raise RuntimeError(f"PostgreSQL release update did not match event {event.event_id}.")
            return
        self._fail_event(event, reason)

    def _retry_delay_for_attempt(self, attempts: int) -> int:
        exponent = max(0, int(attempts or 1) - 1)
        return int(self._config.retry_delay_seconds * (2**exponent))

    @contextmanager
    def _shutdown_signal_handlers(self) -> Iterator[None]:
        signal_names = [name for name in ("SIGTERM", "SIGINT") if hasattr(signal, name)]
        previous_handlers: dict[int, Any] = {}

        def shutdown_handler(signum: int, _frame: Any) -> None:
            raise RuntimeWorkerShutdownRequested(signum)

        try:
            for name in signal_names:
                signum = int(getattr(signal, name))
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, shutdown_handler)
            yield
        finally:
            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)

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
        if event.trace_id:
            payload["trace_id"] = event.trace_id
        if event.source_version is not None:
            payload["source_version"] = event.source_version
        if retry is not None:
            payload["retry"] = retry
        if error:
            payload["error"] = error
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
