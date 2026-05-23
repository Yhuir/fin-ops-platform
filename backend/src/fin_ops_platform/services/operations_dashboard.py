from __future__ import annotations

from datetime import UTC, datetime
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
        self._runtime_repository = runtime_repository or RuntimeMonitoringRepository(connection)

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
            "invoice": self._safe_block("invoice_inventory_unknown", warnings, lambda: self._invoice_inventory(warnings)),
            "oa": self._safe_block("oa_inventory_unknown", warnings, self._oa_inventory),
        }

    def _bank_inventory(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              count(*) filter (where coalesce(nullif(status, ''), 'active') <> 'deleted')::bigint as total_count,
              max(coalesce(import_batches.imported_at, bank_transactions.updated_at, bank_transactions.created_at)) as latest_synced_at
            from app.bank_transactions
            left join app.import_batches on import_batches.id = bank_transactions.source_batch_id
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

    def _invoice_inventory(self, warnings: list[str]) -> dict[str, Any]:
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
                (
                  nullif(invoices.etc_invoice_id, '') is not null
                  or coalesce(invoices.tags, array[]::text[]) && array['ETC', 'etc', 'etc_invoice']::text[]
                  or exists (
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
                    )) in ('etc_import', 'etc_invoice_import', 'etc_submission')
                  )
                ) as is_etc,
                nullif(invoices.oa_form_id, '') is not null as is_oa_attachment
              from app.invoices
              left join app.import_batches on import_batches.id = invoices.source_batch_id
              where coalesce(nullif(invoices.status, ''), 'active') <> 'deleted'
            )
            select
              count(*)::bigint as total_count,
              count(*) filter (where not is_manual and not is_etc and not is_oa_attachment)::bigint as standard_count,
              count(*) filter (where is_manual)::bigint as manual_count,
              count(*) filter (where is_etc)::bigint as etc_count,
              count(*) filter (where is_oa_attachment)::bigint as app_oa_attachment_count,
              max(latest_synced_at) as latest_synced_at,
              max(latest_synced_at) filter (where not is_manual and not is_etc and not is_oa_attachment) as standard_latest_synced_at,
              max(latest_synced_at) filter (where is_manual) as manual_latest_synced_at,
              max(latest_synced_at) filter (where is_etc) as etc_latest_synced_at,
              max(latest_synced_at) filter (where is_oa_attachment) as app_oa_attachment_latest_synced_at
            from invoice_flags
            """
        ) or {}
        oa_attachment = self._oa_attachment_invoice_inventory(warnings)
        latest_synced_at = _max_timestamp(
            row.get("latest_synced_at"),
            oa_attachment.get("latest_synced_at"),
        )
        return _inventory_block(
            total_count=_optional_int(row.get("total_count")),
            latest_synced_at=latest_synced_at,
            sources=[
                _inventory_source(
                    key="standard_import",
                    label="普通导入",
                    count=_optional_int(row.get("standard_count")),
                    latest_synced_at=_isoformat(row.get("standard_latest_synced_at")),
                ),
                _inventory_source(
                    key="oa_attachment",
                    label="OA 解析",
                    count=_optional_int(oa_attachment.get("count")),
                    latest_synced_at=_isoformat(oa_attachment.get("latest_synced_at")),
                    status=str(oa_attachment.get("status") or "available"),
                ),
                _inventory_source(
                    key="etc",
                    label="ETC",
                    count=_optional_int(row.get("etc_count")),
                    latest_synced_at=_isoformat(row.get("etc_latest_synced_at")),
                ),
                _inventory_source(
                    key="manual",
                    label="手工导入",
                    count=_optional_int(row.get("manual_count")),
                    latest_synced_at=_isoformat(row.get("manual_latest_synced_at")),
                ),
            ],
        )

    def _oa_attachment_invoice_inventory(self, warnings: list[str]) -> dict[str, Any]:
        try:
            row = self._connection.fetch_one(
                """
                select
                  count(distinct row_id)::bigint as count,
                  max(generated_at) as latest_synced_at
                from read_model.workbench_rows
                where source_kind = 'oa_attachment_invoice'
                """
            ) or {}
            return {
                "count": _optional_int(row.get("count")),
                "latest_synced_at": row.get("latest_synced_at"),
                "status": "available",
            }
        except Exception:
            pass
        try:
            row = self._connection.fetch_one(
                """
                select
                  coalesce(sum(jsonb_array_length(
                    case
                      when jsonb_typeof(invoices) = 'array' then invoices
                      else '[]'::jsonb
                    end
                  )), 0)::bigint as count,
                  max(parsed_at) as latest_synced_at
                from app.oa_attachment_invoice_cache
                """
            ) or {}
            return {
                "count": _optional_int(row.get("count")),
                "latest_synced_at": row.get("latest_synced_at"),
                "status": "available",
            }
        except Exception:
            warnings.append("invoice_oa_attachment_inventory_unknown")
            return {"count": None, "latest_synced_at": None, "status": "unknown"}

    def _oa_inventory(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              (select count(*)::bigint from app.oa_applications) as oa_records_count,
              (select count(*)::bigint from app.oa_application_items) as oa_items_count,
              (select max(synced_at) from app.oa_applications) as oa_records_latest_synced_at,
              coalesce(
                (select max(synced_at) from app.oa_applications),
                (select max(last_success_at) from app.oa_sync_watermarks),
                (select max(finished_at) from app.oa_sync_runs where status in ('success', 'succeeded', 'done'))
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
                    latest_synced_at=_isoformat(row.get("oa_records_latest_synced_at") or row.get("oa_latest_synced_at")),
                ),
                _inventory_source(
                    key="oa_items",
                    label="明细",
                    count=_optional_int(row.get("oa_items_count")),
                    latest_synced_at=_isoformat(row.get("oa_latest_synced_at")),
                ),
            ],
        )

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

    def _runtime_rows(self, warning_code: str, warnings: list[str], loader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        try:
            rows = loader()
        except Exception:
            warnings.append(warning_code)
            return []
        for row in rows:
            warning = row.get("warning_code")
            if warning:
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
    status: str = "available",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "count": count,
        "latest_synced_at": latest_synced_at,
        "status": status if count is not None else "unknown",
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


def _max_timestamp(*values: object) -> str | None:
    normalized = [_isoformat(value) for value in values if _isoformat(value) is not None]
    return max(normalized) if normalized else None
