from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_RELATION_MODE
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


DETERMINED_CANDIDATE_STATUSES = {"auto_closed", "incomplete"}


class BankDetailsRelationTagProjectionService:
    def __init__(
        self,
        *,
        pair_relation_service: WorkbenchPairRelationService,
        candidate_match_service: WorkbenchCandidateMatchService,
        workbench_read_model_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._pair_relation_service = pair_relation_service
        self._candidate_match_service = candidate_match_service
        self._workbench_read_model_provider = workbench_read_model_provider
        self._index_cache_key = ""
        self._index_cache: dict[str, dict[str, Any]] = {}

    def clear_cache(self) -> None:
        self._index_cache_key = ""
        self._index_cache = {}

    def relation_tag_for_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        resolved_transaction_id = str(transaction_id or "").strip()
        if not resolved_transaction_id:
            return None
        relation = self._relation_tag_index().get(resolved_transaction_id)
        return dict(relation) if isinstance(relation, dict) else None

    def relation_tags_for_transactions(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [
            str(transaction_id).strip()
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id).strip()
        ]
        if not normalized_ids:
            return {}
        index = self._relation_tag_index()
        return {
            transaction_id: dict(relation)
            for transaction_id in normalized_ids
            if isinstance(relation := index.get(transaction_id), dict)
        }

    def _relation_tag_index(self) -> dict[str, dict[str, Any]]:
        read_model = self._workbench_read_model()
        pair_relation_snapshot = self._pair_relation_service.snapshot()
        candidate_snapshot = self._candidate_match_service.snapshot()
        cache_key = WorkbenchReadModelService.snapshot_version(
            {
                "read_model": {
                    "scope_key": read_model.get("scope_key"),
                    "generated_at": read_model.get("generated_at"),
                    "source_versions": read_model.get("source_versions"),
                },
                "pair_relations": pair_relation_snapshot,
                "candidate_matches": candidate_snapshot,
            }
        )
        if cache_key == self._index_cache_key:
            return self._index_cache

        index: dict[str, dict[str, Any]] = {}
        no_oa_locked_row_ids: set[str] = set()

        for relation in self._pair_relation_service.list_active_relations():
            if not isinstance(relation, dict):
                continue
            row_ids = self._normalized_ids(relation.get("row_ids"))
            row_types = self._normalized_texts(relation.get("row_types"))
            case_id = str(relation.get("case_id") or "").strip()
            relation_mode = str(relation.get("relation_mode") or "").strip()
            if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
                no_oa_locked_row_ids.update(row_ids)
            for row_id in row_ids:
                self._merge_index_entry(
                    index,
                    row_id=row_id,
                    row_types=row_types,
                    case_id=case_id,
                    replace=True,
                )

        self._merge_candidate_relation_tags(
            index,
            candidate_snapshot=candidate_snapshot,
            locked_row_ids=no_oa_locked_row_ids,
        )
        payload = read_model.get("payload")
        if isinstance(payload, dict):
            self._merge_grouped_relation_tags(
                index,
                payload,
                locked_row_ids=no_oa_locked_row_ids,
            )

        self._index_cache_key = cache_key
        self._index_cache = index
        return index

    def _workbench_read_model(self) -> dict[str, Any]:
        if self._workbench_read_model_provider is None:
            return {}
        try:
            read_model = self._workbench_read_model_provider()
        except Exception:
            return {}
        return read_model if isinstance(read_model, dict) else {}

    def _merge_candidate_relation_tags(
        self,
        index: dict[str, dict[str, Any]],
        *,
        candidate_snapshot: dict[str, Any],
        locked_row_ids: set[str],
    ) -> None:
        candidates_payload = candidate_snapshot.get("candidates")
        candidates = list(candidates_payload.values()) if isinstance(candidates_payload, dict) else []
        claimed_row_ids: set[str] = set()
        for candidate in sorted(
            (candidate for candidate in candidates if isinstance(candidate, dict)),
            key=self._candidate_display_sort_key,
        ):
            if not isinstance(candidate, dict) or not self._candidate_is_determined(candidate):
                continue
            bank_row_ids = set(self._normalized_ids(candidate.get("bank_row_ids")))
            if not bank_row_ids and "bank" in str(candidate.get("candidate_type") or "").strip():
                bank_row_ids = set(self._normalized_ids(candidate.get("row_ids")))
            if not bank_row_ids:
                continue

            row_types = {"bank"}
            if self._normalized_ids(candidate.get("oa_row_ids")):
                row_types.add("oa")
            if self._normalized_ids(candidate.get("invoice_row_ids")):
                row_types.add("invoice")
            if len(row_types) <= 1:
                continue

            case_id = str(candidate.get("candidate_key") or candidate.get("candidate_id") or "").strip()
            row_ids = set(self._candidate_row_ids(candidate)) or set(bank_row_ids)
            if any(row_id in claimed_row_ids for row_id in row_ids):
                continue
            for bank_row_id in bank_row_ids:
                if bank_row_id in locked_row_ids:
                    continue
                self._merge_index_entry(
                    index,
                    row_id=bank_row_id,
                    row_types=row_types,
                    case_id=case_id,
                )
            claimed_row_ids.update(row_ids)

    def _merge_grouped_relation_tags(
        self,
        index: dict[str, dict[str, Any]],
        payload: dict[str, Any],
        *,
        locked_row_ids: set[str],
    ) -> None:
        for section_name in ("paired", "open"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            section_groups = section.get("groups")
            groups = list(section_groups) if isinstance(section_groups, list) else [section]
            for group in groups:
                if not isinstance(group, dict):
                    continue
                row_types = {
                    row_type
                    for row_type in ("oa", "bank", "invoice")
                    if any(isinstance(row, dict) for row in self._group_rows(group, row_type))
                }
                if "bank" not in row_types or len(row_types) <= 1:
                    continue
                group_case_id = self._group_case_id(group)
                for bank_row in self._group_rows(group, "bank"):
                    if not isinstance(bank_row, dict):
                        continue
                    bank_row_id = str(bank_row.get("id") or bank_row.get("row_id") or "").strip()
                    if not bank_row_id or bank_row_id in locked_row_ids:
                        continue
                    self._merge_index_entry(
                        index,
                        row_id=bank_row_id,
                        row_types=row_types,
                        case_id=str(bank_row.get("case_id") or "").strip() or group_case_id,
                    )

    @staticmethod
    def _group_rows(group: dict[str, Any], row_type: str) -> list[Any]:
        primary = group.get(f"{row_type}_rows")
        if isinstance(primary, list):
            return primary
        legacy = group.get(row_type)
        return legacy if isinstance(legacy, list) else []

    @staticmethod
    def _merge_index_entry(
        index: dict[str, dict[str, Any]],
        *,
        row_id: str,
        row_types: list[str] | set[str],
        case_id: str = "",
        replace: bool = False,
    ) -> None:
        resolved_row_id = str(row_id or "").strip()
        if not resolved_row_id:
            return
        normalized_row_types = {
            str(row_type).strip()
            for row_type in list(row_types or [])
            if str(row_type).strip()
        }
        if not normalized_row_types and not str(case_id or "").strip():
            return

        existing = {} if replace else dict(index.get(resolved_row_id) or {})
        existing_row_types = {
            str(row_type).strip()
            for row_type in list(existing.get("row_types") or [])
            if str(row_type).strip()
        }
        merged_row_types = normalized_row_types if replace else {*existing_row_types, *normalized_row_types}
        entry: dict[str, Any] = {"row_types": sorted(merged_row_types)}
        existing_case_id = str(existing.get("case_id") or "").strip()
        resolved_case_id = existing_case_id or str(case_id or "").strip()
        if resolved_case_id:
            entry["case_id"] = resolved_case_id
        index[resolved_row_id] = entry

    @staticmethod
    def _group_case_id(group: dict[str, Any]) -> str:
        for key in ("oa_rows", "bank_rows", "invoice_rows", "oa", "bank", "invoice"):
            rows = group.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                case_id = str(row.get("case_id") or "").strip()
                if case_id:
                    return case_id
        group_id = str(group.get("group_id") or "").strip()
        if group_id.startswith("case:"):
            return group_id[len("case:") :]
        return group_id

    @staticmethod
    def _candidate_is_determined(candidate: dict[str, Any]) -> bool:
        return str(candidate.get("status") or "").strip() in DETERMINED_CANDIDATE_STATUSES

    @classmethod
    def _candidate_display_sort_key(cls, candidate: dict[str, Any]) -> tuple[int, int, int, str, str]:
        rule_code = str(candidate.get("rule_code") or "")
        row_count = cls._candidate_row_count(candidate)
        status_priority = {
            "auto_closed": 0,
            "conflict": 1,
            "incomplete": 2,
            "needs_review": 3,
        }
        status_rank = status_priority.get(str(candidate.get("status") or ""), 9)
        has_special_metadata = bool(candidate.get("special_metadata"))
        if rule_code == "no_confident_match":
            quality_rank = 9
        elif status_rank <= 1:
            quality_rank = status_rank
        elif row_count > 1:
            quality_rank = 2
        elif has_special_metadata:
            quality_rank = 3
        else:
            quality_rank = 4
        return (
            quality_rank,
            -row_count,
            status_rank,
            rule_code,
            str(candidate.get("candidate_key") or candidate.get("candidate_id") or ""),
        )

    @classmethod
    def _candidate_row_count(cls, candidate: dict[str, Any]) -> int:
        return len(cls._candidate_row_ids(candidate))

    @classmethod
    def _candidate_row_ids(cls, candidate: dict[str, Any]) -> list[str]:
        row_ids = cls._normalized_ids(candidate.get("row_ids"))
        if row_ids:
            return row_ids
        merged: list[str] = []
        for field_name in ("oa_row_ids", "bank_row_ids", "invoice_row_ids"):
            for row_id in cls._normalized_ids(candidate.get(field_name)):
                if row_id not in merged:
                    merged.append(row_id)
        return merged

    @staticmethod
    def _normalized_ids(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            resolved_value = str(value or "").strip()
            if resolved_value and resolved_value not in normalized:
                normalized.append(resolved_value)
        return normalized

    @staticmethod
    def _normalized_texts(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            resolved_value = str(value or "").strip()
            if resolved_value and resolved_value not in normalized:
                normalized.append(resolved_value)
        return normalized
