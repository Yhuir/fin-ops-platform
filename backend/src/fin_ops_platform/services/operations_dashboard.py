from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import Any, Callable

from fin_ops_platform.services.api_performance_metrics import ApiPerformanceRecorder
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


DEFAULT_OPERATION_ENDPOINTS = (
    "GET /api/workbench/summary",
    "GET /api/workbench/groups",
    "GET /api/search",
    "GET /api/pending-invoices/rows",
    "GET /api/cost-statistics",
    "GET /api/cost-statistics/explorer",
    "GET /api/tax-offset",
    "GET /api/app-health",
    "GET /api/operations/app-health-dashboard",
)

EMPTY_PERCENTILES = {"p50": None, "p95": None, "p99": None}


class OperationsDashboardService:
    def __init__(
        self,
        connection: Any,
        *,
        api_performance_recorder: ApiPerformanceRecorder,
        runtime_repository: Any | None = None,
    ) -> None:
        self._connection = connection
        self._api_performance_recorder = api_performance_recorder
        self._runtime_repository = runtime_repository or _default_runtime_repository(connection)

    def build_payload(self) -> dict[str, Any]:
        warnings: list[str] = []
        return {
            "generated_at": _isoformat(datetime.now(UTC)),
            "data_inventory": self._data_inventory(warnings),
            "request_performance": self._request_performance(),
            "runtime_performance": self._runtime_performance(warnings),
            "freshness": {"warnings": sorted(set(warnings))},
        }

    def _data_inventory(self, warnings: list[str]) -> dict[str, Any]:
        return {
            "bank": self._safe_block("bank_inventory_unknown", warnings, self._bank_inventory),
            "invoice": self._safe_invoice_inventory(warnings),
            "oa": self._safe_block("oa_inventory_unknown", warnings, self._oa_inventory),
            "import_events": self._safe_rows("import_events_unknown", warnings, self._import_events),
        }

    def _bank_inventory(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              count(*) filter (
                where coalesce(nullif(bank_transactions.status, ''), 'active') <> 'deleted'
              )::bigint as total_count,
              max(coalesce(import_batches.imported_at, bank_transactions.updated_at, bank_transactions.created_at)) as latest_synced_at
            from app.bank_transactions
            left join app.import_batches
              on import_batches.id = bank_transactions.source_batch_id
              or import_batches.legacy_mongo_id = bank_transactions.legacy_source_batch_id
            """
        ) or {}
        total_count = _optional_int(row.get("total_count"))
        latest_synced_at = _isoformat(row.get("latest_synced_at"))
        return _inventory_block(
            total_count=total_count,
            latest_synced_at=latest_synced_at,
            sources=[
                _inventory_source(
                    key="bank_transactions",
                    label="银行流水",
                    count=total_count,
                    latest_synced_at=latest_synced_at,
                )
            ],
        )

    def _invoice_inventory(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            with invoice_flags as (
              select
                invoices.id,
                coalesce(import_batches.imported_at, invoices.updated_at, invoices.created_at) as latest_synced_at,
                exists (
                  select 1
                  from jsonb_array_elements(
                    case
                      when jsonb_typeof(invoices.source_links) = 'array' then invoices.source_links
                      else '[]'::jsonb
                    end
                  ) as source_link(value)
                  where lower(coalesce(
                    source_link.value->>'source_type',
                    source_link.value->>'type',
                    source_link.value->>'source',
                    ''
                  )) = 'manual_invoice_import'
                ) as is_manual,
                exists (
                  select 1
                  from jsonb_array_elements(
                    case
                      when jsonb_typeof(invoices.source_links) = 'array' then invoices.source_links
                      else '[]'::jsonb
                    end
                  ) as source_link(value)
                  where lower(coalesce(
                    source_link.value->>'source_type',
                    source_link.value->>'type',
                    source_link.value->>'source',
                    ''
                  )) = 'oa_attachment_invoice'
                ) as is_oa_attachment
              from app.invoices
              left join app.import_batches
                on import_batches.id = invoices.source_batch_id
                or import_batches.legacy_mongo_id = invoices.legacy_source_batch_id
              where coalesce(nullif(invoices.status, ''), 'active') <> 'deleted'
            )
            select
              count(*)::bigint as total_count,
              count(*) filter (where is_manual)::bigint as manual_count,
              count(*) filter (where is_oa_attachment)::bigint as oa_attachment_count,
              count(*) filter (where is_oa_attachment and not is_manual)::bigint as oa_attachment_non_manual_count,
              max(latest_synced_at) as latest_synced_at,
              max(latest_synced_at) filter (where is_manual) as manual_latest_synced_at,
              max(latest_synced_at) filter (where is_oa_attachment) as oa_attachment_latest_synced_at
            from invoice_flags
            """
        ) or {}
        latest_synced_at = _isoformat(row.get("latest_synced_at"))
        return _inventory_block(
            total_count=_optional_int(row.get("total_count")),
            latest_synced_at=latest_synced_at,
            sources=[
                _inventory_source(
                    key="manual",
                    label="手工导入",
                    count=_optional_int(row.get("manual_count")),
                    latest_synced_at=_isoformat(row.get("manual_latest_synced_at")),
                ),
                _inventory_source(
                    key="oa_attachment",
                    label="OA 解析",
                    count=_optional_int(row.get("oa_attachment_count")),
                    latest_synced_at=_isoformat(row.get("oa_attachment_latest_synced_at")),
                    supplementary_count=_optional_int(row.get("oa_attachment_non_manual_count")),
                ),
            ],
        )

    def _oa_inventory(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              (select count(*)::bigint from app.oa_applications) as oa_records_count,
              (select count(*)::bigint from app.oa_application_items) as oa_items_count,
              (select max(synced_at) from app.oa_applications) as oa_records_latest_synced_at,
              (select max(coalesce(finished_at, started_at))
                 from app.oa_sync_runs
                where sync_type = 'oa_projection'
                  and status in ('success', 'succeeded', 'done')) as latest_successful_sync_at,
              coalesce(
                (select max(coalesce(finished_at, started_at))
                   from app.oa_sync_runs
                  where sync_type = 'oa_projection'
                    and status in ('success', 'succeeded', 'done')),
                (select max(last_success_at) from app.oa_sync_watermarks),
                (select max(synced_at) from app.oa_applications)
              ) as oa_latest_synced_at
            """
        ) or {}
        return _inventory_block(
            total_count=_optional_int(row.get("oa_records_count")),
            latest_synced_at=_isoformat(row.get("oa_latest_synced_at")),
            sources=[
                _inventory_source(
                    key="oa_records",
                    label="单据",
                    count=_optional_int(row.get("oa_records_count")),
                    latest_synced_at=_isoformat(row.get("oa_latest_synced_at")),
                ),
                _inventory_source(
                    key="oa_items",
                    label="明细",
                    count=_optional_int(row.get("oa_items_count")),
                    latest_synced_at=_isoformat(row.get("oa_latest_synced_at")),
                ),
            ],
        )

    def _import_events(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.extend(
            self._connection.fetch_all(
                """
                select
                  coalesce(legacy_mongo_id, id::text) as event_id,
                  case
                    when batch_type = 'bank_transaction' then 'bank_transactions'
                    else 'manual'
                  end as source_key,
                  case
                    when batch_type = 'bank_transaction' then '流水导入'
                    else '手工导入'
                  end as label,
                  source_name,
                  imported_by,
                  success_count::bigint as count,
                  null::bigint as supplementary_count,
                  imported_at,
                  status
                from app.import_batches
                where batch_type in ('bank_transaction', 'input_invoice', 'output_invoice')
                order by imported_at desc, event_id desc
                """
            )
            or []
        )
        rows.extend(
            self._connection.fetch_all(
                """
                with invoice_flags as (
                  select
                    invoices.id,
                    invoices.updated_at,
                    exists (
                      select 1
                      from jsonb_array_elements(
                        case
                          when jsonb_typeof(invoices.source_links) = 'array' then invoices.source_links
                          else '[]'::jsonb
                        end
                      ) as source_link(value)
                      where lower(coalesce(
                        source_link.value->>'source_type',
                        source_link.value->>'type',
                        source_link.value->>'source',
                        ''
                      )) = 'manual_invoice_import'
                    ) as is_manual,
                    case
                      when jsonb_typeof(invoices.source_links) = 'array' then invoices.source_links
                      else '[]'::jsonb
                    end as source_links
                  from app.invoices
                  where coalesce(nullif(invoices.status, ''), 'active') <> 'deleted'
                ),
                oa_attachment_source_links as (
                  select
                    invoice_flags.id,
                    invoice_flags.is_manual,
                    coalesce(
                      case
                        when nullif(source_link.value->>'created_at', '') ~ '^\\d{4}-\\d{2}-\\d{2}T'
                        then (source_link.value->>'created_at')::timestamptz
                        else null
                      end,
                      invoice_flags.updated_at
                    ) as imported_at
                  from invoice_flags
                  cross join lateral jsonb_array_elements(invoice_flags.source_links) as source_link(value)
                  where lower(coalesce(
                    source_link.value->>'source_type',
                    source_link.value->>'type',
                    source_link.value->>'source',
                    ''
                  )) = 'oa_attachment_invoice'
                )
                select
                  'oa-attachment-' || to_char(date_trunc('second', imported_at), 'YYYYMMDDHH24MISS') as event_id,
                  'oa_attachment' as source_key,
                  'OA 解析' as label,
                  'OA 附件解析' as source_name,
                  'oa_sync' as imported_by,
                  count(distinct id)::bigint as count,
                  count(distinct id) filter (where not is_manual)::bigint as supplementary_count,
                  max(imported_at) as imported_at,
                  'completed' as status
                from oa_attachment_source_links
                group by date_trunc('second', imported_at)
                order by imported_at desc
                """
            )
            or []
        )
        rows.extend(
            self._connection.fetch_all(
                """
                select
                  id::text as event_id,
                  'oa_records' as source_key,
                  'OA 同步' as label,
                  sync_type as source_name,
                  'oa_sync' as imported_by,
                  upserted_count::bigint as count,
                  null::bigint as supplementary_count,
                  coalesce(finished_at, started_at) as imported_at,
                  status
                from app.oa_sync_runs
                where sync_type = 'oa_projection'
                order by coalesce(finished_at, started_at) desc, id desc
                """
            )
            or []
        )
        return [
            _inventory_event(row)
            for row in sorted(rows, key=lambda item: _isoformat(item.get("imported_at")) or "", reverse=True)
        ]

    def _request_performance(self) -> dict[str, Any]:
        summary = self._api_performance_recorder.summary()
        raw_endpoints = summary.get("endpoints") if isinstance(summary, dict) else {}
        endpoint_map = raw_endpoints if isinstance(raw_endpoints, dict) else {}
        rows: list[dict[str, Any]] = []
        seen = set(DEFAULT_OPERATION_ENDPOINTS)
        for endpoint in [*DEFAULT_OPERATION_ENDPOINTS, *sorted(str(key) for key in endpoint_map if key not in seen)]:
            raw = endpoint_map.get(endpoint)
            metric = raw if isinstance(raw, dict) else {}
            rows.append(
                {
                    "endpoint": endpoint,
                    "sample_count": int(metric.get("sample_count") or 0),
                    "last_status_code": _optional_int(metric.get("last_status_code")),
                    "duration_ms": _percentiles(metric.get("duration_ms")),
                    "database_duration_ms": _percentiles(metric.get("database_duration_ms")),
                    "connection_acquire_ms": _percentiles(metric.get("connection_acquire_ms")),
                    "sql_execute_fetch_ms": _percentiles(metric.get("sql_execute_fetch_ms")),
                    "database_query_count": _percentiles(metric.get("database_query_count")),
                }
            )
        rows.sort(key=_endpoint_sort_key)
        return {
            "window": {
                "type": "process_rolling_window",
                "sample_limit_per_endpoint": int(summary.get("window_sample_limit") or 0),
                "reset_on_restart": True,
            },
            "endpoints": rows,
        }

    def _runtime_performance(self, warnings: list[str]) -> dict[str, Any]:
        return {
            "outbox": self._safe_metric("outbox_metrics_unavailable", warnings, self._runtime_repository.dashboard_outbox_metric),
            "queues": self._runtime_rows("rabbitmq_metrics_unavailable", warnings, self._runtime_repository.dashboard_queue_metrics),
            "read_models": self._runtime_rows("read_model_metrics_unavailable", warnings, self._runtime_repository.dashboard_read_model_metrics),
            "workers": self._runtime_rows("worker_metrics_unavailable", warnings, self._runtime_repository.dashboard_worker_metrics),
        }

    def _safe_block(self, warning_code: str, warnings: list[str], loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return loader()
        except Exception:
            warnings.append(warning_code)
            return _inventory_block(total_count=None, latest_synced_at=None, sources=[], status="unknown")

    def _safe_metric(self, warning_code: str, warnings: list[str], loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            metric = loader()
        except Exception:
            warnings.append(warning_code)
            return {
                "pending_count": None,
                "publishing_count": None,
                "failed_count": None,
                "publish_failed_count": None,
                "oldest_pending_age_seconds": None,
                "status": "unknown",
                "warning_code": warning_code,
            }
        warning = metric.get("warning_code")
        if warning:
            warnings.append(str(warning))
        return metric

    def _safe_invoice_inventory(self, warnings: list[str]) -> dict[str, Any]:
        try:
            return self._invoice_inventory()
        except Exception:
            warnings.append("invoice_inventory_unknown")
            return _inventory_block(
                total_count=None,
                latest_synced_at=None,
                sources=[
                    _inventory_source(
                        key="manual",
                        label="手工导入",
                        count=None,
                        latest_synced_at=None,
                    ),
                    _inventory_source(
                        key="oa_attachment",
                        label="OA 解析",
                        count=None,
                        latest_synced_at=None,
                        supplementary_count=None,
                    ),
                ],
                status="unknown",
            )

    def _safe_rows(self, warning_code: str, warnings: list[str], loader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        try:
            return loader()
        except Exception:
            warnings.append(warning_code)
            return []

    def _runtime_rows(self, warning_code: str, warnings: list[str], loader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        try:
            rows = loader()
        except Exception:
            warnings.append(warning_code)
            return []
        for row in rows:
            warning = row.get("warning_code")
            if warning and row.get("required") is not False and row.get("current_effective") is not False:
                warnings.append(str(warning))
        return rows


def _endpoint_sort_key(row: dict[str, Any]) -> tuple[int, float | str]:
    p95 = row.get("duration_ms", {}).get("p95") if isinstance(row.get("duration_ms"), dict) else None
    if p95 is not None:
        return (0, -float(p95))
    last_status_code = row.get("last_status_code")
    if isinstance(last_status_code, int) and last_status_code >= 400:
        return (1, -last_status_code)
    return (2, str(row.get("endpoint") or ""))


def _default_runtime_repository(connection: Any) -> RuntimeMonitoringRepository:
    if os.getenv("FIN_OPS_APP_HEALTH_DASHBOARD_RABBITMQ_METRICS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return RuntimeMonitoringRepository(connection)
    return RuntimeMonitoringRepository(
        connection,
        rabbitmq_metrics_provider=_DashboardRabbitMqMetricsUnavailable(),
    )


class _DashboardRabbitMqMetricsUnavailable:
    def summary(self) -> dict[str, Any]:
        return {
            "rabbitmq_management_configured": False,
            "rabbitmq_metric_error": "dashboard_rabbitmq_metrics_skipped",
        }


def _inventory_block(
    *,
    total_count: int | None,
    latest_synced_at: str | None,
    sources: list[dict[str, Any]],
    status: str = "available",
) -> dict[str, Any]:
    return {
        "total_count": total_count,
        "latest_synced_at": latest_synced_at,
        "status": status,
        "sources": sources,
    }


def _inventory_source(
    *,
    key: str,
    label: str,
    count: int | None,
    latest_synced_at: str | None,
    supplementary_count: int | None = None,
    status: str = "available",
) -> dict[str, Any]:
    payload = {
        "key": key,
        "label": label,
        "count": count,
        "latest_synced_at": latest_synced_at,
        "status": status if count is not None else "unknown",
    }
    if supplementary_count is not None or key == "oa_attachment":
        payload["supplementary_count"] = supplementary_count
    return payload


def _inventory_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": str(row.get("event_id") or ""),
        "source_key": str(row.get("source_key") or ""),
        "label": str(row.get("label") or ""),
        "source_name": str(row.get("source_name") or ""),
        "imported_by": str(row.get("imported_by") or ""),
        "count": _optional_int(row.get("count")),
        "supplementary_count": _optional_int(row.get("supplementary_count")),
        "imported_at": _isoformat(row.get("imported_at")),
        "status": str(row.get("status") or "unknown"),
    }


def _percentiles(value: object) -> dict[str, float | None]:
    if not isinstance(value, dict):
        return dict(EMPTY_PERCENTILES)
    return {
        "p50": _optional_float(value.get("p50")),
        "p95": _optional_float(value.get("p95")),
        "p99": _optional_float(value.get("p99")),
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _isoformat(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None
