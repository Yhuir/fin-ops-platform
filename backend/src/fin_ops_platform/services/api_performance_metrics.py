from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from math import ceil
from threading import Lock
from typing import Iterator


@dataclass
class DatabaseTiming:
    query_count: int = 0
    connection_acquire_duration_ms: float = 0.0
    sql_execute_fetch_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    max_query_duration_ms: float = 0.0

    def record(self, duration_ms: float) -> None:
        safe_duration = max(0.0, float(duration_ms))
        self.query_count += 1
        self.sql_execute_fetch_duration_ms = round(self.sql_execute_fetch_duration_ms + safe_duration, 6)
        self.total_duration_ms = round(self.total_duration_ms + safe_duration, 6)
        self.max_query_duration_ms = max(self.max_query_duration_ms, safe_duration)

    def record_connection_acquire(self, duration_ms: float) -> None:
        safe_duration = max(0.0, float(duration_ms))
        self.connection_acquire_duration_ms = round(self.connection_acquire_duration_ms + safe_duration, 6)
        self.total_duration_ms = round(self.total_duration_ms + safe_duration, 6)


@dataclass(frozen=True)
class ApiPerformanceSample:
    duration_ms: float
    connection_acquire_duration_ms: float
    sql_execute_fetch_duration_ms: float
    database_duration_ms: float
    database_query_count: int
    status_code: int


_current_database_timing: ContextVar[DatabaseTiming | None] = ContextVar(
    "fin_ops_current_database_timing",
    default=None,
)


@contextmanager
def request_database_timing() -> Iterator[DatabaseTiming]:
    timing = DatabaseTiming()
    token = _current_database_timing.set(timing)
    try:
        yield timing
    finally:
        _current_database_timing.reset(token)


def current_request_database_metrics() -> DatabaseTiming | None:
    return _current_database_timing.get()


def record_database_query(duration_ms: float) -> None:
    timing = _current_database_timing.get()
    if timing is not None:
        timing.record(duration_ms)


def record_database_connection_acquire(duration_ms: float) -> None:
    timing = _current_database_timing.get()
    if timing is not None:
        timing.record_connection_acquire(duration_ms)


class ApiPerformanceRecorder:
    def __init__(self, *, max_samples_per_endpoint: int = 512) -> None:
        if max_samples_per_endpoint <= 0:
            raise ValueError("max_samples_per_endpoint must be positive.")
        self._max_samples_per_endpoint = int(max_samples_per_endpoint)
        self._samples: dict[str, deque[ApiPerformanceSample]] = defaultdict(
            lambda: deque(maxlen=self._max_samples_per_endpoint)
        )
        self._lock = Lock()

    def record_request(
        self,
        *,
        method: str,
        route_path: str,
        status_code: int,
        duration_ms: float,
        connection_acquire_duration_ms: float = 0.0,
        sql_execute_fetch_duration_ms: float = 0.0,
        database_duration_ms: float = 0.0,
        database_query_count: int = 0,
    ) -> None:
        endpoint = self._endpoint_key(method=method, route_path=route_path)
        sample = ApiPerformanceSample(
            duration_ms=max(0.0, float(duration_ms)),
            connection_acquire_duration_ms=max(0.0, float(connection_acquire_duration_ms)),
            sql_execute_fetch_duration_ms=max(0.0, float(sql_execute_fetch_duration_ms)),
            database_duration_ms=max(0.0, float(database_duration_ms)),
            database_query_count=max(0, int(database_query_count)),
            status_code=int(status_code),
        )
        with self._lock:
            self._samples[endpoint].append(sample)

    def summary(self) -> dict[str, object]:
        with self._lock:
            samples_by_endpoint = {
                endpoint: list(samples)
                for endpoint, samples in sorted(self._samples.items())
            }
        endpoints: dict[str, object] = {}
        total_sample_count = 0
        for endpoint, samples in samples_by_endpoint.items():
            total_sample_count += len(samples)
            endpoints[endpoint] = {
                "sample_count": len(samples),
                "duration_ms": _percentiles([sample.duration_ms for sample in samples]),
                "connection_acquire_ms": _percentiles([sample.connection_acquire_duration_ms for sample in samples]),
                "sql_execute_fetch_ms": _percentiles([sample.sql_execute_fetch_duration_ms for sample in samples]),
                "database_duration_ms": _percentiles([sample.database_duration_ms for sample in samples]),
                "database_query_count": _percentiles([float(sample.database_query_count) for sample in samples]),
                "last_status_code": samples[-1].status_code if samples else None,
            }
        return {
            "window_sample_limit": self._max_samples_per_endpoint,
            "total_sample_count": total_sample_count,
            "endpoints": endpoints,
        }

    @staticmethod
    def _endpoint_key(*, method: str, route_path: str) -> str:
        safe_method = str(method or "").strip().upper() or "UNKNOWN"
        safe_route_path = str(route_path or "").strip() or "/"
        return f"{safe_method} {safe_route_path}"


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    sorted_values = sorted(float(value) for value in values)
    return {
        "p50": _nearest_rank(sorted_values, 0.50),
        "p95": _nearest_rank(sorted_values, 0.95),
        "p99": _nearest_rank(sorted_values, 0.99),
    }


def _nearest_rank(sorted_values: list[float], percentile: float) -> float:
    index = max(0, min(len(sorted_values) - 1, ceil(percentile * len(sorted_values)) - 1))
    return round(sorted_values[index], 3)
