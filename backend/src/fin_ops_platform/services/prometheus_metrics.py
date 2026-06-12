from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def render_prometheus_metrics(health_payload: Mapping[str, Any]) -> str:
    writer = _PrometheusWriter()
    status = str(health_payload.get("status") or "")
    writer.gauge(
        "finops_ready",
        "FinOps API readiness status, 1 when ready.",
        1 if status == "ready" else 0,
        {"status": status or "unknown"},
    )

    runtime_release = _mapping(health_payload.get("runtime_release"))
    writer.gauge(
        "finops_runtime_release_consistent",
        "FinOps release import path and release metadata consistency.",
        _bool_value(runtime_release.get("consistent")),
        {"release": _release_name(runtime_release)},
    )
    production_guard = _mapping(health_payload.get("production_runtime_guard"))
    writer.gauge(
        "finops_production_runtime_guard_consistent",
        "FinOps production runtime guard consistency.",
        _bool_value(production_guard.get("consistent")),
        {
            "storage_backend": str(production_guard.get("storage_backend") or "unknown"),
            "bootstrap_mode": str(production_guard.get("bootstrap_mode") or "unknown"),
        },
    )

    storage = _mapping(health_payload.get("storage"))
    writer.gauge(
        "finops_postgres_schema_version",
        "Current PostgreSQL schema version reported by the application runtime.",
        storage.get("postgres_schema_version"),
    )
    writer.gauge(
        "finops_redis_hit_total",
        "Process-local Redis helper hit count.",
        storage.get("redis_hit_count"),
    )
    writer.gauge(
        "finops_redis_miss_total",
        "Process-local Redis helper miss count.",
        storage.get("redis_miss_count"),
    )

    runtime = _mapping(health_payload.get("runtime_infrastructure"))
    _runtime_metrics(writer, runtime)
    _api_performance_metrics(writer, _mapping(health_payload.get("api_performance")))
    return writer.render()


def _runtime_metrics(writer: "_PrometheusWriter", runtime: Mapping[str, Any]) -> None:
    for status, count in _mapping(runtime.get("queue_backlog")).items():
        writer.gauge(
            "finops_outbox_events",
            "PostgreSQL durable outbox events by status.",
            count,
            {"status": str(status)},
        )
    for status, count in _mapping(runtime.get("dirty_scopes")).items():
        writer.gauge(
            "finops_read_model_dirty_scopes",
            "PostgreSQL durable read model dirty scopes by status.",
            count,
            {"status": str(status)},
        )

    for name in (
        "failed_jobs",
        "oldest_pending_event_age_seconds",
        "worker_heartbeat_lag_seconds",
        "missing_required_worker_count",
        "stale_required_worker_count",
        "mismatched_required_worker_count",
        "read_model_refresh_sample_count",
        "read_model_refresh_failure_rate",
        "rabbitmq_unpublished_backlog",
        "rabbitmq_publish_failed_backlog",
        "rabbitmq_dispatcher_lag_seconds",
        "rabbitmq_queue_depth",
        "rabbitmq_unacked_messages",
        "rabbitmq_consumer_count",
        "rabbitmq_dlq_count",
        "rabbitmq_oldest_message_age_seconds",
        "rabbitmq_publish_confirm_sample_limit",
        "stale_dirty_scope_count",
    ):
        writer.gauge(
            f"finops_{name}",
            _help_text(name),
            runtime.get(name),
        )

    for quantile, value in _percentiles(runtime.get("read_model_refresh_duration_ms")).items():
        writer.gauge(
            "finops_read_model_refresh_duration_ms",
            "Read model refresh duration percentiles in milliseconds.",
            value,
            {"quantile": quantile},
        )
    for quantile, value in _percentiles(runtime.get("read_model_refresh_enqueue_to_fresh_ms")).items():
        writer.gauge(
            "finops_read_model_refresh_enqueue_to_fresh_ms",
            "Read model enqueue-to-fresh latency percentiles in milliseconds.",
            value,
            {"quantile": quantile},
        )
    for row in _list_of_mappings(runtime.get("read_model_refresh_by_key")):
        labels = {
            "read_model_key": str(row.get("key") or ""),
            "event_type": str(row.get("event_type") or ""),
            "scope_type": str(row.get("scope_type") or ""),
        }
        for quantile, value in _percentiles(row.get("duration_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_by_key_duration_ms",
                "Read model refresh duration percentiles by read model key in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for quantile, value in _percentiles(row.get("enqueue_to_fresh_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_by_key_enqueue_to_fresh_ms",
                "Read model enqueue-to-fresh latency percentiles by read model key in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for field in (
            "sample_count",
            "completed_sample_count",
            "failed_count",
            "failure_rate",
        ):
            writer.gauge(
                f"finops_read_model_refresh_by_key_{field}",
                _help_text(f"read_model_refresh_by_key_{field}"),
                row.get(field),
                labels,
            )
    for window, row in _mapping(runtime.get("read_model_refresh_current_windows")).items():
        metric = _mapping(row)
        labels = {"window": str(window)}
        for quantile, value in _percentiles(metric.get("duration_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_current_window_duration_ms",
                "Read model refresh duration percentiles by current window in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for quantile, value in _percentiles(metric.get("enqueue_to_fresh_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_current_window_enqueue_to_fresh_ms",
                "Read model enqueue-to-fresh latency percentiles by current window in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for field in (
            "sample_count",
            "completed_sample_count",
            "failed_count",
            "failure_rate",
        ):
            writer.gauge(
                f"finops_read_model_refresh_current_window_{field}",
                _help_text(f"read_model_refresh_current_window_{field}"),
                metric.get(field),
                labels,
            )
    for row in _list_of_mappings(runtime.get("read_model_refresh_by_key_current_windows")):
        labels = {
            "read_model_key": str(row.get("key") or ""),
            "event_type": str(row.get("event_type") or ""),
            "scope_type": str(row.get("scope_type") or ""),
            "window": str(row.get("window") or ""),
        }
        for quantile, value in _percentiles(row.get("duration_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_by_key_current_window_duration_ms",
                "Read model refresh duration percentiles by key and current window in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for quantile, value in _percentiles(row.get("enqueue_to_fresh_ms")).items():
            writer.gauge(
                "finops_read_model_refresh_by_key_current_window_enqueue_to_fresh_ms",
                "Read model enqueue-to-fresh latency percentiles by key and current window in milliseconds.",
                value,
                {**labels, "quantile": quantile},
            )
        for field in (
            "sample_count",
            "completed_sample_count",
            "failed_count",
            "failure_rate",
        ):
            writer.gauge(
                f"finops_read_model_refresh_by_key_current_window_{field}",
                _help_text(f"read_model_refresh_by_key_current_window_{field}"),
                row.get(field),
                labels,
            )
    for status, count in _mapping(runtime.get("rabbitmq_publish_status")).items():
        writer.gauge(
            "finops_rabbitmq_publish_events",
            "Pending RabbitMQ dispatch publish status counts.",
            count,
            {"publish_status": str(status)},
        )
    for quantile, value in _percentiles(runtime.get("rabbitmq_publish_confirm_latency_ms")).items():
        writer.gauge(
            "finops_rabbitmq_publish_confirm_latency_ms",
            "RabbitMQ publisher confirm latency percentiles in milliseconds.",
            value,
            {"quantile": quantile},
        )

    for row in _list_of_mappings(runtime.get("worker_metrics")):
        labels = {
            "worker_instance": str(row.get("worker_instance") or ""),
            "worker_kind": str(row.get("worker_kind") or ""),
            "status": str(row.get("status") or "unknown"),
        }
        writer.gauge(
            "finops_worker_heartbeat_lag_seconds",
            "Runtime worker heartbeat lag in seconds.",
            row.get("heartbeat_lag_seconds"),
            labels,
        )
        writer.gauge(
            "finops_worker_required",
            "Runtime worker required flag.",
            _bool_value(row.get("required")),
            labels,
        )
        writer.gauge(
            "finops_worker_current_effective",
            "Runtime worker current-effective flag.",
            _bool_value(row.get("current_effective")),
            labels,
        )
        warning_code = str(row.get("warning_code") or "")
        if warning_code:
            writer.gauge(
                "finops_worker_warning",
                "Runtime worker warning rows by warning code.",
                1,
                {**labels, "warning_code": warning_code},
            )

    workbench = _mapping(runtime.get("workbench_read_model"))
    for name in (
        "active_scope_count",
        "active_row_count",
        "active_group_count",
        "active_summary_count",
        "building_scope_count",
        "failed_scope_count",
    ):
        writer.gauge(
            f"finops_workbench_read_model_{name}",
            _help_text(f"workbench_read_model_{name}"),
            workbench.get(name),
        )


def _api_performance_metrics(writer: "_PrometheusWriter", api_performance: Mapping[str, Any]) -> None:
    endpoints = _mapping(api_performance.get("endpoints"))
    for endpoint, raw_metric in endpoints.items():
        metric = _mapping(raw_metric)
        labels = {"endpoint": str(endpoint)}
        writer.gauge(
            "finops_api_request_samples",
            "Process rolling-window API request sample count by endpoint.",
            metric.get("sample_count"),
            labels,
        )
        writer.gauge(
            "finops_api_request_last_status_code",
            "Last HTTP status code observed for the endpoint.",
            metric.get("last_status_code"),
            labels,
        )
        for field in (
            "duration_ms",
            "connection_acquire_ms",
            "sql_execute_fetch_ms",
            "database_duration_ms",
            "database_query_count",
        ):
            for quantile, value in _percentiles(metric.get(field)).items():
                writer.gauge(
                    f"finops_api_{field}",
                    _help_text(f"api_{field}"),
                    value,
                    {**labels, "quantile": quantile},
                )


class _PrometheusWriter:
    def __init__(self) -> None:
        self._lines: list[str] = []
        self._declared: set[str] = set()

    def gauge(
        self,
        name: str,
        help_text: str,
        value: Any,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        numeric_value = _numeric_value(value)
        if numeric_value is None:
            return
        metric_name = _metric_name(name)
        if metric_name not in self._declared:
            self._lines.append(f"# HELP {metric_name} {_escape_help(help_text)}")
            self._lines.append(f"# TYPE {metric_name} gauge")
            self._declared.add(metric_name)
        label_text = _format_labels(labels or {})
        self._lines.append(f"{metric_name}{label_text} {_format_number(numeric_value)}")

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _percentiles(value: Any) -> dict[str, Any]:
    raw = _mapping(value)
    return {
        "0.5": raw.get("p50"),
        "0.95": raw.get("p95"),
        "0.99": raw.get("p99"),
    }


def _numeric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return float(value) if isinstance(value, bool) else None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) else None


def _bool_value(value: Any) -> int:
    return 1 if bool(value) else 0


def _release_name(runtime_release: Mapping[str, Any]) -> str:
    metadata = _mapping(runtime_release.get("release_metadata"))
    return str(metadata.get("release_name") or "unknown")


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(float(value))


def _format_labels(labels: Mapping[str, str]) -> str:
    filtered = {str(key): str(value) for key, value in labels.items() if str(key)}
    if not filtered:
        return ""
    parts = [
        f'{_label_name(key)}="{_escape_label(value)}"'
        for key, value in sorted(filtered.items())
    ]
    return "{" + ",".join(parts) + "}"


def _metric_name(value: str) -> str:
    return _sanitize_identifier(value, first_char_prefix="_")


def _label_name(value: str) -> str:
    return _sanitize_identifier(value, first_char_prefix="_")


def _sanitize_identifier(value: str, *, first_char_prefix: str) -> str:
    text = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(value))
    if not text:
        return first_char_prefix
    if text[0].isdigit():
        return f"{first_char_prefix}{text}"
    return text


def _escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _escape_help(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n")


def _help_text(metric: str) -> str:
    return metric.replace("_", " ").capitalize() + "."
