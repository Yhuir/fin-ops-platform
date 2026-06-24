from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fin_ops_platform.services.read_model_query_gateway import build_fresh_cache_envelope
from fin_ops_platform.services.tax_offset_read_model_service import TAX_OFFSET_READ_MODEL_SCHEMA_VERSION
from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService


class TaxOffsetWorkerRebuildExecutor:
    def __init__(
        self,
        *,
        runtime_service: TaxOffsetRuntimeService,
        read_model_service: Any,
        month_payload_loader: Callable[[str], dict[str, object]],
        persist_read_models: Callable[..., None],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._read_model_service = read_model_service
        self._month_payload_loader = month_payload_loader
        self._persist_read_models = persist_read_models
        self._clock = clock or datetime.now

    def rebuild_scope(self, scope_key: str) -> dict[str, object]:
        month = self._runtime_service.request_scope_key(scope_key)
        payload = self._load_month_payload(month)
        source_versions = self._runtime_service.expected_source_versions()
        read_model = self._read_model_service.upsert_read_model(
            month,
            payload,
            generated_at=self._clock().isoformat(),
            source_scope_keys=[month],
            source_versions=source_versions,
            cache_status="ready",
        )
        warmed_scope_key = self._runtime_service.read_model_scope_key(month, read_model=read_model)
        self._persist_read_models(
            snapshot=self._read_model_service.snapshot_scope_keys([warmed_scope_key]),
            changed_scope_keys=[warmed_scope_key],
            operation="worker_tax_offset_read_model_refresh",
        )
        self._publish_fresh_cache(
            scope_key=warmed_scope_key,
            payload=payload,
            source_versions=source_versions,
        )
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "entry_count": self._runtime_service.month_entry_count(payload),
        }

    def _load_month_payload(self, month: str) -> dict[str, object]:
        payload = self._month_payload_loader(month)
        if not isinstance(payload, dict):
            raise RuntimeError("Tax offset month payload loader must return a dict.")
        return dict(payload)

    def _publish_fresh_cache(
        self,
        *,
        scope_key: str,
        payload: dict[str, object],
        source_versions: dict[str, Any],
    ) -> None:
        cached_payload = dict(payload)
        cached_payload["read_model_status"] = "fresh"
        cached_payload["read_model_scope_key"] = scope_key
        cached_payload["source_versions"] = source_versions
        self._runtime_service.redis_set_json_best_effort(
            self._runtime_service.redis_cache_key(scope_key, source_versions=source_versions),
            build_fresh_cache_envelope(
                cached_payload,
                scope_key=scope_key,
                source_versions=source_versions,
                schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            ),
            ttl_seconds=self._runtime_service.redis_ttl_seconds(),
        )
        self._runtime_service.redis_set_json_best_effort(
            self._runtime_service.summary_redis_cache_key(scope_key, source_versions=source_versions),
            build_fresh_cache_envelope(
                self._runtime_service.summary_payload(cached_payload, scope_key=scope_key),
                scope_key=scope_key,
                source_versions=source_versions,
                schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            ),
            ttl_seconds=self._runtime_service.redis_ttl_seconds(),
        )
