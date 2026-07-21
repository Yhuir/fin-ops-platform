from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

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
