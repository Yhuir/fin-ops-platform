from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DEFAULT_READY_SAMPLE_LIMIT = 5
MAX_READY_SAMPLE_STRING_LENGTH = 500

_RUNTIME_KEEP_KEYS = (
    "queue_backlog",
    "dirty_scopes",
    "oldest_pending_event_age_seconds",
    "worker_heartbeat_lag_seconds",
    "missing_required_worker_count",
    "stale_required_worker_count",
    "mismatched_required_worker_count",
    "failed_jobs",
    "stale_dirty_scope_count",
    "critical_failed_outbox_count",
    "critical_failed_dirty_scope_count",
    "critical_stale_dirty_scope_count",
    "read_model_refresh_duration_ms",
    "read_model_refresh_enqueue_to_fresh_ms",
    "read_model_refresh_sample_count",
    "read_model_refresh_failure_rate",
    "read_model_refresh_current_windows",
    "rabbitmq_publish_status",
    "rabbitmq_unpublished_backlog",
    "rabbitmq_publish_failed_backlog",
    "rabbitmq_dispatcher_lag_seconds",
    "rabbitmq_publish_confirm_latency_ms",
    "rabbitmq_queue_depth",
    "rabbitmq_unacked_messages",
    "rabbitmq_consumer_count",
    "rabbitmq_dlq_count",
    "rabbitmq_metric_error",
    "redis_hit_count",
    "redis_miss_count",
)

_RUNTIME_SUMMARY_KEYS = (
    "worker_metrics",
    "read_model_refresh_by_key",
    "read_model_refresh_by_key_current_windows",
    "read_model_refresh_slow_events",
    "read_model_refresh_current_slow_events",
    "stale_dirty_scopes",
    "dirty_scopes_by_scope",
    "pending_outbox_events_by_scope",
    "critical_read_models",
    "rabbitmq_queues",
)

_WORKER_SAMPLE_KEYS = (
    "worker_id",
    "worker_instance",
    "worker_kind",
    "expected_worker_kind",
    "status",
    "warning_code",
    "required",
    "current_effective",
    "worker_status",
    "heartbeat_lag_seconds",
)


def compact_ready_payload(payload: dict[str, Any], *, sample_limit: int = DEFAULT_READY_SAMPLE_LIMIT) -> dict[str, Any]:
    """Mutate the readiness payload into a lightweight probe contract."""
    entrypoints = payload.pop("entrypoints", None)
    if isinstance(entrypoints, list):
        payload["entrypoint_count"] = len(entrypoints)
    capabilities = payload.pop("capabilities", None)
    if isinstance(capabilities, list):
        payload["capability_count"] = len(capabilities)

    storage = payload.get("storage")
    if isinstance(storage, dict):
        storage.pop("runtime_infrastructure", None)

    runtime = payload.get("runtime_infrastructure")
    if isinstance(runtime, dict):
        payload["runtime_infrastructure"] = compact_runtime_infrastructure(runtime, sample_limit=sample_limit)
    return payload


def compact_runtime_infrastructure(
    runtime: Mapping[str, Any],
    *,
    sample_limit: int = DEFAULT_READY_SAMPLE_LIMIT,
) -> dict[str, Any]:
    compact: dict[str, Any] = {key: runtime[key] for key in _RUNTIME_KEEP_KEYS if key in runtime}
    worker_metrics = runtime.get("worker_metrics")
    if isinstance(worker_metrics, list):
        compact["worker_metric_count"] = len(worker_metrics)
        compact["worker_status_counts"] = _worker_status_counts(worker_metrics)
        problem_samples = _worker_problem_samples(worker_metrics, sample_limit=sample_limit)
        if problem_samples:
            compact["worker_problem_samples"] = problem_samples

    for key in _RUNTIME_SUMMARY_KEYS:
        if key == "worker_metrics" or key not in runtime:
            continue
        compact[f"{key}_summary"] = _collection_summary(runtime[key], sample_limit=sample_limit)
    return compact


def _worker_status_counts(worker_metrics: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for worker in worker_metrics:
        if not isinstance(worker, Mapping):
            continue
        if worker.get("current_effective") is False:
            continue
        status = str(worker.get("status") or worker.get("worker_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _worker_problem_samples(worker_metrics: list[Any], *, sample_limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for worker in worker_metrics:
        if not isinstance(worker, Mapping):
            continue
        status = str(worker.get("status") or worker.get("worker_status") or "unknown")
        warning_code = str(worker.get("warning_code") or "").strip()
        required = bool(worker.get("required"))
        current_effective = worker.get("current_effective")
        if status in {"available", "idle", "ok"} and not warning_code and (current_effective is not False or not required):
            continue
        samples.append({key: worker[key] for key in _WORKER_SAMPLE_KEYS if key in worker})
        if len(samples) >= sample_limit:
            break
    return samples


def _collection_summary(value: Any, *, sample_limit: int) -> dict[str, Any]:
    if isinstance(value, list):
        return {
            "count": len(value),
            "samples": [_bounded_value(item) for item in value[:sample_limit]],
        }
    if isinstance(value, Mapping):
        keys = list(value.keys())
        return {
            "count": len(keys),
            "samples": {str(key): _bounded_value(value[key]) for key in keys[:sample_limit]},
        }
    return {
        "count": 1 if value is not None else 0,
        "samples": [_bounded_value(value)] if value is not None else [],
    }


def _bounded_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _bounded_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:DEFAULT_READY_SAMPLE_LIMIT]]
    if isinstance(value, str) and len(value) > MAX_READY_SAMPLE_STRING_LENGTH:
        return f"{value[:MAX_READY_SAMPLE_STRING_LENGTH]}..."
    return value
