from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons


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
        cache_key = self._runtime_service.redis_cache_key(scope_key, source_versions=expected_source_versions)
        cached = self._runtime_service.redis_get_json_best_effort(cache_key)
        if isinstance(cached, dict):
            cached_payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else cached
            payload = dict(cached_payload)
            payload["read_model_status"] = "fresh"
            payload["read_model_scope_key"] = scope_key
            return payload, True

        view = get_view(scope_key=scope_key)
        if not isinstance(view, dict):
            self._runtime_service.enqueue_read_model_refresh(scope_key, reason="api_miss")
            payload = self._runtime_service.empty_month_payload(month)
            payload["read_model_status"] = "refreshing"
            payload["read_model_scope_key"] = scope_key
            return payload, False

        payload = dict(view.get("payload") if isinstance(view.get("payload"), dict) else {})
        refresh_status, stale_reasons = self._read_model_refresh_status(view, expected_source_versions)
        if refresh_status != "fresh":
            self._runtime_service.enqueue_read_model_refresh(
                scope_key,
                reason="api_source_versions_stale" if stale_reasons else "api_stale",
            )
        self._attach_read_model_metadata(
            payload,
            view=view,
            scope_key=scope_key,
            refresh_status=refresh_status,
            stale_reasons=stale_reasons,
        )
        if refresh_status == "fresh":
            self._runtime_service.redis_set_json_best_effort(
                cache_key,
                {"payload": payload},
                ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            )
        return payload, False

    def get_summary_payload(self, month: str) -> tuple[dict[str, Any], bool]:
        scope_key = self._runtime_service.request_scope_key(month)
        expected_source_versions = self._runtime_service.expected_source_versions()
        cache_key = self._runtime_service.summary_redis_cache_key(scope_key, source_versions=expected_source_versions)
        cached = self._runtime_service.redis_get_json_best_effort(cache_key)
        if isinstance(cached, dict):
            cached_payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else cached
            payload = dict(cached_payload)
            payload["read_model_status"] = "fresh"
            payload["read_model_scope_key"] = scope_key
            return payload, True

        get_view = getattr(self._sql_read_repository, "get_tax_offset_view", None)
        if not callable(get_view):
            full_payload, cache_hit = self.get_month_payload(month)
            return self._runtime_service.summary_payload(full_payload, scope_key=scope_key), cache_hit

        view = get_view(scope_key=scope_key)
        if not isinstance(view, dict):
            self._runtime_service.enqueue_read_model_refresh(scope_key, reason="api_summary_miss")
            payload = self._runtime_service.summary_payload(
                self._runtime_service.empty_month_payload(month),
                scope_key=scope_key,
            )
            payload["read_model_status"] = "refreshing"
            return payload, False

        full_payload = dict(view.get("payload") if isinstance(view.get("payload"), dict) else {})
        payload = self._runtime_service.summary_payload(full_payload, scope_key=scope_key)
        refresh_status, stale_reasons = self._read_model_refresh_status(view, expected_source_versions)
        if refresh_status != "fresh":
            self._runtime_service.enqueue_read_model_refresh(
                scope_key,
                reason="api_summary_source_versions_stale" if stale_reasons else "api_summary_stale",
            )
        payload["read_model_status"] = refresh_status
        payload["source_versions"] = view.get("source_versions") if isinstance(view.get("source_versions"), dict) else {}
        if stale_reasons:
            payload["read_model_stale_reasons"] = stale_reasons
        if view.get("generated_at"):
            payload["read_model_generated_at"] = view.get("generated_at")
        if view.get("schema_version"):
            payload["read_model_schema_version"] = view.get("schema_version")
        if refresh_status == "fresh":
            self._runtime_service.redis_set_json_best_effort(
                cache_key,
                {"payload": payload},
                ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            )
        return payload, False

    @staticmethod
    def _read_model_refresh_status(
        view: dict[str, Any],
        expected_source_versions: dict[str, Any],
    ) -> tuple[str, list[str]]:
        refresh_status = str(view.get("refresh_status") or "fresh")
        stale_reasons = source_version_mismatch_reasons(
            expected=expected_source_versions,
            actual=view.get("source_versions") if isinstance(view.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            refresh_status = "stale"
        return refresh_status, stale_reasons

    @staticmethod
    def _attach_read_model_metadata(
        payload: dict[str, Any],
        *,
        view: dict[str, Any],
        scope_key: str,
        refresh_status: str,
        stale_reasons: list[str],
    ) -> None:
        payload["read_model_status"] = refresh_status
        payload["read_model_scope_key"] = scope_key
        payload["source_versions"] = view.get("source_versions") if isinstance(view.get("source_versions"), dict) else {}
        if stale_reasons:
            payload["read_model_stale_reasons"] = stale_reasons
        if view.get("generated_at"):
            payload["read_model_generated_at"] = view.get("generated_at")
        if view.get("schema_version"):
            payload["read_model_schema_version"] = view.get("schema_version")
