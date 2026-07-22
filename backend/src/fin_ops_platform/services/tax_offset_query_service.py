from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_query_gateway import (
    ReadModelQueryGateway,
    ReadModelRedisBestEffortAdapter,
    ReadModelRefreshQueueAdapter,
)
from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
)


class TaxOffsetQueryService:
    def __init__(
        self,
        *,
        tax_offset_service: Any | None,
        runtime_service: Any,
        sql_read_repository: Any | None = None,
        requires_sql_read_model_runtime: Callable[[], bool] | None = None,
    ) -> None:
        self._tax_offset_service = tax_offset_service
        self._runtime_service = runtime_service
        self._sql_read_repository = sql_read_repository
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime or (lambda: False)
        self._read_model_query_gateway = ReadModelQueryGateway(
            queue_repository=ReadModelRefreshQueueAdapter(
                scope_type="tax_offset",
                refresh_enqueuer=self._runtime_service.enqueue_read_model_refresh,
            ),
            redis_helper=ReadModelRedisBestEffortAdapter(
                get_json=self._runtime_service.redis_get_json_best_effort,
                set_json=self._runtime_service.redis_set_json_best_effort,
            ),
        )

    def get_month_payload(self, month: str) -> tuple[dict[str, Any], bool]:
        sql_result = self.get_month_from_sql_read_model(month)
        if sql_result is not None:
            return sql_result
        if self._requires_sql_read_model_runtime():
            scope_key = self._runtime_service.request_scope_key(month)
            self._runtime_service.enqueue_read_model_refresh(scope_key, reason="api_sql_repository_unavailable")
            payload = self._runtime_service.empty_month_payload(month)
            payload["error"] = "read_model_unavailable"
            payload["read_model_status"] = "refreshing"
            payload["read_model_scope_key"] = scope_key
            return payload, False

        cached_payload = self._runtime_service.get_legacy_cached_payload(month)
        if cached_payload is not None:
            return cached_payload, True

        if self._tax_offset_service is None:
            raise RuntimeError("Tax offset service is not configured.")
        payload = self._tax_offset_service.get_month_payload(month)
        self._runtime_service.upsert_legacy_read_model(
            month,
            payload,
            operation="upsert_tax_offset_read_model",
        )
        return payload, False

    def calculate(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        if self._requires_sql_read_model_runtime():
            month = self._runtime_service.request_scope_key(str(payload["month"]))
            month_payload, _cache_hit = self.get_month_payload(month)
            read_model_status = str(month_payload.get("read_model_status") or "fresh")
            if read_model_status != "fresh":
                result = {
                    "month": month,
                    "summary": month_payload.get("summary")
                    if isinstance(month_payload.get("summary"), dict)
                    else self._runtime_service.empty_month_payload(month)["summary"],
                    "read_model_status": "refreshing" if read_model_status in {"missing", "stale"} else read_model_status,
                    "read_model_scope_key": month_payload.get("read_model_scope_key") or month,
                }
                return result, 202
            return (
                self._require_tax_offset_service().calculate_from_month_payload(
                    month=str(payload["month"]),
                    month_payload=month_payload,
                    selected_output_ids=list(payload["selected_output_ids"]),
                    selected_input_ids=list(payload["selected_input_ids"]),
                ),
                200,
            )
        return (
            self._require_tax_offset_service().calculate(
                month=str(payload["month"]),
                selected_output_ids=list(payload["selected_output_ids"]),
                selected_input_ids=list(payload["selected_input_ids"]),
            ),
            200,
        )

    def _require_tax_offset_service(self) -> Any:
        if self._tax_offset_service is None:
            raise RuntimeError("Tax offset service is not configured.")
        return self._tax_offset_service

    def get_month_from_sql_read_model(self, month: str) -> tuple[dict[str, Any], bool] | None:
        get_view = getattr(self._sql_read_repository, "get_tax_offset_view", None)
        if not callable(get_view):
            return None
        scope_key = self._runtime_service.request_scope_key(month)
        expected_source_versions = self._runtime_service.expected_source_versions()
        statistics_generation_token = self._statistics_generation_token()
        cache_key = (
            self._runtime_service.redis_cache_key(
                scope_key,
                source_versions=expected_source_versions,
                statistics_generation_token=statistics_generation_token,
            )
            if statistics_generation_token
            else None
        )
        result = self._read_model_query_gateway.load(
            scope_type="tax_offset",
            scope_key=scope_key,
            expected_schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            load_freshness_view=lambda: {
                "payload": {},
                "source_versions": expected_source_versions,
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "refresh_status": "fresh",
            },
            empty_payload_factory=lambda: self._runtime_service.empty_month_payload(month),
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_miss",
            stale_reason="api_stale",
            source_mismatch_reason="api_source_versions_stale",
        )
        self._gate_statistics(result.payload)
        return result.payload, result.cache_hit

    def get_summary_payload(self, month: str) -> tuple[dict[str, Any], bool]:
        scope_key = self._runtime_service.request_scope_key(month)
        expected_source_versions = self._runtime_service.expected_source_versions()
        statistics_generation_token = self._statistics_generation_token()
        cache_key = (
            self._runtime_service.summary_redis_cache_key(
                scope_key,
                source_versions=expected_source_versions,
                statistics_generation_token=statistics_generation_token,
            )
            if statistics_generation_token
            else None
        )
        get_view = getattr(self._sql_read_repository, "get_tax_offset_view", None)
        if not callable(get_view):
            full_payload, cache_hit = self.get_month_payload(month)
            return self._runtime_service.summary_payload(full_payload, scope_key=scope_key), cache_hit

        result = self._read_model_query_gateway.load(
            scope_type="tax_offset",
            scope_key=scope_key,
            expected_schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            load_freshness_view=lambda: {
                "payload": {},
                "source_versions": expected_source_versions,
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "refresh_status": "fresh",
            },
            empty_payload_factory=lambda: self._runtime_service.summary_payload(
                self._runtime_service.empty_month_payload(month),
                scope_key=scope_key,
            ),
            payload_from_view=lambda view: self._runtime_service.summary_payload(
                dict(view.get("payload") if isinstance(view.get("payload"), dict) else {}),
                scope_key=scope_key,
            ),
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_summary_miss",
            stale_reason="api_summary_stale",
            source_mismatch_reason="api_summary_source_versions_stale",
        )
        self._gate_statistics(result.payload)
        return result.payload, result.cache_hit

    def _statistics_generation_token(self) -> str | None:
        loader = getattr(self._sql_read_repository, "tax_offset_statistics_generation_token", None)
        value = loader() if callable(loader) else None
        return str(value) if value not in (None, "") else None

    def _gate_statistics(self, payload: dict[str, Any]) -> None:
        if "statistics_status" not in payload:
            return
        status = str(payload.get("statistics_status") or "stale").strip().lower()
        if status == "fresh" and isinstance(payload.get("statistics"), dict):
            return
        payload["statistics"] = None
        payload["statistics_status"] = "refreshing"
        payload["statistics_refresh_enqueued"] = self._runtime_service.enqueue_read_model_refresh(
            "all",
            reason=f"api_statistics_{status}",
        )
