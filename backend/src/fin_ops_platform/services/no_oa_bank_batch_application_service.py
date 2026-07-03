from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Callable

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_turnover_tag_semantics import (
    EXTERNAL_TURNOVER_CATEGORY_CODE,
    EXTERNAL_TURNOVER_ROLE,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_TRANSACTION_CATEGORY_LABELS,
    BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
    BankTransactionCategoryService,
)
from fin_ops_platform.services.no_oa_bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_SCHEMA_VERSION,
    NoOaBankBatchService,
)
from fin_ops_platform.services.no_oa_bank_batch_read_model_repository import NoOaBankBatchReadModelRepositoryPort
from fin_ops_platform.services.no_oa_managed_rule_policy import NO_OA_MANAGED_LABELS
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.read_model_write_targets import write_target_envelope
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_distribution_mapper import relation_dicts_from_distribution_payload
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
TURNOVER_RULE_REQUIREMENT_SOURCE = "no_oa_bank_batch_tag_selection"
TURNOVER_RULE_CATEGORY_ROOTS = frozenset({"借入", "借出", "业务往来"})


class NoOaBankBatchPersistenceError(RuntimeError):
    error_code = "no_oa_bank_batch_persistence_failed"


class NoOaBankBatchRelationMutationError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.payload = dict(payload or {})


class NoOaPairRelationSnapshotPort:
    def __init__(self, pair_relation_service: Any) -> None:
        self._pair_relation_service = pair_relation_service

    def snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self._pair_relation_service, "snapshot", None)
        return deepcopy(snapshot() or {}) if callable(snapshot) else {}

    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, Any]:
        snapshot_case_ids = getattr(self._pair_relation_service, "snapshot_case_ids", None)
        if callable(snapshot_case_ids):
            return deepcopy(snapshot_case_ids(case_ids) or {})
        return self.snapshot()

    def snapshot_version(self) -> str:
        return WorkbenchReadModelService.snapshot_version(self.snapshot())

    def snapshot_by_case_id(self, case_id: str) -> dict[str, object] | None:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            return None
        pair_relations = self.snapshot().get("pair_relations", {})
        relation = pair_relations.get(normalized_case_id) if isinstance(pair_relations, dict) else None
        return dict(relation) if isinstance(relation, dict) else None

    def restore(self, relation_snapshot: dict[str, Any]) -> None:
        restored_relation_service = WorkbenchPairRelationService.from_snapshot(relation_snapshot)
        if hasattr(self._pair_relation_service, "_pair_relations"):
            self._pair_relation_service._pair_relations = deepcopy(restored_relation_service._pair_relations)
        if hasattr(self._pair_relation_service, "_pair_relation_history"):
            self._pair_relation_service._pair_relation_history = deepcopy(restored_relation_service._pair_relation_history)


def _stable_dependency_source_versions(source_versions: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in dict(source_versions).items():
        if key in {"source_version", "workbench_relation_source_versions", "pair_relation_snapshot_version"}:
            continue
        if isinstance(value, dict):
            result[key] = _stable_dependency_source_versions(value)
        elif isinstance(value, list):
            result[key] = [
                _stable_dependency_source_versions(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class NoOaBankBatchApplicationService:
    def __init__(
        self,
        *,
        import_service: Any,
        effective_category_provider: Any,
        no_oa_bank_batch_service: NoOaBankBatchService,
        app_settings_service: AppSettingsService,
        bank_transaction_category_service: BankTransactionCategoryService,
        pair_relation_snapshot_port: NoOaPairRelationSnapshotPort,
        workbench_read_model_service: WorkbenchReadModelService,
        state_store: Any | None,
        tag_selection_service: Any | None = None,
        no_oa_bank_batch_read_model_repository: Any | None = None,
        workbench_sql_read_repository: Any | None = None,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        bank_transaction_category_affected_months_provider: Callable[[list[str]], list[str]] | None = None,
        execute_derived_data_lifecycle_event: Callable[..., Any] | None = None,
        expand_workbench_read_model_scope_keys_for_base_scopes: Callable[[list[str]], list[str]] | None = None,
        search_cache_clearer: Callable[[], Any] | None = None,
        queue_repository: Any | None = None,
        read_model_refresh_producer: Any | None = None,
        relation_facade: Any | None = None,
        relation_command_service: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._effective_category_provider = effective_category_provider
        self._no_oa_bank_batch_service = no_oa_bank_batch_service
        self._tag_selection_service = tag_selection_service
        self._app_settings_service = app_settings_service
        self._bank_transaction_category_service = bank_transaction_category_service
        self._pair_relation_snapshot_port = pair_relation_snapshot_port
        self._workbench_read_model_service = workbench_read_model_service
        self._state_store = state_store
        self._no_oa_bank_batch_read_model_repository = no_oa_bank_batch_read_model_repository
        if self._no_oa_bank_batch_read_model_repository is None and workbench_sql_read_repository is not None:
            self._no_oa_bank_batch_read_model_repository = NoOaBankBatchReadModelRepositoryPort(
                workbench_sql_read_repository
            )
        self._workbench_matching_source_versions_provider = workbench_matching_source_versions_provider or (lambda: {})
        self._bank_transaction_category_affected_months_provider = (
            bank_transaction_category_affected_months_provider or (lambda _row_ids: [])
        )
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event or (lambda *_args, **_kwargs: None)
        self._expand_workbench_read_model_scope_keys_for_base_scopes = (
            expand_workbench_read_model_scope_keys_for_base_scopes or (lambda scope_keys: scope_keys)
        )
        self._search_cache_clearer = search_cache_clearer or (lambda: None)
        self._queue_repository = queue_repository
        self._read_model_refresh_producer = read_model_refresh_producer
        self._relation_facade = relation_facade
        self._relation_command_service = relation_command_service

    def list_batches_payload(
        self,
        query: dict[str, list[str]],
        *,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> dict[str, object]:
        pagination = self._pagination_from_query(query)
        filters = {
            "month": query.get("month", [""])[0],
            "type": query.get("type", [""])[0],
            "status": query.get("status", [""])[0],
            "bucket": query.get("bucket", [""])[0],
            "account_key": query.get("account_key", [""])[0],
            "relation_mode": self._read_model_key_for_relation_mode(relation_mode),
        }
        summary_filters = {
            "month": filters["month"],
            "account_key": filters["account_key"],
            "relation_mode": filters["relation_mode"],
        }
        refresh_scope_keys = self._refresh_scope_keys_for_filters(filters)
        refresh_metadata = self._read_model_refresh_metadata_for_relation_mode(relation_mode)
        list_read_model_batches = getattr(
            self._no_oa_bank_batch_read_model_repository,
            self._read_model_list_method_for_relation_mode(relation_mode),
            None,
        )
        if callable(list_read_model_batches):
            summary_read_model_batches = list_read_model_batches(summary_filters)
            read_model_batches = list_read_model_batches(filters)
            if summary_read_model_batches is None or read_model_batches is None:
                refresh_reason = self._read_model_refresh_reason_for_relation_mode(
                    relation_mode,
                    fallback_reason="api_no_oa_read_model_missing",
                    bank_flow_reason="api_bank_flow_rule_batch_read_model_missing",
                )
                refresh_enqueued = self.enqueue_background_refresh(
                    refresh_scope_keys,
                    reason=refresh_reason,
                    metadata=refresh_metadata,
                )
                return {
                    "summary": self.summary([]),
                    "batches": [],
                    **self._pagination_payload([], pagination),
                    "read_model_status": "missing",
                    "read_model_stale_reasons": [],
                    "refresh_enqueued": refresh_enqueued,
                    "refresh_reason": refresh_reason,
                }
            if summary_read_model_batches is not None and read_model_batches is not None:
                self.load_relation_source_versions_for_scope_keys(refresh_scope_keys)
                stale_reasons = self.no_oa_bank_batch_stale_reasons(summary_read_model_batches + read_model_batches)
                summary_public_batches = self._public_batches(summary_read_model_batches)
                read_model_public_batches = self._public_batches(read_model_batches)
                if stale_reasons:
                    refresh_reason = self._read_model_refresh_reason_for_relation_mode(
                        relation_mode,
                        fallback_reason="api_no_oa_source_versions_stale",
                        bank_flow_reason="api_bank_flow_rule_batch_source_versions_stale",
                    )
                    refresh_enqueued = self.enqueue_background_refresh(
                        refresh_scope_keys,
                        reason=refresh_reason,
                        metadata=refresh_metadata,
                    )
                    return {
                        "summary": self.summary(summary_public_batches),
                        "batches": self.resolve_labels(self._page_items(read_model_public_batches, pagination)),
                        **self._pagination_payload(read_model_public_batches, pagination),
                        "read_model_status": "stale",
                        "read_model_stale_reasons": stale_reasons,
                        "refresh_enqueued": refresh_enqueued,
                        "refresh_reason": refresh_reason,
                    }
                return {
                    "summary": self.summary(summary_public_batches),
                    "batches": self.resolve_labels(self._page_items(read_model_public_batches, pagination)),
                    **self._pagination_payload(read_model_public_batches, pagination),
                    "read_model_status": "fresh",
                }
        refresh_reason = self._read_model_refresh_reason_for_relation_mode(
            relation_mode,
            fallback_reason="api_no_oa_read_model_unavailable",
            bank_flow_reason="api_bank_flow_rule_batch_read_model_unavailable",
        )
        refresh_enqueued = self.enqueue_background_refresh(
            refresh_scope_keys,
            reason=refresh_reason,
            metadata=refresh_metadata,
        )
        return {
            "summary": self.summary([]),
            "batches": [],
            **self._pagination_payload([], pagination),
            "read_model_status": "unavailable",
            "read_model_stale_reasons": [],
            "refresh_enqueued": refresh_enqueued,
            "refresh_reason": refresh_reason,
        }

    def tag_selection_payload(self) -> dict[str, Any]:
        if self._tag_selection_service is not None:
            return self._tag_selection_service.get_tag_selection_payload()
        return self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()

    def update_tag_selection(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._tag_selection_service is not None:
            result = self._tag_selection_service.update_tag_selection(payload, actor_id=actor_id)
        else:
            result = self._app_settings_service.update_no_oa_bank_batch_tag_selection(payload, actor_id=actor_id)
            self.enqueue_background_refresh(["all"], reason="no_oa_bank_batch_tag_selection_changed")
            self.after_mutation(["all"], changed_case_ids=[], persist=False)
        self._sync_bank_flow_rule_relation_requirements(result, actor_id=actor_id)
        self._sync_turnover_rule_relation_requirements(result, actor_id=actor_id)
        return result

    def _sync_bank_flow_rule_relation_requirements(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, object]:
        relation_command_service = self._relation_command_service
        if relation_command_service is None:
            return {"changed_case_ids": [], "affected_months": []}
        list_active_relations = getattr(relation_command_service, "list_active_relations", None)
        if not callable(list_active_relations):
            return {"changed_case_ids": [], "affected_months": []}
        requirements_by_tag_code = self._bank_flow_rule_requirements_by_tag_code(payload)
        if not requirements_by_tag_code:
            return {"changed_case_ids": [], "affected_months": []}
        rule_version = int(BankTransactionCategoryService._normalize_version(payload.get("version", 1)) or 1)
        changed_case_ids: list[str] = []
        affected_months: set[str] = set()
        for relation in list(list_active_relations() or []):
            if not isinstance(relation, dict):
                continue
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            relation_mode = str(relation.get("relation_mode") or metadata.get("relation_mode") or "").strip()
            if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
                continue
            tag_code = str(metadata.get("flow_rule_tag_code") or "").strip()
            if not tag_code:
                continue
            requirement = requirements_by_tag_code.get(tag_code)
            if not isinstance(requirement, dict):
                continue
            next_metadata = {
                "requires_oa": bool(requirement.get("requires_oa")),
                "requires_invoice": bool(requirement.get("requires_invoice")),
                "flow_rule_version": rule_version,
            }
            if self._bank_flow_rule_relation_requirements_current(metadata, next_metadata):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id:
                continue
            try:
                result = relation_command_service.update_relation_metadata_for_case_id(
                    case_id=case_id,
                    actor_id=str(actor_id or ""),
                    special_metadata=next_metadata,
                    history_operation_type="bank_flow_rule_batch_tag_rule_requirement_sync",
                )
            except WorkbenchRelationCommandError as exc:
                raise self._relation_command_error(exc) from exc
            changed_case_ids.extend(
                str(changed_case_id).strip()
                for changed_case_id in list(result.get("changed_case_ids") or [])
                if str(changed_case_id).strip()
            )
            affected_months.update(
                str(month).strip()
                for month in list(result.get("affected_months") or [])
                if SEARCH_MONTH_RE.match(str(month).strip())
            )
        normalized_changed_case_ids = self._dedupe_ordered(changed_case_ids)
        normalized_months = sorted(affected_months)
        if normalized_changed_case_ids:
            self.after_mutation(
                normalized_months,
                changed_case_ids=normalized_changed_case_ids,
                persist=True,
                action_name="bank_flow_rule_batch_tag_rules_changed",
            )
            self.enqueue_background_refresh(
                normalized_months or ["all"],
                reason="bank_flow_rule_batch_tag_rules_changed",
                metadata=self._read_model_refresh_metadata_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE),
            )
        return {"changed_case_ids": normalized_changed_case_ids, "affected_months": normalized_months}

    def _sync_turnover_rule_relation_requirements(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, object]:
        relation_command_service = self._relation_command_service
        if relation_command_service is None:
            return {"changed_case_ids": [], "affected_months": []}
        list_active_relations = getattr(relation_command_service, "list_active_relations", None)
        if not callable(list_active_relations):
            return {"changed_case_ids": [], "affected_months": []}
        requirements_by_tag_code = self._bank_flow_rule_requirements_by_tag_code(payload)
        if not requirements_by_tag_code:
            return {"changed_case_ids": [], "affected_months": []}
        rule_version = int(BankTransactionCategoryService._normalize_version(payload.get("version", 1)) or 1)
        changed_case_ids: list[str] = []
        affected_months: set[str] = set()
        for relation in list(list_active_relations() or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id.startswith("turnover:"):
                continue
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            relation_mode = str(relation.get("relation_mode") or metadata.get("relation_mode") or "").strip()
            if relation_mode not in {"manual_confirmed", TURNOVER_MANUAL_CLOSURE_RELATION_MODE}:
                continue
            bank_row_ids = self._turnover_relation_bank_row_ids(relation)
            if not bank_row_ids:
                continue
            requirement = self._turnover_relation_requirement_from_bank_rows(
                bank_row_ids,
                requirements_by_tag_code=requirements_by_tag_code,
            )
            if requirement is None:
                continue
            next_metadata = {
                "source": str(metadata.get("source") or "turnover_ledger"),
                "turnover_relation_id": str(metadata.get("turnover_relation_id") or case_id.removeprefix("turnover:")),
                "requires_oa": bool(requirement.get("requires_oa")),
                "requires_invoice": bool(requirement.get("requires_invoice")),
                "paired_requirement_tag_codes": list(requirement.get("tag_codes") or []),
                "paired_requirement_source": TURNOVER_RULE_REQUIREMENT_SOURCE,
                "paired_requirement_version": rule_version,
            }
            if self._turnover_relation_requirements_current(
                relation=relation,
                metadata=metadata,
                next_metadata=next_metadata,
            ):
                continue
            try:
                result = relation_command_service.update_relation_metadata_for_case_id(
                    case_id=case_id,
                    relation_mode=TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
                    actor_id=str(actor_id or ""),
                    special_metadata=next_metadata,
                    history_operation_type="turnover_rule_tag_requirement_sync",
                )
            except WorkbenchRelationCommandError as exc:
                raise self._relation_command_error(exc) from exc
            changed_case_ids.extend(
                str(changed_case_id).strip()
                for changed_case_id in list(result.get("changed_case_ids") or [])
                if str(changed_case_id).strip()
            )
            affected_months.update(
                str(month).strip()
                for month in list(result.get("affected_months") or [])
                if SEARCH_MONTH_RE.match(str(month).strip())
            )
        normalized_changed_case_ids = self._dedupe_ordered(changed_case_ids)
        normalized_months = sorted(affected_months)
        if normalized_changed_case_ids:
            self.after_mutation(
                normalized_months,
                changed_case_ids=normalized_changed_case_ids,
                persist=True,
                action_name="turnover_rule_tag_rules_changed",
            )
        return {"changed_case_ids": normalized_changed_case_ids, "affected_months": normalized_months}

    @staticmethod
    def _turnover_relation_bank_row_ids(relation: dict[str, Any]) -> list[str]:
        row_ids = [
            str(row_id).strip()
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        row_types = [str(row_type or "").strip() for row_type in list(relation.get("row_types") or [])]
        if not row_ids:
            return []
        if len(row_types) == len(row_ids):
            return [
                row_id
                for row_id, row_type in zip(row_ids, row_types)
                if row_type == "bank"
            ]
        return [
            row_id
            for row_id in row_ids
            if row_id.startswith("txn_") or row_id.startswith("bank")
        ]

    def _turnover_relation_requirement_from_bank_rows(
        self,
        bank_row_ids: list[str],
        *,
        requirements_by_tag_code: dict[str, dict[str, bool]],
    ) -> dict[str, object] | None:
        categories_by_row_id = self._bank_transaction_category_service.bulk_get(bank_row_ids)
        tag_codes: list[str] = []
        requires_oa = False
        requires_invoice = False
        for row_id in bank_row_ids:
            category = categories_by_row_id.get(row_id)
            if not isinstance(category, dict):
                continue
            tag_code = self._turnover_requirement_tag_code_for_category(category, requirements_by_tag_code)
            if not tag_code:
                continue
            requirement = requirements_by_tag_code.get(tag_code)
            if not isinstance(requirement, dict):
                continue
            tag_codes.append(tag_code)
            requires_oa = requires_oa or bool(requirement.get("requires_oa"))
            requires_invoice = requires_invoice or bool(requirement.get("requires_invoice"))
        normalized_tag_codes = self._dedupe_ordered(tag_codes)
        if not normalized_tag_codes:
            return None
        return {
            "tag_codes": normalized_tag_codes,
            "requires_oa": requires_oa,
            "requires_invoice": requires_invoice,
        }

    def _turnover_requirement_tag_code_for_category(
        self,
        category: dict[str, Any],
        requirements_by_tag_code: dict[str, dict[str, bool]],
    ) -> str:
        category_code = str(category.get("category_code") or "").strip()
        if category_code and category_code in requirements_by_tag_code:
            return category_code
        if EXTERNAL_TURNOVER_CATEGORY_CODE not in requirements_by_tag_code:
            return ""
        semantics = self._bank_transaction_category_service.category_semantics_for_code(category_code)
        if str(semantics.get("turnover_role") or "").strip() == EXTERNAL_TURNOVER_ROLE:
            return EXTERNAL_TURNOVER_CATEGORY_CODE
        category_path = category.get("category_path")
        if not isinstance(category_path, list):
            category_path = semantics.get("category_path")
        category_root = str(category_path[0] if isinstance(category_path, list) and category_path else "").strip()
        if category_root in TURNOVER_RULE_CATEGORY_ROOTS:
            return EXTERNAL_TURNOVER_CATEGORY_CODE
        return ""

    @staticmethod
    def _turnover_relation_requirements_current(
        *,
        relation: dict[str, Any],
        metadata: dict[str, Any],
        next_metadata: dict[str, object],
    ) -> bool:
        if str(relation.get("relation_mode") or "").strip() != TURNOVER_MANUAL_CLOSURE_RELATION_MODE:
            return False
        if bool(metadata.get("requires_oa")) != bool(next_metadata.get("requires_oa")):
            return False
        if bool(metadata.get("requires_invoice")) != bool(next_metadata.get("requires_invoice")):
            return False
        current_version = int(
            BankTransactionCategoryService._normalize_version(metadata.get("paired_requirement_version", 1)) or 1
        )
        next_version = int(next_metadata.get("paired_requirement_version") or 1)
        if current_version != next_version:
            return False
        if str(metadata.get("paired_requirement_source") or "").strip() != str(
            next_metadata.get("paired_requirement_source") or ""
        ).strip():
            return False
        return [
            str(tag_code).strip()
            for tag_code in list(metadata.get("paired_requirement_tag_codes") or [])
            if str(tag_code).strip()
        ] == list(next_metadata.get("paired_requirement_tag_codes") or [])

    @staticmethod
    def _bank_flow_rule_requirements_by_tag_code(payload: dict[str, Any]) -> dict[str, dict[str, bool]]:
        requirements: dict[str, dict[str, bool]] = {}
        for item in list(payload.get("rules") or []):
            if not isinstance(item, dict):
                continue
            tag_code = str(item.get("tag_code") or item.get("code") or "").strip()
            if not tag_code:
                continue
            requirements[tag_code] = {
                "requires_oa": bool(item.get("requires_oa")),
                "requires_invoice": bool(item.get("requires_invoice")),
            }
        raw_requirements = payload.get("requirements_by_tag_code")
        if isinstance(raw_requirements, dict):
            for raw_code, item in raw_requirements.items():
                tag_code = str(raw_code or "").strip()
                if not tag_code or not isinstance(item, dict):
                    continue
                requirements[tag_code] = {
                    "requires_oa": bool(item.get("requires_oa")),
                    "requires_invoice": bool(item.get("requires_invoice")),
                }
        return requirements

    @staticmethod
    def _bank_flow_rule_relation_requirements_current(
        metadata: dict[str, Any],
        next_metadata: dict[str, object],
    ) -> bool:
        return (
            bool(metadata.get("requires_oa")) == bool(next_metadata.get("requires_oa"))
            and bool(metadata.get("requires_invoice")) == bool(next_metadata.get("requires_invoice"))
            and int(BankTransactionCategoryService._normalize_version(metadata.get("flow_rule_version", 1)) or 1)
            == int(next_metadata.get("flow_rule_version") or 1)
        )

    @staticmethod
    def _dedupe_ordered(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def detail_payload(self, batch_id: str) -> dict[str, object]:
        batch = self._no_oa_bank_batch_service.get_batch(batch_id)
        public_batch = self._public_batch(batch)
        if public_batch is None:
            raise KeyError("no_oa_bank_batch_not_found")
        row_ids = [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id).strip()]
        bank_rows = self.no_oa_bank_transaction_rows_by_ids(row_ids)
        categories_by_transaction_id = self.effective_categories_for_rows(bank_rows)
        rows_by_id = {str(row.get("id")): row for row in bank_rows if str(row.get("id") or "").strip()}
        relation_rows_by_id = self._workbench_relation_rows_by_id(row_ids)
        detail_rows = self._apply_submitted_row_tag_snapshot(
            public_batch,
            self.detail_rows(row_ids, rows_by_id, categories_by_transaction_id),
        )
        return {
            "batch": self.resolve_labels([public_batch])[0],
            "rows": self._apply_relation_status_to_detail_rows(
                detail_rows,
                relation_rows_by_id,
            ),
            "tag_counts": batch.get("tag_counts") if isinstance(batch.get("tag_counts"), dict) else {},
            "direction_counts": batch.get("direction_counts") if isinstance(batch.get("direction_counts"), dict) else {},
            "categories_by_transaction_id": self._detail_categories_by_transaction_id(
                row_ids,
                categories_by_transaction_id,
                public_batch,
            ),
            "workbench_relation_source_versions": self._workbench_relation_source_versions(),
        }

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
        persist: bool = True,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        try:
            self.refresh_batches(relation_mode=relation_mode)
            before_batch = self._no_oa_bank_batch_service.get_batch(batch_id)
            already_submitted = str(before_batch.get("status") or "") == "submitted"
            batch = self._no_oa_bank_batch_service.submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
            )
            if not already_submitted:
                self._confirm_relation_for_batch(batch, actor=actor, note=note, relation_mode=relation_mode)
            result = self._mutation_result(
                batch,
                status="submitted",
                persist=persist,
                read_model_key=self._read_model_key_for_relation_mode(relation_mode),
            )
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def submit_selected_rows(
        self,
        *,
        row_ids: list[str],
        actor: str,
        note: str | None,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        try:
            bank_rows, categories_by_transaction_id = self.refresh_batches(relation_mode=relation_mode)
            self._validate_internal_transfer_selection(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                row_ids=row_ids,
            )
            batch = self._no_oa_bank_batch_service.submit_selected_rows(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                active_relations=self._workbench_relation_active_relations_for_bank_rows(bank_rows),
                source_versions=self.no_oa_bank_batch_source_versions(),
                eligible_batch_types=self._eligible_tag_codes_for_relation_mode(relation_mode),
                row_ids=row_ids,
                actor=actor,
                note=note,
                relation_mode=relation_mode,
            )
            self._confirm_relation_for_batch(batch, actor=actor, note=note, relation_mode=relation_mode)
            result = self._mutation_result(
                batch,
                status="submitted",
                persist=True,
                read_model_key=self._read_model_key_for_relation_mode(relation_mode),
            )
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def submit_internal_transfer_rows_from_workbench(
        self,
        *,
        row_ids: list[str],
        actor: str,
        note: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        try:
            bank_rows, categories_by_transaction_id = self.refresh_batches()
            batch = self._internal_transfer_batch_for_workbench_rows(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                row_ids=row_ids,
            )
            already_submitted = str(batch.get("status") or "") == "submitted"
            submitted = self._no_oa_bank_batch_service.submit_batch(
                str(batch["batch_id"]),
                actor=actor,
                expected_version=int(batch.get("version") or 1),
                note=note,
            )
            if not already_submitted:
                self._confirm_relation_for_batch(submitted, actor=actor, note=note)
            result = self._mutation_result(submitted, status="submitted", persist=True)
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        try:
            before_batch = self._no_oa_bank_batch_service.get_batch(batch_id)
            already_withdrawn = str(before_batch.get("status") or "") == "withdrawn"
            batch = self._no_oa_bank_batch_service.withdraw_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                reason=reason,
            )
            if not already_withdrawn:
                self._cancel_relation_for_batch(batch, actor=actor, reason=reason)
            result = self._mutation_result(batch, status="withdrawn", persist=True)
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def reset_submitted_bank_flow_rule_batches(
        self,
        *,
        actor: str,
        reason: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        candidates = self._submitted_no_oa_rebaseline_candidates()
        withdrawn_batches: list[dict[str, object]] = []
        changed_case_ids: list[str] = []
        affected_months: set[str] = set()
        resolved_reason = str(reason or "").strip() or "流水规则批量处理：重置全部已提交批次为未提交"
        try:
            for candidate in candidates:
                batch_id = str(candidate.get("batch_id") or "").strip()
                if not batch_id:
                    continue
                before_batch = self._no_oa_bank_batch_service.get_batch(batch_id)
                already_withdrawn = str(before_batch.get("status") or "") == "withdrawn"
                withdrawn = self._no_oa_bank_batch_service.withdraw_batch(
                    batch_id,
                    actor=actor,
                    expected_version=int(before_batch.get("version") or 1),
                    reason=resolved_reason,
                )
                if not already_withdrawn:
                    try:
                        self._cancel_relation_for_batch(
                            withdrawn,
                            actor=actor,
                            reason=resolved_reason,
                            history_operation_type="bank_flow_rule_batch_reset_submitted_withdraw",
                            idempotency_operation="bank_flow_rule_batch_reset_submitted",
                        )
                    except NoOaBankBatchRelationMutationError as exc:
                        if exc.error_code != "no_oa_bank_batch_relation_not_found":
                            raise
                withdrawn_batches.append(withdrawn)
                relation_case_id = str(withdrawn.get("relation_case_id") or withdrawn.get("batch_id") or "").strip()
                if relation_case_id:
                    changed_case_ids.append(relation_case_id)
                affected_months.update(self.affected_months(withdrawn))
            if withdrawn_batches:
                self.refresh_batches(
                    relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    scope_key="all",
                )
            workbench_rebuild_queued = self.after_mutation(
                sorted(affected_months),
                changed_case_ids=changed_case_ids,
                persist=True,
                action_name="bank_flow_rule_batch_reset_submitted",
            )
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return {
            "summary": {
                "reset_count": len(withdrawn_batches),
                "batch_count": len(withdrawn_batches),
                "row_count": sum(int(batch.get("row_count") or 0) for batch in withdrawn_batches),
                "affected_months": sorted(affected_months),
            },
            "affected_months": sorted(affected_months),
            **write_target_envelope(
                read_model_key=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                scope_keys=sorted(affected_months),
                fallback_scope_key="all",
            ),
            "workbench_rebuild_queued": workbench_rebuild_queued,
            "results": [
                {"batch_id": batch.get("batch_id"), "status": "withdrawn"}
                for batch in withdrawn_batches
            ],
        }

    def rebaseline_submitted_no_oa_batches_dry_run(self) -> dict[str, object]:
        candidates = self._submitted_no_oa_rebaseline_candidates()
        return self._rebaseline_no_oa_manifest(candidates, applied=False)

    def apply_submitted_no_oa_rebaseline(
        self,
        *,
        actor: str,
        reason: str | None,
        manifest: object | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        candidates = self._submitted_no_oa_rebaseline_candidates()
        self._assert_rebaseline_manifest_matches(candidates, manifest)
        withdrawn_batches: list[dict[str, object]] = []
        changed_case_ids: list[str] = []
        affected_months: set[str] = set()
        resolved_reason = str(reason or "").strip() or "流水规则批量处理 rebaseline：撤回历史免OA已提交批次"
        try:
            for candidate in candidates:
                batch_id = str(candidate.get("batch_id") or "").strip()
                if not batch_id:
                    continue
                before_batch = self._no_oa_bank_batch_service.get_batch(batch_id)
                already_withdrawn = str(before_batch.get("status") or "") == "withdrawn"
                withdrawn = self._no_oa_bank_batch_service.withdraw_batch(
                    batch_id,
                    actor=actor,
                    expected_version=int(before_batch.get("version") or 1),
                    reason=resolved_reason,
                )
                if not already_withdrawn:
                    self._cancel_relation_for_batch(
                        withdrawn,
                        actor=actor,
                        reason=resolved_reason,
                        history_operation_type="bank_flow_rule_rebaseline_no_oa_withdraw",
                        idempotency_operation="rebaseline_no_oa_withdraw",
                    )
                withdrawn_batches.append(withdrawn)
                relation_case_id = str(withdrawn.get("relation_case_id") or withdrawn.get("batch_id") or "").strip()
                if relation_case_id:
                    changed_case_ids.append(relation_case_id)
                affected_months.update(self.affected_months(withdrawn))
            workbench_rebuild_queued = self.after_mutation(
                sorted(affected_months),
                changed_case_ids=changed_case_ids,
                persist=True,
                action_name="bank_flow_rule_rebaseline_no_oa",
            )
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        manifest = self._rebaseline_no_oa_manifest(withdrawn_batches, applied=True)
        return {
            **manifest,
            "workbench_rebuild_queued": workbench_rebuild_queued,
        }

    def _submitted_no_oa_rebaseline_candidates(self) -> list[dict[str, object]]:
        return [
            batch
            for batch in self._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
            if str(batch.get("status") or "").strip() == "submitted"
        ]

    def _assert_rebaseline_manifest_matches(self, candidates: list[dict[str, object]], manifest: object | None) -> None:
        if not isinstance(manifest, dict):
            raise ValueError("bank_flow_rule_rebaseline_manifest_required")
        expected_rows = manifest.get("batches")
        if not isinstance(expected_rows, list):
            raise ValueError("bank_flow_rule_rebaseline_manifest_required")

        def key(row: dict[str, object]) -> tuple[str, int]:
            return str(row.get("batch_id") or "").strip(), int(row.get("version") or 1)

        expected = sorted(
            key(row)
            for row in expected_rows
            if isinstance(row, dict) and str(row.get("batch_id") or "").strip()
        )
        actual = sorted(key(row) for row in candidates)
        if not actual and expected and self._rebaseline_manifest_already_applied(expected):
            return
        if expected != actual:
            raise ValueError("bank_flow_rule_rebaseline_manifest_mismatch")

    def _rebaseline_manifest_already_applied(self, expected: list[tuple[str, int]]) -> bool:
        for batch_id, _version in expected:
            try:
                batch = self._no_oa_bank_batch_service.get_batch(batch_id)
            except KeyError:
                return False
            if str(batch.get("status") or "").strip() != "withdrawn":
                return False
        return True

    @staticmethod
    def _rebaseline_no_oa_manifest(batches: list[dict[str, object]], *, applied: bool) -> dict[str, object]:
        affected_months = sorted({
            str(batch.get("scope_month") or "").strip()
            for batch in batches
            if str(batch.get("scope_month") or "").strip()
        })
        rows = [
            {
                "batch_id": str(batch.get("batch_id") or ""),
                "batch_type": str(batch.get("batch_type") or ""),
                "batch_label": str(batch.get("batch_label") or ""),
                "relation_case_id": str(batch.get("relation_case_id") or batch.get("batch_id") or ""),
                "scope_month": str(batch.get("scope_month") or ""),
                "row_ids": [str(row_id) for row_id in list(batch.get("row_ids") or [])],
                "row_count": int(batch.get("row_count") or len(list(batch.get("row_ids") or []))),
                "version": int(batch.get("version") or 1),
                "status": str(batch.get("status") or ""),
            }
            for batch in batches
        ]
        return {
            "dry_run": not applied,
            "applied": applied,
            "summary": {
                "candidate_count": len(rows),
                "batch_count": len(rows),
                "row_count": sum(int(row.get("row_count") or 0) for row in rows),
                "affected_months": affected_months,
            },
            "batches": rows,
            "risks": [],
        }

    def _eligible_tag_codes_for_relation_mode(self, relation_mode: str) -> set[str]:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            payload = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
            return {
                str(tag.get("code") or "").strip()
                for tag in list(payload.get("active_tags") or [])
                if isinstance(tag, dict) and str(tag.get("code") or "").strip()
            }
        return set(self.selected_tag_codes())

    @staticmethod
    def _read_model_key_for_relation_mode(relation_mode: str) -> str:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            return BANK_FLOW_RULE_BATCH_RELATION_MODE
        return "no_oa_bank_batch"

    @staticmethod
    def _read_model_list_method_for_relation_mode(relation_mode: str) -> str:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            return "list_bank_flow_rule_batch_rows"
        return "list_no_oa_bank_batch_rows"

    @staticmethod
    def _read_model_refresh_metadata_for_relation_mode(relation_mode: str) -> dict[str, object] | None:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            return {
                "action_name": "bank_flow_rule_batch_read_model_refresh",
                "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
            }
        return None

    @staticmethod
    def _read_model_refresh_reason_for_relation_mode(
        relation_mode: str,
        *,
        fallback_reason: str,
        bank_flow_reason: str,
    ) -> str:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            return bank_flow_reason
        return fallback_reason

    def _confirm_relation_for_batch(
        self,
        batch: dict[str, object],
        *,
        actor: str,
        note: str | None,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> None:
        relation_command_service = self._require_relation_command_service()
        payload = self._no_oa_bank_batch_service.relation_command_payload_for_batch(batch, note=note)
        special_metadata = payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {}
        requirement_metadata = self._no_oa_paired_requirement_metadata(str(batch.get("batch_type") or ""))
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            requirement_metadata = self._bank_flow_rule_requirement_metadata(batch, requirement_metadata)
        payload["special_metadata"] = {
            **special_metadata,
            **requirement_metadata,
        }
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("no_oa_bank_batch_relation_case_id_required")
        try:
            relation_command_service.confirm_relation(
                case_id=case_id,
                row_ids=list(payload.get("row_ids") or []),
                row_types=list(payload.get("row_types") or []),
                relation_mode=relation_mode,
                actor_id=str(actor or ""),
                month_scope=str(payload.get("month_scope") or "all"),
                note=str(payload.get("note") or ""),
                special_metadata=payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {},
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
                display_tags=[
                    str(tag).strip()
                    for tag in list(payload.get("display_tags") or [])
                    if str(tag).strip()
                ],
                idempotency_key=self._relation_idempotency_key(batch, operation="submit"),
                history_operation_type=(
                    "bank_flow_rule_batch_submit"
                    if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
                    else "no_oa_bank_batch_submit"
                ),
            )
        except WorkbenchRelationCommandError as exc:
            raise self._relation_command_error(exc) from exc

    def _bank_flow_rule_requirement_metadata(
        self,
        batch: dict[str, object],
        requirement_metadata: dict[str, object],
    ) -> dict[str, object]:
        tag_code = str(requirement_metadata.get("paired_requirement_tag_code") or batch.get("batch_type") or "").strip()
        requires_oa = bool(requirement_metadata.get("paired_requires_oa"))
        requires_invoice = bool(requirement_metadata.get("paired_requires_invoice"))
        return {
            "source": BANK_FLOW_RULE_BATCH_RELATION_MODE,
            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
            "source_batch_id": str(batch.get("batch_id") or ""),
            "flow_rule_tag_code": tag_code,
            "flow_rule_version": int(requirement_metadata.get("paired_requirement_version") or 1),
            "requires_oa": requires_oa,
            "requires_invoice": requires_invoice,
            "source_row_count": int(batch.get("row_count") or len(list(batch.get("row_ids") or []))),
            "collapsed_bank_rows": int(batch.get("row_count") or 0) > 3,
        }

    def _no_oa_paired_requirement_metadata(self, batch_type: str) -> dict[str, object]:
        tag_code = str(batch_type or "").strip()
        payload = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        requirements = payload.get("requirements_by_tag_code") if isinstance(payload.get("requirements_by_tag_code"), dict) else {}
        rule = requirements.get(tag_code) if isinstance(requirements.get(tag_code), dict) else {}
        return {
            "paired_requires_oa": bool(rule.get("requires_oa")),
            "paired_requires_invoice": bool(rule.get("requires_invoice")),
            "paired_requirement_tag_code": tag_code,
            "paired_requirement_version": int(payload.get("version") or 1),
        }

    def _cancel_relation_for_batch(
        self,
        batch: dict[str, object],
        *,
        actor: str,
        reason: str | None,
        history_operation_type: str = "no_oa_bank_batch_withdraw",
        idempotency_operation: str = "withdraw",
    ) -> None:
        relation_command_service = self._require_relation_command_service()
        case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        if not case_id:
            raise ValueError("no_oa_bank_batch_relation_case_id_required")
        try:
            relation_command_service.cancel_relation(
                case_id=case_id,
                actor_id=str(actor or ""),
                reason=reason,
                idempotency_key=self._relation_idempotency_key(batch, operation=idempotency_operation),
                history_operation_type=history_operation_type,
            )
        except WorkbenchRelationCommandError as exc:
            raise self._relation_command_error(exc) from exc

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise ValueError("no_oa_bank_batch_relation_command_unavailable")
        return self._relation_command_service

    @staticmethod
    def _relation_idempotency_key(batch: dict[str, object], *, operation: str) -> str:
        return ":".join(
            [
                "no_oa_bank_batch",
                operation,
                str(batch.get("batch_id") or ""),
                str(batch.get("relation_case_id") or batch.get("batch_id") or ""),
                str(batch.get("version") or ""),
            ]
        )

    @staticmethod
    def _relation_command_error(exc: WorkbenchRelationCommandError) -> NoOaBankBatchRelationMutationError:
        if exc.error_code in {"workbench_relation_read_model_not_fresh", "workbench_relation_read_model_unavailable"}:
            return NoOaBankBatchRelationMutationError(
                "no_oa_bank_batch_relation_read_model_not_fresh",
                "no_oa_bank_batch_relation_read_model_not_fresh",
                payload=exc.payload,
            )
        if exc.error_code == "workbench_relation_active_row_conflict":
            return NoOaBankBatchRelationMutationError(
                "no_oa_bank_batch_relation_active_row_conflict",
                "no_oa_bank_batch_relation_active_row_conflict",
                payload=exc.payload,
            )
        if exc.error_code == "workbench_relation_not_found":
            return NoOaBankBatchRelationMutationError(
                "no_oa_bank_batch_relation_not_found",
                "no_oa_bank_batch_relation_not_found",
                payload=exc.payload,
            )
        return NoOaBankBatchRelationMutationError(exc.error_code, exc.error_code, payload=exc.payload)

    @classmethod
    def _pagination_from_query(cls, query: dict[str, list[str]]) -> dict[str, int] | None:
        if "page" not in query and "page_size" not in query and "pageSize" not in query:
            return None
        return {
            "page": cls._positive_int((query.get("page") or [1])[0], "page"),
            "page_size": cls._positive_int(
                (query.get("page_size") or query.get("pageSize") or [100])[0],
                "page_size",
                maximum=200,
            ),
        }

    @staticmethod
    def _positive_int(value: object, field: str, *, maximum: int | None = None) -> int:
        try:
            number = int(value if value not in (None, "") else 1)
        except (TypeError, ValueError) as exc:
            raise NoOaBankBatchRelationMutationError("invalid_paging", f"{field} must be a positive integer.") from exc
        if number < 1:
            raise NoOaBankBatchRelationMutationError("invalid_paging", f"{field} must be a positive integer.")
        if maximum is not None and number > maximum:
            raise NoOaBankBatchRelationMutationError("invalid_paging", f"{field} must be <= {maximum}.")
        return number

    @staticmethod
    def _page_items(items: list[dict[str, Any]], pagination: dict[str, int] | None) -> list[dict[str, Any]]:
        if pagination is None:
            return items
        page = pagination["page"]
        page_size = pagination["page_size"]
        start = (page - 1) * page_size
        return items[start : start + page_size]

    @staticmethod
    def _pagination_payload(items: list[dict[str, Any]], pagination: dict[str, int] | None) -> dict[str, object]:
        if pagination is None:
            return {}
        page_size = pagination["page_size"]
        return {
            "pagination": {
                "page": pagination["page"],
                "page_size": page_size,
                "pageSize": page_size,
                "total": len(items),
            }
        }

    @staticmethod
    def _refresh_scope_keys_for_filters(filters: dict[str, object]) -> list[str]:
        month = str(filters.get("month") or "").strip()
        return [month] if SEARCH_MONTH_RE.match(month) else ["all"]

    def refresh_batches(
        self,
        *,
        apply_relation_repairs: bool = True,
        scope_key: str = "all",
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
        refresh_scope_key = str(scope_key or "all").strip() or "all"
        bank_rows = self.no_oa_bank_transaction_rows(month=refresh_scope_key, include_categories=False)
        categories_by_transaction_id = self.effective_categories_for_rows(bank_rows)
        return self.refresh_batches_from_prepared_rows(
            bank_rows=bank_rows,
            categories_by_transaction_id=categories_by_transaction_id,
            apply_relation_repairs=apply_relation_repairs,
            scope_key=refresh_scope_key,
            relation_mode=relation_mode,
        )

    def unchanged_read_model_scope_result(
        self,
        *,
        scope_key: str,
        source_versions: dict[str, object],
        allow_refreshing_read_model_status: bool = False,
    ) -> dict[str, object] | None:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        filters = {"month": normalized_scope_key} if SEARCH_MONTH_RE.match(normalized_scope_key) else {}
        source_versions_summary_loader = getattr(
            self._no_oa_bank_batch_read_model_repository,
            "no_oa_bank_batch_source_versions_summary",
            None,
        )
        if callable(source_versions_summary_loader):
            summary = source_versions_summary_loader(filters)
            allowed_statuses = {"fresh"}
            if allow_refreshing_read_model_status:
                allowed_statuses.add("refreshing")
            if not isinstance(summary, dict) or str(summary.get("read_model_status") or "") not in allowed_statuses:
                return None
            existing_source_versions = summary.get("source_versions")
            if not isinstance(existing_source_versions, dict) or dict(existing_source_versions) != source_versions:
                return None
            return {
                "scope_key": normalized_scope_key,
                "batch_count": max(int(summary.get("row_count") or 0), 0),
                "source_versions": source_versions,
                "skipped": True,
                "skip_reason": "source_versions_unchanged",
            }
        list_read_model_batches = getattr(self._no_oa_bank_batch_read_model_repository, "list_no_oa_bank_batch_rows", None)
        if not callable(list_read_model_batches):
            return None
        read_model_rows = list_read_model_batches(filters)
        if not read_model_rows:
            return None
        existing_versions = [
            row.get("source_versions")
            for row in list(read_model_rows)
            if isinstance(row, dict) and isinstance(row.get("source_versions"), dict)
        ]
        if not existing_versions or any(dict(value) != source_versions for value in existing_versions):
            return None
        return {
            "scope_key": normalized_scope_key,
            "batch_count": len(read_model_rows),
            "source_versions": source_versions,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

    def active_relations_for_bank_rows(self, bank_rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return self._workbench_relation_active_relations_for_bank_rows(bank_rows)

    def load_relation_source_versions_for_bank_rows(self, bank_rows: list[dict[str, object]]) -> None:
        if self._relation_facade is None:
            return
        load_source_versions = getattr(self._relation_facade, "source_versions_for_month", None)
        if not callable(load_source_versions):
            self._workbench_relation_active_relations_for_bank_rows(bank_rows)
            return
        self.load_relation_source_versions_for_scope_keys(self._months_for_bank_rows(bank_rows))

    def load_relation_source_versions_for_scope_keys(self, scope_keys: list[str]) -> None:
        if self._relation_facade is None:
            return
        load_source_versions = getattr(self._relation_facade, "source_versions_for_month", None)
        if not callable(load_source_versions):
            return
        for month in [
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if SEARCH_MONTH_RE.match(str(scope_key).strip())
        ]:
            load_source_versions(
                month,
                require_fresh=False,
                reason="no_oa_bank_batch_source_version_precheck",
            )

    def read_model_scope_source_versions(self, *, scope_key: str) -> dict[str, object]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        scope_keys = [normalized_scope_key] if SEARCH_MONTH_RE.match(normalized_scope_key) else []
        source_versions = self._no_oa_bank_batch_base_source_versions()
        bank_detail_source_versions = self._bank_detail_source_versions_for_scope_keys(scope_keys)
        if bank_detail_source_versions:
            source_versions["bank_detail_source_versions"] = bank_detail_source_versions
        workbench_relation_source_versions = self._workbench_relation_source_versions_for_scope_keys(scope_keys)
        if workbench_relation_source_versions:
            source_versions["workbench_relation_source_versions"] = workbench_relation_source_versions
        return source_versions

    def bank_row_count_from_source_versions(self, source_versions: dict[str, object]) -> int:
        bank_detail_source_versions = source_versions.get("bank_detail_source_versions")
        if not isinstance(bank_detail_source_versions, dict):
            return 0
        row_count = bank_detail_source_versions.get("row_count")
        if row_count is None:
            for value in bank_detail_source_versions.values():
                if isinstance(value, dict) and value.get("row_count") is not None:
                    row_count = value.get("row_count")
                    break
        try:
            return max(int(row_count or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _bank_detail_source_versions_for_scope_keys(self, scope_keys: list[str]) -> dict[str, object]:
        source_versions_loader = getattr(self._effective_category_provider, "source_versions_for_scope_keys", None)
        normalized_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if SEARCH_MONTH_RE.match(str(scope_key).strip())
        ]
        if not callable(source_versions_loader) or not normalized_scope_keys:
            return {}
        payload = source_versions_loader(
            normalized_scope_keys,
            require_fresh=False,
            reason="no_oa_bank_batch_source_version_precheck",
        )
        if not isinstance(payload, dict):
            return {}
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        return _stable_dependency_source_versions(source_versions)

    def _workbench_relation_source_versions_for_scope_keys(self, scope_keys: list[str]) -> dict[str, object]:
        if self._relation_facade is None:
            return {}
        load_source_versions = getattr(self._relation_facade, "source_versions_for_month", None)
        normalized_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if SEARCH_MONTH_RE.match(str(scope_key).strip())
        ]
        if not callable(load_source_versions) or not normalized_scope_keys:
            return {}
        versions_by_scope: dict[str, object] = {}
        for scope_key in normalized_scope_keys:
            payload = load_source_versions(
                scope_key,
                require_fresh=False,
                reason="no_oa_bank_batch_source_version_precheck",
            )
            source_versions = payload.get("source_versions") if isinstance(payload, dict) else None
            if isinstance(source_versions, dict) and source_versions:
                versions_by_scope[scope_key] = dict(source_versions)
        if len(normalized_scope_keys) == 1:
            value = versions_by_scope.get(normalized_scope_keys[0])
            return dict(value) if isinstance(value, dict) else {}
        return versions_by_scope

    def refresh_batches_from_prepared_rows(
        self,
        *,
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
        active_relations: list[dict[str, object]] | None = None,
        source_versions: dict[str, object] | None = None,
        apply_relation_repairs: bool,
        scope_key: str,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
        refresh_scope_key = str(scope_key or "all").strip() or "all"
        source_version_payload = dict(source_versions) if isinstance(source_versions, dict) else self.no_oa_bank_batch_source_versions()
        self._apply_categories_to_rows(bank_rows, categories_by_transaction_id)
        self._no_oa_bank_batch_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            active_relations
            if active_relations is not None
            else self._workbench_relation_active_relations_for_bank_rows(bank_rows),
            source_version_payload,
            eligible_batch_types=self._eligible_tag_codes_for_relation_mode(relation_mode),
            apply_relation_repairs=apply_relation_repairs,
            refresh_scope_key=refresh_scope_key,
            relation_mode=relation_mode,
        )
        migration_result = self._no_oa_bank_batch_service.last_legacy_migration_result()
        if apply_relation_repairs and migration_result.get("changed"):
            self.after_mutation(
                [
                    str(month)
                    for month in list(migration_result.get("affected_months") or [])
                    if str(month).strip()
                ],
                changed_case_ids=[
                    str(case_id)
                    for case_id in list(migration_result.get("changed_case_ids") or [])
                    if str(case_id).strip()
                ],
                persist=True,
            )
        return bank_rows, categories_by_transaction_id

    def no_oa_bank_transaction_rows(
        self,
        *,
        month: str = "all",
        include_categories: bool = True,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        normalized_month = str(month or "all").strip() or "all"
        for transaction in list(self._import_service.list_transactions(month=normalized_month)):
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            row = self.normalize_no_oa_bank_transaction_payload(payload)
            if row is not None:
                rows.append(row)
        if include_categories:
            self._apply_categories_to_rows(rows, self.effective_categories_for_rows(rows))
        return rows

    def _apply_categories_to_rows(
        self,
        rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
    ) -> None:
        for row in rows:
            transaction_id = str(row.get("id") or "").strip()
            category = categories_by_transaction_id.get(transaction_id, {})
            if category:
                row["category_code"] = category.get("category_code")
                row["category_label"] = category.get("category_label")
                row["category_path"] = list(category.get("category_path") or [])
                row["category_primary_label"] = category.get("category_primary_label") or category.get("effective_category_primary_label")
                row["category_sub_label"] = category.get("category_sub_label") or category.get("effective_category_sub_label")
                row["category_label_path"] = list(
                    category.get("category_label_path") or category.get("effective_category_label_path") or []
                )
                row["category_source"] = category.get("category_source") or category.get("source")

    def no_oa_bank_transaction_rows_by_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        get_transaction = getattr(self._import_service, "get_transaction", None)
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not callable(get_transaction):
            rows_by_id = {
                str(row.get("id") or "").strip(): row
                for row in self.no_oa_bank_transaction_rows()
                if str(row.get("id") or "").strip()
            }
            return [rows_by_id[row_id] for row_id in normalized_row_ids if row_id in rows_by_id]

        rows: list[dict[str, object]] = []
        for row_id in normalized_row_ids:
            transaction = get_transaction(row_id)
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            row = self.normalize_no_oa_bank_transaction_payload(payload)
            if row is not None:
                rows.append(row)
        return rows

    @staticmethod
    def normalize_no_oa_bank_transaction_payload(payload: dict[str, object]) -> dict[str, object] | None:
        transaction_id = str(payload.get("id") or "").strip()
        if not transaction_id:
            return None
        row = dict(payload)
        row["id"] = transaction_id
        row["type"] = "bank"
        row["bank_name"] = str(
            row.get("bank_name")
            or row.get("imported_bank_name")
            or row.get("bank_short_name")
            or row.get("account_bank")
            or ""
        ).strip()
        account_no = str(row.get("account_no") or row.get("account_number") or "").strip()
        account_last4 = str(row.get("account_last4") or row.get("imported_bank_last4") or "").strip()
        if not account_last4:
            digits = "".join(ch for ch in account_no if ch.isdigit())
            account_last4 = digits[-4:] if digits else ""
        row["account_last4"] = account_last4
        row["account_key"] = str(row.get("account_key") or f"{row['bank_name']}:{account_last4}").strip(":")
        row["counterparty_name"] = str(row.get("counterparty_name") or row.get("counterparty_name_raw") or "").strip()
        amount = row.get("amount") or "0.00"
        direction = str(row.get("txn_direction") or row.get("direction") or "").strip().lower()
        if direction in {"outflow", "expense", "支", "出"}:
            row["direction"] = "expense"
            row["direction_label"] = "支"
            row["debit_amount"] = row.get("debit_amount") or amount
            row["credit_amount"] = row.get("credit_amount") or "0.00"
        elif direction in {"inflow", "income", "收", "进"}:
            row["direction"] = "income"
            row["direction_label"] = "收"
            row["debit_amount"] = row.get("debit_amount") or "0.00"
            row["credit_amount"] = row.get("credit_amount") or amount
        if "purpose" not in row:
            row["purpose"] = row.get("usage") or row.get("use") or ""
        return row

    def effective_categories_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        categories_by_transaction_id = {
            str(transaction_id): dict(category)
            for transaction_id, category in dict(self._effective_category_provider.bulk_get_for_rows(rows) or {}).items()
            if isinstance(category, dict)
        }
        row_ids = {
            str(row.get("id") or "").strip()
            for row in list(rows or [])
            if str(row.get("id") or "").strip()
        }
        snapshot = self._bank_transaction_category_service.snapshot()
        manual_categories = snapshot.get("categories") if isinstance(snapshot, dict) else None
        if not isinstance(manual_categories, dict):
            return categories_by_transaction_id
        for transaction_id, category in manual_categories.items():
            normalized_transaction_id = str(transaction_id or "").strip()
            if normalized_transaction_id not in row_ids or not isinstance(category, dict):
                continue
            category_code = str(category.get("category_code") or "").strip()
            if category_code != "internal_transfer":
                continue
            merged = dict(categories_by_transaction_id.get(normalized_transaction_id) or {})
            merged.update(category)
            merged["transaction_id"] = normalized_transaction_id
            merged["category_code"] = category_code
            merged["effective_category_code"] = category_code
            merged["effective_category_label"] = category.get("category_label")
            merged["effective_category_primary_label"] = category.get("category_primary_label")
            merged["effective_category_sub_label"] = category.get("category_sub_label")
            merged["effective_category_label_path"] = list(category.get("category_label_path") or [])
            merged["effective_category_path"] = list(category.get("category_path") or [])
            merged["effective_category_source"] = category.get("source") or category.get("category_source") or "manual"
            categories_by_transaction_id[normalized_transaction_id] = merged
        return categories_by_transaction_id

    def selected_tag_codes(self) -> list[str]:
        payload = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        return [str(code) for code in list(payload.get("selected_tag_codes") or []) if str(code).strip()]

    def summary(self, batches: list[dict[str, object]]) -> dict[str, object]:
        public_batches = self._public_batches(batches)
        counts: dict[str, int] = {"draft": 0, "submitted": 0, "withdrawn": 0, "conflict": 0, "stale": 0}
        selected_or_existing_codes = [
            *self.selected_tag_codes(),
            *[
                str(batch.get("batch_type") or "").strip()
                for batch in public_batches
                if isinstance(batch, dict) and str(batch.get("batch_type") or "").strip()
            ],
        ]
        category_counts: dict[str, dict[str, object]] = {}
        for batch_type in selected_or_existing_codes:
            if not batch_type or batch_type in category_counts:
                continue
            definition = self.bank_transaction_tag_definition_current(batch_type)
            category_counts[batch_type] = {
                "code": batch_type,
                "label": self.bank_transaction_tag_label_from_definition(batch_type, definition),
                "primary_label": str((definition or {}).get("output_primary_label") or ""),
                "sub_label": str((definition or {}).get("output_sub_label") or ""),
                "label_path": [
                    item
                    for item in [
                        str((definition or {}).get("output_primary_label") or "").strip(),
                        str((definition or {}).get("output_sub_label") or "").strip(),
                    ]
                    if item
                ],
                "total": 0,
                "draft": 0,
                "submitted": 0,
                "withdrawn": 0,
                "conflict": 0,
                "stale": 0,
                "total_amount": Decimal("0.00"),
            }
        total_amount = Decimal("0.00")
        for presented_batch in public_batches:
            status = str(presented_batch.get("status") or "").strip()
            if status in counts:
                counts[status] += 1
            batch_type = str(presented_batch.get("batch_type") or "").strip()
            try:
                amount = Decimal(str(presented_batch.get("total_amount") or "0").replace(",", ""))
            except Exception:
                amount = Decimal("0.00")
            total_amount += amount
            if batch_type in category_counts:
                category = category_counts[batch_type]
                category["total"] = int(category["total"]) + 1
                if status in counts:
                    category[status] = int(category[status]) + 1
                category["total_amount"] = category["total_amount"] + amount
        categories = []
        for category in [dict(value) for value in category_counts.values()]:
            category["total_amount"] = f"{category['total_amount']:.2f}"
            categories.append(category)
        return {
            "total": len(public_batches),
            **counts,
            "draft_count": counts["draft"],
            "submitted_count": counts["submitted"],
            "withdrawn_count": counts["withdrawn"],
            "conflict_count": counts["conflict"],
            "stale_count": counts["stale"],
            "total_amount": f"{total_amount:.2f}",
            "categories": categories,
        }

    @classmethod
    def _public_batches(cls, batches: list[dict[str, object]] | object) -> list[dict[str, object]]:
        if not isinstance(batches, list):
            return []
        public_batches: list[dict[str, object]] = []
        for batch in batches:
            if not isinstance(batch, dict):
                continue
            public_batch = cls._public_batch(batch)
            if public_batch is not None:
                public_batches.append(public_batch)
        return public_batches

    def resolve_labels(self, batches: list[dict[str, object]]) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for batch in list(batches or []):
            if not isinstance(batch, dict):
                continue
            next_batch = self._presentation_batch(batch)
            batch_type = str(next_batch.get("batch_type") or "").strip()
            if batch_type:
                definition = self.bank_transaction_tag_definition_current(batch_type)
                label = self.bank_transaction_tag_label_from_definition(batch_type, definition)
                next_batch["batch_label"] = label
                next_batch["display_tags"] = ["免OA", label]
                next_batch["category_primary_label"] = str((definition or {}).get("output_primary_label") or label)
                next_batch["category_sub_label"] = str((definition or {}).get("output_sub_label") or "")
                next_batch["category_label_path"] = [
                    item
                    for item in [
                        str(next_batch.get("category_primary_label") or "").strip(),
                        str(next_batch.get("category_sub_label") or "").strip(),
                    ]
                    if item
                ]
            resolved.append(next_batch)
        return resolved

    @classmethod
    def _public_batch(cls, batch: dict[str, object]) -> dict[str, object] | None:
        next_batch = cls._presentation_batch(batch)
        status = str(next_batch.get("status") or "").strip()
        if status not in {"draft", "submitted", "withdrawn"}:
            return None
        return next_batch

    @staticmethod
    def _presentation_batch(batch: dict[str, object]) -> dict[str, object]:
        next_batch = dict(batch)
        status = str(next_batch.get("status") or "").strip()
        status_bucket = str(next_batch.get("status_bucket") or next_batch.get("statusBucket") or "").strip()
        raw_can_withdraw = next_batch.get("can_withdraw", next_batch.get("canWithdraw"))
        can_withdraw = raw_can_withdraw is True or str(raw_can_withdraw).strip().lower() == "true"
        if status == "unsubmitted" and status_bucket == "unsubmitted":
            next_batch["status"] = "draft"
            next_batch["status_bucket"] = "unsubmitted"
            next_batch["can_submit"] = True
            next_batch["can_withdraw"] = False
            next_batch["blocked_reason"] = ""
            return next_batch
        if status == "stale" and (status_bucket == "submitted" or can_withdraw):
            next_batch["relation_backed_status"] = "stale"
            next_batch["status"] = "submitted"
            next_batch["status_bucket"] = "submitted"
            next_batch["can_submit"] = False
            next_batch["can_withdraw"] = True
            next_batch["blocked_reason"] = ""
        return next_batch

    def no_oa_bank_batch_source_versions(self) -> dict[str, object]:
        source_versions = self._no_oa_bank_batch_base_source_versions()
        bank_detail_source_versions = getattr(self._effective_category_provider, "last_source_versions", None)
        if isinstance(bank_detail_source_versions, dict) and bank_detail_source_versions:
            source_versions["bank_detail_source_versions"] = _stable_dependency_source_versions(bank_detail_source_versions)
        workbench_relation_source_versions = self._workbench_relation_source_versions()
        if workbench_relation_source_versions:
            source_versions["workbench_relation_source_versions"] = workbench_relation_source_versions
        return source_versions

    def _no_oa_bank_batch_base_source_versions(self) -> dict[str, object]:
        no_oa_selection = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        return {
            **_stable_dependency_source_versions(self._workbench_matching_source_versions_provider()),
            "no_oa_bank_batch_schema_version": NO_OA_BANK_BATCH_SCHEMA_VERSION,
            "no_oa_bank_batch_tag_selection_version": int(no_oa_selection.get("version") or 1),
            "bank_transaction_category_schema_version": BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
            "bank_transaction_category_snapshot_version": WorkbenchReadModelService.snapshot_version(
                self._bank_transaction_category_service.snapshot()
            ),
        }

    def _workbench_relation_source_versions(self) -> dict[str, object]:
        source_versions = getattr(self._relation_facade, "last_source_versions", None)
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def _workbench_relation_rows_by_id(self, row_ids: list[str]) -> dict[str, dict[str, object]]:
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for row_id in row_ids:
            text = str(row_id or "").strip()
            if text and text not in seen:
                seen.add(text)
                normalized_ids.append(text)
        if not normalized_ids or self._relation_facade is None:
            return {}
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return {}
        try:
            payload = reader(normalized_ids, require_fresh=False, reason="no_oa_bank_batch_detail_relations")
        except TypeError:
            payload = reader(normalized_ids)
        if not isinstance(payload, dict):
            return {}
        rows_by_id: dict[str, dict[str, object]] = {}
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id") or "").strip()
            if row_id:
                rows_by_id[row_id] = row
        return rows_by_id

    def _workbench_relation_active_relations_for_bank_rows(self, bank_rows: list[dict[str, object]]) -> list[dict[str, object]]:
        if self._relation_facade is None:
            return []
        list_by_month = getattr(self._relation_facade, "list_by_month", None)
        if not callable(list_by_month):
            return []
        months = self._months_for_bank_rows(bank_rows)
        relations_by_case_id: dict[str, dict[str, object]] = {}
        for month in months:
            try:
                payload = list_by_month(
                    month,
                    row_types=["bank_transaction"],
                    require_fresh=False,
                    reason="no_oa_bank_batch_build_relations",
                )
            except TypeError:
                payload = list_by_month(month)
            for relation in relation_dicts_from_distribution_payload(payload if isinstance(payload, dict) else {}):
                case_id = str(relation.get("case_id") or "").strip()
                if case_id:
                    relations_by_case_id[case_id] = relation
        return list(relations_by_case_id.values())

    @classmethod
    def _months_for_bank_rows(cls, bank_rows: list[dict[str, object]]) -> list[str]:
        months: list[str] = []
        seen: set[str] = set()
        for row in list(bank_rows or []):
            if not isinstance(row, dict):
                continue
            month = cls._month_from_bank_row(row)
            if month and month not in seen:
                seen.add(month)
                months.append(month)
        return sorted(months)

    @staticmethod
    def _month_from_bank_row(row: dict[str, object]) -> str:
        for key in ("scope_month", "txn_month", "trade_time", "pay_receive_time", "txn_date", "transaction_date", "date"):
            value = str(row.get(key) or "").strip()
            if len(value) >= 7 and re.match(r"^\d{4}-\d{2}", value):
                return value[:7]
        return ""

    @staticmethod
    def _apply_relation_status_to_detail_rows(
        rows: list[dict[str, object]],
        relation_rows_by_id: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        enriched: list[dict[str, object]] = []
        for row in rows:
            next_row = dict(row)
            row_id = str(next_row.get("id") or "").strip()
            relation_row = relation_rows_by_id.get(row_id) if row_id else None
            if relation_row is None:
                next_row.update(
                    {
                        "relation_status": "unlinked",
                        "relation_case_ids": [],
                        "linked_oa_count": 0,
                        "linked_invoice_count": 0,
                    }
                )
            else:
                group_ids = [
                    str(group_id).strip()
                    for group_id in list(relation_row.get("group_ids") or [])
                    if str(group_id).strip()
                ]
                input_invoices = [item for item in list(relation_row.get("linked_input_invoices") or []) if isinstance(item, dict)]
                output_invoices = [item for item in list(relation_row.get("linked_output_invoices") or []) if isinstance(item, dict)]
                linked_oa = [item for item in list(relation_row.get("linked_oa") or []) if isinstance(item, dict)]
                next_row.update(
                    {
                        "relation_status": str(relation_row.get("relation_status") or ("linked" if group_ids else "unlinked")),
                        "relation_case_ids": list(dict.fromkeys(group_ids)),
                        "linked_oa_count": len({str(item.get("id") or item.get("oa_id") or "").strip() for item in linked_oa if str(item.get("id") or item.get("oa_id") or "").strip()}),
                        "linked_invoice_count": len(
                            {
                                str(item.get("id") or item.get("invoice_id") or "").strip()
                                for item in [*input_invoices, *output_invoices]
                                if str(item.get("id") or item.get("invoice_id") or "").strip()
                            }
                        ),
                    }
                )
            enriched.append(next_row)
        return enriched

    def no_oa_bank_batch_stale_reasons(self, batches: object) -> list[str]:
        batch_rows = batches if isinstance(batches, list) else []
        if not batch_rows:
            return []
        expected = require_expected_source_versions(
            self.no_oa_bank_batch_source_versions(),
            context="no_oa_bank_batch_read_model",
        )
        reasons: list[str] = []
        for batch in batch_rows:
            if not isinstance(batch, dict):
                continue
            source_versions = batch.get("source_versions")
            for reason in source_version_mismatch_reasons(
                expected=expected,
                actual=source_versions if isinstance(source_versions, dict) else {},
            ):
                if reason not in reasons:
                    reasons.append(reason)
        return reasons

    def after_mutation(
        self,
        affected_months: list[str],
        *,
        changed_case_ids: list[str],
        persist: bool,
        action_name: str | None = None,
    ) -> bool:
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if SEARCH_MONTH_RE.match(str(month).strip())
        ]
        scope_keys = ["all", *normalized_months]
        self._execute_derived_data_lifecycle_event(
            "no_oa_bank_batch_changed",
            months=normalized_months,
            metadata={
                "source": "no_oa_bank_batch",
                **({"action_name": str(action_name).strip()} if str(action_name or "").strip() else {}),
            },
            schedule_cost_warmup=False,
        )
        if persist:
            self.persist_mutation(
                changed_case_ids=changed_case_ids,
                changed_scope_keys=self._expand_workbench_read_model_scope_keys_for_base_scopes(scope_keys),
            )
        return bool(normalized_months)

    def enqueue_background_refresh(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        if self._read_model_refresh_producer is not None:
            if metadata:
                return bool(self._read_model_refresh_producer.enqueue(scope_keys, reason=reason, metadata=metadata))
            return bool(self._read_model_refresh_producer.enqueue(scope_keys, reason=reason))
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        return bool(
            refresh_gateway.enqueue_many(
                self._read_model_key_from_refresh_metadata(metadata),
                scope_keys,
                reason=reason,
                metadata=metadata,
            )
        )

    @staticmethod
    def _read_model_key_from_refresh_metadata(metadata: dict[str, object] | None) -> str:
        payload = metadata if isinstance(metadata, dict) else {}
        relation_mode = str(payload.get("relation_mode") or "").strip()
        action_name = str(payload.get("action_name") or "").strip()
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE or action_name.startswith("bank_flow_rule_batch"):
            return BANK_FLOW_RULE_BATCH_RELATION_MODE
        return "no_oa_bank_batch"

    def persist_mutation(self, *, changed_case_ids: list[str], changed_scope_keys: list[str]) -> None:
        if self._state_store is None:
            return
        try:
            self._search_cache_clearer()
            save_mutation = getattr(self._state_store, "save_no_oa_bank_batch_mutation", None)
            if not callable(save_mutation):
                raise RuntimeError("No-OA mutation persistence requires save_no_oa_bank_batch_mutation.")
            save_mutation(
                pair_relation_snapshot=self._pair_relation_snapshot_port.snapshot_case_ids(changed_case_ids)
                if changed_case_ids
                else self._pair_relation_snapshot_port.snapshot(),
                no_oa_bank_batch_snapshot=self._no_oa_public_snapshot(),
                workbench_read_model_snapshot=self._workbench_read_model_service.snapshot(),
                changed_case_ids=changed_case_ids,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            raise NoOaBankBatchPersistenceError(str(exc)) from exc

    def _no_oa_public_snapshot(self) -> dict[str, object]:
        public_snapshot = getattr(self._no_oa_bank_batch_service, "public_snapshot", None)
        if callable(public_snapshot):
            return public_snapshot()
        snapshot = getattr(self._no_oa_bank_batch_service, "snapshot", None)
        if callable(snapshot):
            return snapshot()
        return {"batches": {}}

    def _mutation_result(
        self,
        batch: dict[str, object],
        *,
        status: str,
        persist: bool,
        read_model_key: str = "no_oa_bank_batch",
    ) -> dict[str, object]:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        relation = self.pair_relation_snapshot_by_case_id(relation_case_id)
        affected_months = self.affected_months(batch)
        action_name_by_status = (
            {
                "submitted": "bank_flow_rule_batch_submit",
                "withdrawn": "bank_flow_rule_batch_withdraw",
            }
            if read_model_key == BANK_FLOW_RULE_BATCH_RELATION_MODE
            else {
                "submitted": "no_oa_bank_batch_submit",
                "withdrawn": "no_oa_bank_batch_withdraw",
            }
        )
        action_name = action_name_by_status.get(str(status or "").strip())
        workbench_rebuild_queued = self.after_mutation(
            affected_months,
            changed_case_ids=[relation_case_id] if relation_case_id else [],
            persist=persist,
            action_name=action_name,
        )
        return {
            "batch": self.resolve_labels([batch])[0],
            "pair_relation": relation or {},
            "affected_months": affected_months,
            **write_target_envelope(
                read_model_key=read_model_key,
                scope_keys=affected_months,
                fallback_scope_key="all",
            ),
            "workbench_rebuild_queued": workbench_rebuild_queued,
            "results": [{"batch_id": batch.get("batch_id"), "status": status}],
        }

    def affected_months(self, batch: dict[str, object]) -> list[str]:
        months = {
            str(batch.get("scope_month") or "").strip(),
            *self._bank_transaction_category_affected_months_provider(
                [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id).strip()]
            ),
        }
        return sorted(month for month in months if SEARCH_MONTH_RE.match(month))

    def pair_relation_snapshot_by_case_id(self, case_id: str) -> dict[str, object] | None:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            return None
        return self._pair_relation_snapshot_port.snapshot_by_case_id(normalized_case_id)

    def _validate_internal_transfer_selection(
        self,
        *,
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
        row_ids: list[str],
    ) -> None:
        rows_by_id = {
            str(row.get("id") or "").strip(): row
            for row in bank_rows
            if str(row.get("id") or "").strip()
        }
        selected_rows = [
            rows_by_id.get(str(row_id).strip())
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        if not selected_rows or any(row is None for row in selected_rows):
            return
        batch_types = {
            NoOaBankBatchService._category_code(row, categories_by_transaction_id)
            for row in selected_rows
            if isinstance(row, dict)
        }
        batch_types.discard("")
        if "internal_transfer" not in batch_types:
            return
        if len(batch_types) != 1:
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")
        refreshed = self._no_oa_bank_batch_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            self._workbench_relation_active_relations_for_bank_rows(bank_rows),
            self.no_oa_bank_batch_source_versions(),
            eligible_batch_types=self.selected_tag_codes(),
        )
        selected_set = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        matching_drafts = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and str(batch.get("status") or "") == "draft"
            and set(str(item) for item in list(batch.get("row_ids") or [])) == selected_set
        ]
        if matching_drafts:
            return
        conflict_batches = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and selected_set.intersection(str(item) for item in list(batch.get("row_ids") or []))
        ]
        if conflict_batches:
            conflict_codes = {
                str(batch.get("conflict_code") or "").strip()
                for batch in conflict_batches
                if str(batch.get("conflict_code") or "").strip()
            }
            if "missing_internal_transfer_counterpart" in conflict_codes:
                raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")
        raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")

    def _internal_transfer_batch_for_workbench_rows(
        self,
        *,
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
        row_ids: list[str],
    ) -> dict[str, object]:
        rows_by_id = {
            str(row.get("id") or "").strip(): row
            for row in bank_rows
            if str(row.get("id") or "").strip()
        }
        selected_row_ids = [
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        if not selected_row_ids:
            raise ValueError("no_oa_bank_batch_selection_empty")
        if len(set(selected_row_ids)) != len(selected_row_ids):
            raise ValueError("no_oa_bank_batch_selection_duplicate_rows")
        selected_rows = [rows_by_id.get(row_id) for row_id in selected_row_ids]
        if any(row is None for row in selected_rows):
            raise ValueError("no_oa_bank_batch_selection_unknown_row")
        batch_types = [
            NoOaBankBatchService._category_code(row, categories_by_transaction_id)
            for row in selected_rows
            if isinstance(row, dict)
        ]
        if not batch_types or any(batch_type != "internal_transfer" for batch_type in batch_types):
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")

        refreshed = self._no_oa_bank_batch_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            self._workbench_relation_active_relations_for_bank_rows(bank_rows),
            self.no_oa_bank_batch_source_versions(),
            eligible_batch_types=self.selected_tag_codes(),
        )
        selected_set = set(selected_row_ids)
        matching_drafts = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and str(batch.get("status") or "") == "draft"
            and set(str(item) for item in list(batch.get("row_ids") or [])) == selected_set
        ]
        if matching_drafts:
            return dict(matching_drafts[0])
        matching_submitted = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and str(batch.get("status") or "") == "submitted"
            and set(str(item) for item in list(batch.get("row_ids") or [])) == selected_set
        ]
        if matching_submitted:
            return dict(matching_submitted[0])

        conflict_batches = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and selected_set.intersection(str(item) for item in list(batch.get("row_ids") or []))
        ]
        conflict_codes = {
            str(batch.get("conflict_code") or "").strip()
            for batch in conflict_batches
            if str(batch.get("conflict_code") or "").strip()
        }
        if "missing_internal_transfer_counterpart" in conflict_codes:
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")
        if conflict_batches:
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")
        raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")

    def _restore_snapshots(
        self,
        batch_snapshot: dict[str, Any],
        relation_snapshot: dict[str, Any],
    ) -> None:
        restored_batch_service = NoOaBankBatchService.from_snapshot(batch_snapshot)
        self._no_oa_bank_batch_service._batches = deepcopy(restored_batch_service._batches)
        self._no_oa_bank_batch_service._audit_log = deepcopy(restored_batch_service._audit_log)
        self._pair_relation_snapshot_port.restore(relation_snapshot)

    def bank_transaction_tag_definition_current(self, code: str) -> dict[str, object] | None:
        tag_code = str(code or "").strip()
        if not tag_code:
            return None
        payload = self._bank_transaction_category_service.tag_dictionary_payload()
        for definition in list(payload.get("definitions") or []):
            if isinstance(definition, dict) and str(definition.get("code") or "").strip() == tag_code:
                return dict(definition)
        return None

    @staticmethod
    def bank_transaction_tag_label_from_definition(code: str, definition: dict[str, object] | None) -> str:
        if isinstance(definition, dict):
            return str(definition.get("label") or definition.get("output_sub_label") or definition.get("output_primary_label") or code)
        return NO_OA_MANAGED_LABELS.get(code, BANK_TRANSACTION_CATEGORY_LABELS.get(code, code))

    @staticmethod
    def detail_rows(
        row_ids: list[str],
        rows_by_id: dict[str, dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row_id in row_ids:
            source_row = rows_by_id.get(row_id)
            if not isinstance(source_row, dict):
                continue
            row = dict(source_row)
            category = categories_by_transaction_id.get(row_id, {})
            if isinstance(category, dict):
                row["category_code"] = row.get("category_code") or category.get("category_code")
                row["category_label"] = row.get("category_label") or category.get("category_label")
                row["category_primary_label"] = (
                    row.get("category_primary_label")
                    or category.get("category_primary_label")
                    or category.get("effective_category_primary_label")
                )
                row["category_sub_label"] = (
                    row.get("category_sub_label")
                    or category.get("category_sub_label")
                    or category.get("effective_category_sub_label")
                )
                row["category_label_path"] = list(
                    row.get("category_label_path")
                    or category.get("category_label_path")
                    or category.get("effective_category_label_path")
                    or []
                )
                row["category_source"] = row.get("category_source") or category.get("category_source") or category.get("source")
            row.setdefault("category_code", "")
            row.setdefault("category_label", "")
            row.setdefault("category_primary_label", "")
            row.setdefault("category_sub_label", "")
            row.setdefault("category_label_path", [])
            row.setdefault("category_source", "")
            rows.append(row)
        return rows

    @classmethod
    def _apply_submitted_row_tag_snapshot(
        cls,
        batch: dict[str, object],
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not cls._uses_frozen_row_tags(batch):
            return rows
        snapshot = batch.get("row_tag_snapshot")
        if not isinstance(snapshot, dict):
            return rows
        result: list[dict[str, object]] = []
        for row in rows:
            row_id = str(row.get("id") or row.get("transaction_id") or "").strip()
            frozen = snapshot.get(row_id)
            if isinstance(frozen, dict):
                result.append(cls._apply_row_tag_payload(row, frozen))
            else:
                result.append(row)
        return result

    @classmethod
    def _detail_categories_by_transaction_id(
        cls,
        row_ids: list[str],
        categories_by_transaction_id: dict[str, dict[str, object]],
        batch: dict[str, object],
    ) -> dict[str, dict[str, object]]:
        result = {
            row_id: dict(categories_by_transaction_id.get(row_id, {}))
            for row_id in row_ids
        }
        if not cls._uses_frozen_row_tags(batch):
            return result
        snapshot = batch.get("row_tag_snapshot")
        if not isinstance(snapshot, dict):
            return result
        for row_id in row_ids:
            frozen = snapshot.get(row_id)
            if isinstance(frozen, dict):
                result[row_id] = cls._category_from_row_tag_payload(frozen)
        return result

    @staticmethod
    def _uses_frozen_row_tags(batch: dict[str, object]) -> bool:
        return str(batch.get("status") or "").strip() in {"submitted", "withdrawn"}

    @classmethod
    def _apply_row_tag_payload(
        cls,
        row: dict[str, object],
        payload: dict[str, object],
    ) -> dict[str, object]:
        next_row = dict(row)
        category = cls._category_from_row_tag_payload(payload)
        next_row["category_code"] = category.get("category_code", "")
        next_row["category_label"] = category.get("category_label", "")
        next_row["category_primary_label"] = category.get("category_primary_label", "")
        next_row["category_sub_label"] = category.get("category_sub_label", "")
        next_row["category_label_path"] = list(category.get("category_label_path") or [])
        next_row["category_source"] = category.get("category_source", "")
        return next_row

    @staticmethod
    def _category_from_row_tag_payload(payload: dict[str, object]) -> dict[str, object]:
        label_path = payload.get("category_label_path")
        return {
            "transaction_id": str(payload.get("transaction_id") or ""),
            "category_code": str(payload.get("category_code") or ""),
            "category_label": str(payload.get("category_label") or ""),
            "category_primary_label": str(payload.get("category_primary_label") or ""),
            "category_sub_label": str(payload.get("category_sub_label") or ""),
            "category_label_path": [str(item) for item in list(label_path or []) if str(item).strip()] if isinstance(label_path, list) else [],
            "category_source": str(payload.get("category_source") or ""),
            "source": str(payload.get("category_source") or ""),
        }

    @staticmethod
    def _serialize_value(value: object) -> object:
        if is_dataclass(value):
            return {key: NoOaBankBatchApplicationService._serialize_value(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): NoOaBankBatchApplicationService._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [NoOaBankBatchApplicationService._serialize_value(item) for item in value]
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, Enum):
            return value.value
        return value
