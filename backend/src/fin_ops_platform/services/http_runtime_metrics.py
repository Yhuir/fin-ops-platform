from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class HttpRuntimeSnapshot:
    active_requests: int
    peak_active_requests: int
    rejected_requests: int
    request_body_rejections: int
    database_backpressure_rejections: int


class HttpRuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active_requests = 0
        self._peak_active_requests = 0
        self._rejected_requests = 0
        self._request_body_rejections = 0
        self._database_backpressure_rejections = 0

    def request_started(self) -> int:
        with self._lock:
            self._active_requests += 1
            self._peak_active_requests = max(self._peak_active_requests, self._active_requests)
            return self._active_requests

    def request_finished(self) -> int:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            return self._active_requests

    def reject_body(self) -> None:
        with self._lock:
            self._rejected_requests += 1
            self._request_body_rejections += 1

    def reject_database_backpressure(self) -> None:
        with self._lock:
            self._rejected_requests += 1
            self._database_backpressure_rejections += 1

    def snapshot(self) -> HttpRuntimeSnapshot:
        with self._lock:
            return HttpRuntimeSnapshot(
                active_requests=self._active_requests,
                peak_active_requests=self._peak_active_requests,
                rejected_requests=self._rejected_requests,
                request_body_rejections=self._request_body_rejections,
                database_backpressure_rejections=self._database_backpressure_rejections,
            )


HTTP_RUNTIME_METRICS = HttpRuntimeMetrics()
