from __future__ import annotations

from typing import Callable


class WorkbenchCacheReadPayloadHelper:
    """Evaluates Workbench cached/read payload readiness through explicit ports."""

    def __init__(
        self,
        *,
        is_mongo_oa_adapter: Callable[[], bool],
        cached_payload_needs_oa_invoice_offset_rebuild: Callable[[dict[str, object]], bool],
        workbench_candidate_snapshot_hash: Callable[[str], str],
        current_oa_attachment_invoice_parser_version: Callable[[], str],
        workbench_read_model_schema_version: str,
        candidate_match_schema_version: str,
        workbench_matching_rules_version: str,
    ) -> None:
        self._is_mongo_oa_adapter = is_mongo_oa_adapter
        self._cached_payload_needs_oa_invoice_offset_rebuild = cached_payload_needs_oa_invoice_offset_rebuild
        self._workbench_candidate_snapshot_hash = workbench_candidate_snapshot_hash
        self._current_oa_attachment_invoice_parser_version = current_oa_attachment_invoice_parser_version
        self._workbench_read_model_schema_version = workbench_read_model_schema_version
        self._candidate_match_schema_version = candidate_match_schema_version
        self._workbench_matching_rules_version = workbench_matching_rules_version

    def can_use_cached_payload(self, payload: dict[str, object]) -> bool:
        if not self.oa_status_is_ready_for_cache(payload):
            return False
        if self._cached_payload_needs_oa_invoice_offset_rebuild(payload):
            return False
        if self._payload_has_visible_legacy_candidate_group(payload):
            return False
        cached_candidate_hash = str(payload.get("workbench_candidate_snapshot_hash") or "").strip()
        if cached_candidate_hash:
            expected_candidate_hash = self._workbench_candidate_snapshot_hash(
                str(payload.get("month") or "all")
            )
            if cached_candidate_hash != expected_candidate_hash:
                return False
        if self._is_mongo_oa_adapter():
            cached_schema_version = str(payload.get("workbench_read_model_schema_version") or "").strip()
            if cached_schema_version != self._workbench_read_model_schema_version:
                return False
            cached_candidate_schema_version = str(
                payload.get("workbench_candidate_match_schema_version") or ""
            ).strip()
            if cached_candidate_schema_version != self._candidate_match_schema_version:
                return False
            cached_rules_version = str(payload.get("workbench_matching_rules_version") or "").strip()
            if cached_rules_version != self._workbench_matching_rules_version:
                return False
            expected_parser_version = self._current_oa_attachment_invoice_parser_version()
            cached_parser_version = str(payload.get("oa_attachment_invoice_parser_version") or "").strip()
            if expected_parser_version and cached_parser_version != expected_parser_version:
                return False
            expected_candidate_hash = self._workbench_candidate_snapshot_hash(
                str(payload.get("month") or "all")
            )
            cached_candidate_hash = str(payload.get("workbench_candidate_snapshot_hash") or "").strip()
            if cached_candidate_hash != expected_candidate_hash:
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

    @classmethod
    def _payload_has_visible_legacy_candidate_group(cls, payload: dict[str, object]) -> bool:
        for section_name in ("paired", "open"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            for group in list(section.get("groups") or []):
                if not isinstance(group, dict):
                    continue
                group_type = str(group.get("group_type") or "").strip()
                if group_type == "candidate":
                    return True
                if group_type != "auto_closed":
                    continue
                relation_mode = str(group.get("relation_mode") or "").strip()
                if relation_mode in {"bank_flow_rule_batch", "no_oa_bank_batch"}:
                    continue
                rows = cls._group_rows(group)
                if rows and all(cls._row_has_active_pair_relation_marker(row) for row in rows):
                    continue
                return True
        return False

    @staticmethod
    def _group_rows(group: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for key in ("oa_rows", "bank_rows", "invoice_rows"):
            rows.extend(row for row in list(group.get(key) or []) if isinstance(row, dict))
        return rows

    @staticmethod
    def _row_has_active_pair_relation_marker(row: dict[str, object]) -> bool:
        metadata = row.get("special_metadata")
        if not isinstance(metadata, dict):
            return False
        return (
            bool(metadata.get("active_pair_relation"))
            or bool(str(metadata.get("active_relation_case_id") or "").strip())
        )
