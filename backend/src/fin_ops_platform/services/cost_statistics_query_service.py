from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from fin_ops_platform.services.cost_statistics_read_model_service import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.read_model_query_gateway import (
    ReadModelQueryGateway,
    ReadModelRefreshQueueAdapter,
)


class CostStatisticsQueryService:
    def __init__(
        self,
        *,
        cost_statistics_service: Any,
        runtime_service: Any,
        read_model_service: Any | None = None,
        redis_helper: Any | None = None,
        sql_read_repository: Any | None = None,
        requires_sql_read_model_runtime: Callable[[], bool] | None = None,
        persist_read_models: Callable[..., None] | None = None,
    ) -> None:
        self._cost_statistics_service = cost_statistics_service
        self._runtime_service = runtime_service
        self._read_model_service = read_model_service
        self._sql_read_repository = sql_read_repository
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime or (lambda: False)
        self._persist_read_models = persist_read_models
        self._read_model_query_gateway = ReadModelQueryGateway(
            queue_repository=ReadModelRefreshQueueAdapter(
                scope_type="cost_statistics",
                refresh_enqueuer=self._runtime_service.enqueue_read_model_refresh,
            ),
            redis_helper=redis_helper,
        )

    def get_month_statistics(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        sql_result = self.get_month_from_sql_read_model(month, normalized_project_scope)
        if sql_result is not None:
            return sql_result
        payload = self._cost_statistics_service.get_month_statistics(
            month,
            project_scope=normalized_project_scope,
        )
        return payload, False

    def get_explorer(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        sql_result = self.get_explorer_from_sql_read_model(month, normalized_project_scope)
        if sql_result is not None:
            return sql_result
        if self._requires_sql_read_model_runtime():
            scope_key = self._runtime_service.request_scope_key(month, normalized_project_scope)
            self._runtime_service.enqueue_read_model_refresh(scope_key, reason="api_sql_repository_unavailable")
            payload = self.empty_explorer_payload(month)
            payload["error"] = "read_model_unavailable"
            payload["read_model_status"] = "refreshing"
            payload["read_model_scope_key"] = scope_key
            return payload, False

        read_model_service = self._read_model_service
        if read_model_service is not None:
            cached_read_model = read_model_service.get_read_model(month, normalized_project_scope)
            if isinstance(cached_read_model, dict):
                cached_payload = cached_read_model.get("payload")
                if isinstance(cached_payload, dict):
                    return cached_payload, True

        if month == "all":
            self._runtime_service.schedule_cache_warmup(["all"], reason="explorer_all_cache_miss")
            return self.empty_explorer_payload(month), False

        payload = self._cost_statistics_service.get_explorer(
            month,
            project_scope=normalized_project_scope,
        )
        if read_model_service is not None:
            read_model = read_model_service.upsert_read_model(
                month,
                normalized_project_scope,
                payload,
                generated_at=datetime.now().isoformat(),
                source_scope_keys=[month],
                cache_status="ready",
            )
            scope_key = self._runtime_service.read_model_scope_key(
                month,
                normalized_project_scope,
                read_model=read_model,
            )
            if self._persist_read_models is not None:
                self._persist_read_models(
                    snapshot=read_model_service.snapshot_scope_keys([scope_key]),
                    changed_scope_keys=[scope_key],
                    operation="upsert_cost_statistics_explorer_read_model",
                )
        return payload, False

    def get_explorer_from_sql_read_model(
        self,
        month: str,
        project_scope: str,
    ) -> tuple[dict[str, Any], bool] | None:
        get_view = getattr(self._sql_read_repository, "get_cost_statistics_view", None)
        if not callable(get_view):
            return None
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        expected_source_versions = self._runtime_service.expected_source_versions(scope_key)
        cache_key = self._runtime_service.redis_cache_key(scope_key, source_versions=expected_source_versions)
        result = self._read_model_query_gateway.load(
            scope_type="cost_statistics",
            scope_key=scope_key,
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            empty_payload_factory=lambda: self.empty_explorer_payload(month),
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_miss",
            stale_reason="api_stale",
            source_mismatch_reason="api_source_versions_stale",
        )
        return result.payload, result.cache_hit

    def get_month_from_sql_read_model(
        self,
        month: str,
        project_scope: str,
    ) -> tuple[dict[str, Any], bool] | None:
        get_view = getattr(self._sql_read_repository, "get_cost_statistics_view", None)
        if not callable(get_view):
            return None
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        expected_source_versions = self._runtime_service.expected_source_versions(scope_key)
        cache_key = self._runtime_service.month_redis_cache_key(scope_key, source_versions=expected_source_versions)
        result = self._read_model_query_gateway.load(
            scope_type="cost_statistics",
            scope_key=scope_key,
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            empty_payload_factory=lambda: self.empty_month_payload(month),
            payload_from_view=lambda view: self.month_payload_from_explorer_payload(
                month,
                view.get("payload") if isinstance(view.get("payload"), dict) else {},
            ),
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_month_miss",
            stale_reason="api_month_stale",
            source_mismatch_reason="api_month_source_versions_stale",
        )
        return result.payload, result.cache_hit

    @staticmethod
    def month_payload_from_explorer_payload(
        month: str,
        explorer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        time_rows = explorer_payload.get("time_rows")
        if not isinstance(time_rows, list):
            time_rows = []
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        transaction_ids: set[str] = set()
        total_amount = Decimal("0.00")
        for raw_row in time_rows:
            if not isinstance(raw_row, dict):
                continue
            amount = _decimal_from_value(raw_row.get("amount")) or Decimal("0.00")
            transaction_id = str(raw_row.get("transaction_id") or "").strip()
            if transaction_id:
                transaction_ids.add(transaction_id)
            total_amount += amount
            key = (
                str(raw_row.get("project_name") or "").strip(),
                str(raw_row.get("expense_type") or "").strip(),
                str(raw_row.get("expense_content") or "").strip(),
            )
            bucket = grouped.setdefault(
                key,
                {
                    "project_name": key[0],
                    "expense_type": key[1],
                    "expense_content": key[2],
                    "amount_decimal": Decimal("0.00"),
                    "transaction_count": 0,
                    "sample_transaction_ids": [],
                },
            )
            bucket["amount_decimal"] = bucket["amount_decimal"] + amount
            bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
            samples = bucket["sample_transaction_ids"]
            if transaction_id and isinstance(samples, list) and transaction_id not in samples:
                samples.append(transaction_id)

        rows = []
        for bucket in sorted(grouped.values(), key=lambda item: (item["project_name"], item["expense_type"], item["expense_content"])):
            rows.append(
                {
                    "project_name": bucket["project_name"],
                    "expense_type": bucket["expense_type"],
                    "expense_content": bucket["expense_content"],
                    "amount": _plain_money(bucket["amount_decimal"]),
                    "transaction_count": bucket["transaction_count"],
                    "sample_transaction_ids": list(bucket["sample_transaction_ids"]),
                }
            )
        return {
            "month": month,
            "summary": {
                "row_count": len(rows),
                "transaction_count": len(transaction_ids) if transaction_ids else len(time_rows),
                "total_amount": _plain_money(total_amount),
            },
            "rows": rows,
        }

    @staticmethod
    def empty_explorer_payload(month: str) -> dict[str, Any]:
        return {
            "month": month,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "time_rows": [],
            "project_rows": [],
            "expense_type_rows": [],
        }

    @staticmethod
    def empty_month_payload(month: str) -> dict[str, Any]:
        return {
            "month": month,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "rows": [],
        }

    @staticmethod
    def explorer_entry_count(payload: dict[str, Any]) -> int:
        time_rows = payload.get("time_rows")
        if isinstance(time_rows, list):
            return len(time_rows)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            raw_count = summary.get("transaction_count", summary.get("row_count", 0))
            try:
                return int(raw_count)
            except (TypeError, ValueError):
                return 0
        return 0

    @staticmethod
    def _normalize_project_scope(project_scope: str) -> str:
        normalized_project_scope = str(project_scope or "active").strip().lower()
        if normalized_project_scope not in {"active", "all"}:
            raise ValueError("project_scope must be active or all")
        return normalized_project_scope


def _plain_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _decimal_from_value(value: object) -> Decimal | None:
    if value in (None, "", "--", "—"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None
