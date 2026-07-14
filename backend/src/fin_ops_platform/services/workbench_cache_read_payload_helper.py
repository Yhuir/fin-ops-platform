from __future__ import annotations

from typing import Callable


class WorkbenchCacheReadPayloadHelper:
    """Evaluates Workbench cached/read payload readiness through explicit ports."""

    def __init__(
        self,
        *,
        is_mongo_oa_adapter: Callable[[], bool],
        cached_payload_needs_oa_invoice_offset_rebuild: Callable[[dict[str, object]], bool],
        current_oa_attachment_invoice_parser_version: Callable[[], str],
        workbench_read_model_schema_version: str,
    ) -> None:
        self._is_mongo_oa_adapter = is_mongo_oa_adapter
        self._cached_payload_needs_oa_invoice_offset_rebuild = cached_payload_needs_oa_invoice_offset_rebuild
        self._current_oa_attachment_invoice_parser_version = current_oa_attachment_invoice_parser_version
        self._workbench_read_model_schema_version = workbench_read_model_schema_version

    def can_use_cached_payload(self, payload: dict[str, object]) -> bool:
        if not self.oa_status_is_ready_for_cache(payload):
            return False
        if self._cached_payload_needs_oa_invoice_offset_rebuild(payload):
            return False
        if self._is_mongo_oa_adapter():
            cached_schema_version = str(payload.get("workbench_read_model_schema_version") or "").strip()
            if cached_schema_version != self._workbench_read_model_schema_version:
                return False
            expected_parser_version = self._current_oa_attachment_invoice_parser_version()
            cached_parser_version = str(payload.get("oa_attachment_invoice_parser_version") or "").strip()
            if expected_parser_version and cached_parser_version != expected_parser_version:
                return False
            summary = payload.get("summary")
            if isinstance(summary, dict):
                try:
                    return int(summary.get("oa_count", 0) or 0) > 0
                except (TypeError, ValueError):
                    return False
        return True

    def can_persist_payload(self, payload: dict[str, object]) -> bool:
        return self.oa_status_is_ready_for_cache(payload)

    def can_fallback_to_stale_payload(self, payload: dict[str, object]) -> bool:
        return self.oa_status_is_ready_for_cache(payload)

    def oa_status_is_ready_for_cache(self, payload: dict[str, object]) -> bool:
        oa_status = payload.get("oa_status")
        if self._is_mongo_oa_adapter():
            return isinstance(oa_status, dict) and str(oa_status.get("code", "")).strip() == "ready"
        return not isinstance(oa_status, dict) or str(oa_status.get("code", "")).strip() == "ready"
