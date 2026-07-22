from __future__ import annotations

from datetime import datetime
from time import sleep
from typing import Any, Callable

from fin_ops_platform.domain.models import ProjectMaster
from fin_ops_platform.services.access_control_service import DEFAULT_ADMIN_USERNAME
from fin_ops_platform.services.bank_transaction_category_service import (
    BankAutoTagRulesValidationError,
    BankTransactionCategoryService,
    default_bank_transaction_tag_dictionary_payload,
)
from fin_ops_platform.services.bank_turnover_tag_semantics import (
    EXTERNAL_TURNOVER_ROLE,
    is_external_turnover_definition,
    normalize_turnover_action_type,
)
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    InputInvoiceUsagePaymentRulesValidationError,
    SETTINGS_KEY as INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY,
    normalize_payment_status_rules_settings,
)
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.pending_invoice_rules import (
    PENDING_INVOICE_GROUP_LABELS_BY_DIRECTION,
    active_pending_invoice_rule_tags,
    normalize_pending_invoice_direction,
)
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.state_store_protocol import ApplicationStateStoreProtocol

DEFAULT_OA_RETENTION_CUTOFF_DATE = "2026-01-01"
DEFAULT_OA_INVOICE_OFFSET_APPLICANTS = ["周洁莹"]
DEFAULT_OA_IMPORT_FORM_TYPES = ["payment_request", "expense_claim"]
DEFAULT_OA_IMPORT_STATUSES = ["completed"]
OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED = "disabled"
OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY = "link_existing_only"
OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING = "create_missing"
DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE = OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY
OA_ATTACHMENT_INVOICE_PROMOTION_MODES = {
    OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
    OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
    OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
}
OA_IMPORT_FORM_TYPE_OPTIONS = [
    {"id": "payment_request", "label": "支付申请"},
    {"id": "expense_claim", "label": "日常报销"},
]
OA_IMPORT_STATUS_OPTIONS = [
    {"id": "completed", "label": "已完成"},
    {"id": "in_progress", "label": "进行中"},
]
DEFAULT_WORKBENCH_COLUMN_LAYOUTS = {
    "oa": ["applicant", "projectName", "amount", "counterparty", "reason"],
    "bank": ["counterparty", "amount", "loanRepaymentDate", "note"],
    "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
}
PENDING_INVOICE_TAG_GROUP_LABELS = {
    "requires_invoice": "需要开票",
    "bank_statement_as_invoice": "流水代替发票",
    "no_invoice_required": "无需开票",
}
PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS = PENDING_INVOICE_GROUP_LABELS_BY_DIRECTION["income"]
DEFAULT_NO_OA_BANK_BATCH_TAG_SELECTION = {
    "version": 1,
    "selected_tag_codes": [],
    "requirements_by_tag_code": {},
}
DEFAULT_BANK_FLOW_RULE_BATCH_TAG_RULES = {
    "version": 1,
    "selected_tag_codes": [],
    "requirements_by_tag_code": {},
}
DEFAULT_TURNOVER_LEDGER_TAG_SELECTION = {
    "version": 1,
    "selected_tag_codes": None,
}
COST_STATISTICS_UNCATEGORIZED_TAG_CODE = "__uncategorized__"
COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION = 2
DEFAULT_COST_STATISTICS_TAG_SELECTION = {
    "version": 1,
    "selection_schema_version": COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION,
    "selected_tag_codes": None,
}


class AppSettingsValidationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class BankAutoTagRulesPersistenceError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class AppSettingsService:
    def __init__(
        self,
        state_store: ApplicationStateStoreProtocol | None,
        project_costing_service: ProjectCostingService,
        oa_role_sync_service: OARoleSyncService | None = None,
        oa_import_options_provider: Callable[[], dict[str, Any]] | None = None,
        bank_transaction_category_service: BankTransactionCategoryService | None = None,
        bank_transaction_auto_category_service: Any | None = None,
        audit_service: Any | None = None,
    ) -> None:
        self._state_store = state_store
        self._project_costing_service = project_costing_service
        self._oa_role_sync_service = oa_role_sync_service
        self._oa_import_options_provider = oa_import_options_provider
        self._bank_transaction_category_service = bank_transaction_category_service
        self._bank_transaction_auto_category_service = bank_transaction_auto_category_service
        self._audit_service = audit_service
        self._snapshot = self._normalize_settings(
            state_store.load_app_settings() if state_store is not None else {},
            validate_pending_invoice_tag_groups=False,
        )
        self._configure_category_service(self._snapshot)
        self._restore_manual_projects()

    def _refresh_snapshot_from_state_store(self) -> None:
        if self._state_store is None:
            return
        loaded_settings = self._state_store.load_app_settings()
        normalized_snapshot = self._normalize_settings(
            loaded_settings,
            validate_pending_invoice_tag_groups=False,
        )
        if normalized_snapshot == self._snapshot:
            return
        self._snapshot = normalized_snapshot
        self._configure_category_service(normalized_snapshot)
        self._restore_manual_projects()

    def get_settings_payload(self) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        completed_ids = set(self._snapshot["completed_project_ids"])
        manual_project_ids = {
            str(project["id"])
            for project in self._snapshot["manual_projects"]
        }
        active_projects: list[dict[str, Any]] = []
        completed_projects: list[dict[str, Any]] = []
        for project in self._list_known_projects():
            payload = {
                "id": project.id,
                "project_code": project.project_code,
                "project_name": project.project_name,
                "project_status": "completed" if project.id in completed_ids else "active",
                "source": "manual" if project.id in manual_project_ids else "oa",
                "department_name": project.department_name,
                "owner_name": project.owner_name,
            }
            if project.id in completed_ids:
                completed_projects.append(payload)
            else:
                active_projects.append(payload)

        mappings = sorted(
            self._snapshot["bank_account_mappings"],
            key=lambda item: (item["bank_name"], item["last4"]),
        )
        oa_import_options = self._oa_import_available_options()
        return {
            "projects": {
                "active": active_projects,
                "completed": completed_projects,
                "completed_project_ids": sorted(completed_ids),
            },
            "bank_account_mappings": mappings,
            "access_control": {
                "allowed_usernames": list(self._snapshot["allowed_usernames"]),
                "readonly_export_usernames": list(self._snapshot["readonly_export_usernames"]),
                "admin_usernames": list(self._snapshot["admin_usernames"]),
                "full_access_usernames": list(self._snapshot["full_access_usernames"]),
            },
            "workbench_column_layouts": {
                pane_id: list(self._snapshot["workbench_column_layouts"][pane_id])
                for pane_id in ("oa", "bank", "invoice")
            },
            "oa_retention": {
                "cutoff_date": self._snapshot["oa_retention"]["cutoff_date"],
            },
            "oa_import": {
                "form_types": list(self._snapshot["oa_import"]["form_types"]),
                "statuses": list(self._snapshot["oa_import"]["statuses"]),
                "attachment_invoice_promotion_mode": self._snapshot["oa_import"]["attachment_invoice_promotion_mode"],
                "available_form_types": oa_import_options["available_form_types"],
                "available_statuses": oa_import_options["available_statuses"],
            },
            "oa_invoice_offset": {
                "applicant_names": list(self._snapshot["oa_invoice_offset"]["applicant_names"]),
            },
            "bank_transaction_tags": self._public_bank_transaction_tags(self._snapshot["bank_transaction_tags"]),
            "no_oa_bank_batch_tag_selection": self._public_no_oa_bank_batch_tag_selection(
                self._snapshot["no_oa_bank_batch_tag_selection"],
                bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            ),
            "bank_flow_rule_batch_tag_rules": self._public_bank_transaction_paired_policy(
                self._snapshot["bank_flow_rule_batch_tag_rules"],
                bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            ),
            "turnover_ledger_tag_selection": self._public_turnover_ledger_tag_selection(
                self._snapshot["turnover_ledger_tag_selection"],
                bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            ),
            "cost_statistics_tag_selection": self._public_cost_statistics_tag_selection(
                self._snapshot["cost_statistics_tag_selection"],
                bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            ),
            "pending_invoice_tag_groups": self._public_pending_invoice_tag_groups(
                self._snapshot["pending_invoice_tag_groups"],
                version=int(self._snapshot["pending_invoice_tag_groups"].get("version") or 1),
                group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
            ),
            "pending_output_invoice_tag_groups": self._public_pending_invoice_tag_groups(
                self._snapshot["pending_output_invoice_tag_groups"],
                version=int(self._snapshot["pending_output_invoice_tag_groups"].get("version") or 1),
                group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
            ),
            INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY: self.get_input_invoice_usage_payment_status_rules_payload(
                can_save=True,
            ),
        }

    def get_pending_invoice_settings_payload(self) -> dict[str, Any]:
        payload = self.get_settings_payload()
        payload["pending_invoice_available_tags_expense"] = active_pending_invoice_rule_tags(
            self._snapshot["bank_transaction_tags"],
            direction="expense",
        )
        payload["pending_invoice_available_tags_income"] = active_pending_invoice_rule_tags(
            self._snapshot["bank_transaction_tags"],
            direction="income",
        )
        payload["pending_invoice_available_tags"] = payload["pending_invoice_available_tags_expense"]
        return payload

    def update_settings(
        self,
        *,
        completed_project_ids: list[str],
        bank_account_mappings: list[dict[str, Any]],
        allowed_usernames: list[str],
        readonly_export_usernames: list[str] | None = None,
        admin_usernames: list[str] | None = None,
        workbench_column_layouts: dict[str, Any] | None = None,
        oa_retention: dict[str, Any] | None = None,
        oa_import: dict[str, Any] | None = None,
        oa_invoice_offset: dict[str, Any] | None = None,
        manual_projects: list[dict[str, Any]] | None = None,
        pending_invoice_tag_groups: dict[str, Any] | None = None,
        pending_output_invoice_tag_groups: dict[str, Any] | None = None,
        actor_id: str | None = None,
        after_bank_transaction_tag_settings_saved: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        previous_snapshot = dict(self._snapshot)
        normalized_snapshot = self._normalize_settings(
            {
                "completed_project_ids": completed_project_ids,
                "bank_account_mappings": bank_account_mappings,
                "allowed_usernames": allowed_usernames,
                "readonly_export_usernames": readonly_export_usernames or [],
                "admin_usernames": admin_usernames or [],
                "workbench_column_layouts": workbench_column_layouts or {},
                "oa_retention": oa_retention or {},
                "oa_import": (
                    oa_import
                    if oa_import is not None
                    else self._snapshot.get("oa_import", {})
                ),
                "oa_invoice_offset": oa_invoice_offset or {},
                "manual_projects": (
                    manual_projects
                    if manual_projects is not None
                    else self._snapshot.get("manual_projects", [])
                ),
                "synced_projects": self._snapshot.get("synced_projects", []),
                "bank_transaction_tags": self._snapshot.get("bank_transaction_tags", {}),
                "pending_invoice_tag_groups": (
                    pending_invoice_tag_groups
                    if pending_invoice_tag_groups is not None
                    else self._snapshot.get("pending_invoice_tag_groups", {})
                ),
                "pending_output_invoice_tag_groups": (
                    pending_output_invoice_tag_groups
                    if pending_output_invoice_tag_groups is not None
                    else self._snapshot.get("pending_output_invoice_tag_groups", {})
                ),
                "no_oa_bank_batch_tag_selection": self._snapshot.get("no_oa_bank_batch_tag_selection", {}),
                "bank_flow_rule_batch_tag_rules": self._snapshot.get("bank_flow_rule_batch_tag_rules", {}),
                "turnover_ledger_tag_selection": self._snapshot.get("turnover_ledger_tag_selection", {}),
                "cost_statistics_tag_selection": self._snapshot.get("cost_statistics_tag_selection", {}),
                INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY: self._snapshot.get(
                    INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY,
                    {},
                ),
            },
            validate_pending_invoice_tag_groups=True,
        )
        tag_settings_event = self._prepare_tag_settings_event(
            previous_snapshot,
            normalized_snapshot,
            actor_id=actor_id,
        )
        if tag_settings_event is not None:
            self._apply_tag_settings_versions(previous_snapshot, normalized_snapshot, tag_settings_event)
        if self._oa_role_sync_service is not None:
            self._oa_role_sync_service.sync_access_control(normalized_snapshot)
        try:
            if self._state_store is not None:
                self._state_store.save_app_settings(normalized_snapshot)
        except Exception:
            if self._oa_role_sync_service is not None:
                self._oa_role_sync_service.sync_access_control(previous_snapshot)
            raise
        self._snapshot = normalized_snapshot
        self._configure_category_service(normalized_snapshot)
        if tag_settings_event is not None:
            self._record_tag_settings_audit(tag_settings_event)
            if after_bank_transaction_tag_settings_saved is not None:
                after_bank_transaction_tag_settings_saved(dict(tag_settings_event))
        self._restore_manual_projects()
        return self.get_settings_payload()

    def update_pending_invoice_rule_groups(
        self,
        *,
        direction: str,
        editable_groups: dict[str, Any],
        expected_version: int | None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        previous_snapshot = dict(self._snapshot)
        normalized_direction = normalize_pending_invoice_direction(direction)
        settings_key = (
            "pending_output_invoice_tag_groups"
            if normalized_direction == "income"
            else "pending_invoice_tag_groups"
        )
        group_labels = (
            PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS
            if normalized_direction == "income"
            else PENDING_INVOICE_TAG_GROUP_LABELS
        )
        previous_groups = previous_snapshot[settings_key]
        previous_version = int(previous_groups.get("version") or 1)
        if expected_version is not None and int(expected_version) != previous_version:
            raise AppSettingsValidationError(
                f"{settings_key}_version_conflict",
                "Pending invoice rule settings version conflict.",
            )
        raw_groups = dict(editable_groups if isinstance(editable_groups, dict) else {})
        raw_groups.setdefault("version", previous_version)
        normalized_groups = self._normalize_pending_invoice_tag_groups(
            raw_groups,
            bank_transaction_tags=previous_snapshot["bank_transaction_tags"],
            validate=True,
            group_labels=group_labels,
        )
        affected_groups = self._affected_pending_invoice_groups(
            previous_groups,
            normalized_groups,
            group_labels=group_labels,
        )
        if not affected_groups:
            return {
                "settings": self.get_settings_payload(),
                "event": None,
            }
        new_version = previous_version + 1
        normalized_groups["version"] = new_version
        normalized_snapshot = {
            **previous_snapshot,
            settings_key: normalized_groups,
        }
        if self._state_store is not None:
            self._state_store.save_app_settings(normalized_snapshot)
        self._snapshot = normalized_snapshot
        self._configure_category_service(normalized_snapshot)
        self._restore_manual_projects()
        event = {
            "event_type": "pending_invoice_rules_changed",
            "actor_id": str(actor_id or "pending_invoice_rules").strip() or "pending_invoice_rules",
            "direction": normalized_direction,
            "settings_key": settings_key,
            "old_version": previous_version,
            "new_version": new_version,
            "affected_groups": [
                f"income:{group_id}" if normalized_direction == "income" else group_id
                for group_id in affected_groups
            ],
            "before_summary": self._tag_settings_summary(previous_snapshot),
            "after_summary": self._tag_settings_summary(normalized_snapshot),
        }
        self._record_pending_invoice_rules_audit(event)
        return {
            "settings": self.get_settings_payload(),
            "event": event,
        }

    def get_bank_auto_tag_rules_payload(
        self,
        *,
        can_save: bool = True,
        read_model_status: str | None = None,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return BankTransactionCategoryService.auto_tag_rules_payload(
            self._snapshot["bank_transaction_tags"],
            can_save=can_save,
            read_model_status=read_model_status,
        )

    def update_bank_auto_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        previous_snapshot = dict(self._snapshot)
        previous_tags = previous_snapshot["bank_transaction_tags"]
        normalized = BankTransactionCategoryService.normalize_auto_tag_rules_update(
            payload,
            previous_tag_dictionary=previous_tags,
        )
        next_tags = normalized["tag_dictionary"]
        next_pending_invoice_groups, detached_pending_invoice_references = self._detach_pending_invoice_tag_references(
            previous_snapshot["pending_invoice_tag_groups"],
            tag_codes=set(normalized["changes"].get("archived_codes") or []),
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        next_pending_output_invoice_groups, detached_pending_output_invoice_references = self._detach_pending_invoice_tag_references(
            previous_snapshot["pending_output_invoice_tag_groups"],
            tag_codes=set(normalized["changes"].get("archived_codes") or []),
            group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
        )
        next_no_oa_selection, detached_no_oa_references = self._detach_bank_transaction_requirement_rule_references(
            previous_snapshot["no_oa_bank_batch_tag_selection"],
            tag_codes=set(normalized["changes"].get("archived_codes") or []),
            include_selected_tag_codes=True,
        )
        next_bank_flow_rule_batch_tag_rules, detached_bank_flow_rule_batch_references = (
            self._detach_bank_transaction_requirement_rule_references(
                previous_snapshot["bank_flow_rule_batch_tag_rules"],
                tag_codes=set(normalized["changes"].get("archived_codes") or []),
                include_selected_tag_codes=False,
            )
        )
        next_turnover_selection, detached_turnover_references = self._detach_turnover_ledger_tag_references(
            previous_snapshot["turnover_ledger_tag_selection"],
            tag_codes=set(normalized["changes"].get("archived_codes") or []),
        )
        next_cost_statistics_selection, detached_cost_statistics_references = self._detach_cost_statistics_tag_references(
            previous_snapshot["cost_statistics_tag_selection"],
            tag_codes=set(normalized["changes"].get("archived_codes") or []),
        )
        if (
            not normalized["changes"]["changed"]
            and not detached_pending_invoice_references
            and not detached_pending_output_invoice_references
            and not detached_no_oa_references
            and not detached_bank_flow_rule_batch_references
            and not detached_turnover_references
            and not detached_cost_statistics_references
        ):
            return self.get_bank_auto_tag_rules_payload(can_save=True)

        next_snapshot = dict(self._snapshot)
        next_snapshot["bank_transaction_tags"] = next_tags
        next_snapshot["pending_invoice_tag_groups"] = {
            **next_pending_invoice_groups,
            "version": (
                int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1) + 1
                if detached_pending_invoice_references
                else int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1)
            ),
        }
        next_snapshot["pending_output_invoice_tag_groups"] = {
            **next_pending_output_invoice_groups,
            "version": (
                int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1) + 1
                if detached_pending_output_invoice_references
                else int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1)
            ),
        }
        next_snapshot["no_oa_bank_batch_tag_selection"] = next_no_oa_selection
        next_snapshot["bank_flow_rule_batch_tag_rules"] = next_bank_flow_rule_batch_tag_rules
        next_snapshot["turnover_ledger_tag_selection"] = next_turnover_selection
        next_snapshot["cost_statistics_tag_selection"] = next_cost_statistics_selection
        saved_snapshot = self._save_and_verify_bank_auto_tag_rules_snapshot(next_snapshot)
        self._snapshot = saved_snapshot
        self._configure_category_service(saved_snapshot)
        event = {
            "actor_id": str(actor_id or "bank_auto_tag_rules").strip() or "bank_auto_tag_rules",
            "old_version": int(normalized["old_version"]),
            "new_version": int(normalized["new_version"]),
            **normalized["changes"],
            "detached_pending_invoice_tag_references": detached_pending_invoice_references,
            "detached_pending_output_invoice_tag_references": detached_pending_output_invoice_references,
            "detached_no_oa_bank_batch_tag_references": detached_no_oa_references,
            "detached_bank_flow_rule_batch_tag_rule_references": detached_bank_flow_rule_batch_references,
            "detached_turnover_ledger_tag_references": detached_turnover_references,
            "detached_cost_statistics_tag_references": detached_cost_statistics_references,
        }
        self._record_bank_auto_tag_rules_audit(event)
        return self.get_bank_auto_tag_rules_payload(can_save=True)

    def replace_bank_auto_tag_rules_from_file_source(
        self,
        source: Any,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        previous_snapshot = dict(self._snapshot)
        normalized = BankTransactionCategoryService.normalize_auto_tag_rules_file_replacement(
            source,
            previous_tag_dictionary=previous_snapshot["bank_transaction_tags"],
        )
        next_tags = normalized["tag_dictionary"]
        archived_codes = set(normalized["changes"].get("archived_codes") or [])
        next_pending_invoice_groups, detached_pending_invoice_references = self._detach_pending_invoice_tag_references(
            previous_snapshot["pending_invoice_tag_groups"],
            tag_codes=archived_codes,
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        next_pending_output_invoice_groups, detached_pending_output_invoice_references = self._detach_pending_invoice_tag_references(
            previous_snapshot["pending_output_invoice_tag_groups"],
            tag_codes=archived_codes,
            group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
        )
        next_no_oa_selection, detached_no_oa_references = self._detach_bank_transaction_requirement_rule_references(
            previous_snapshot["no_oa_bank_batch_tag_selection"],
            tag_codes=archived_codes,
            include_selected_tag_codes=True,
        )
        next_bank_flow_rule_batch_tag_rules, detached_bank_flow_rule_batch_references = (
            self._detach_bank_transaction_requirement_rule_references(
                previous_snapshot["bank_flow_rule_batch_tag_rules"],
                tag_codes=archived_codes,
                include_selected_tag_codes=False,
            )
        )
        next_turnover_selection, detached_turnover_references = self._detach_turnover_ledger_tag_references(
            previous_snapshot["turnover_ledger_tag_selection"],
            tag_codes=archived_codes,
        )
        next_cost_statistics_selection, detached_cost_statistics_references = self._detach_cost_statistics_tag_references(
            previous_snapshot["cost_statistics_tag_selection"],
            tag_codes=archived_codes,
        )
        if (
            not normalized["changes"]["changed"]
            and not detached_pending_invoice_references
            and not detached_pending_output_invoice_references
            and not detached_no_oa_references
            and not detached_bank_flow_rule_batch_references
            and not detached_turnover_references
            and not detached_cost_statistics_references
        ):
            return self.get_bank_auto_tag_rules_payload(can_save=True)

        next_snapshot = dict(self._snapshot)
        next_snapshot["bank_transaction_tags"] = next_tags
        next_snapshot["pending_invoice_tag_groups"] = {
            **next_pending_invoice_groups,
            "version": (
                int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1) + 1
                if detached_pending_invoice_references
                else int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1)
            ),
        }
        next_snapshot["pending_output_invoice_tag_groups"] = {
            **next_pending_output_invoice_groups,
            "version": (
                int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1) + 1
                if detached_pending_output_invoice_references
                else int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1)
            ),
        }
        next_snapshot["no_oa_bank_batch_tag_selection"] = next_no_oa_selection
        next_snapshot["bank_flow_rule_batch_tag_rules"] = next_bank_flow_rule_batch_tag_rules
        next_snapshot["turnover_ledger_tag_selection"] = next_turnover_selection
        next_snapshot["cost_statistics_tag_selection"] = next_cost_statistics_selection
        saved_snapshot = self._save_and_verify_bank_auto_tag_rules_snapshot(next_snapshot)
        self._snapshot = saved_snapshot
        self._configure_category_service(saved_snapshot)
        event = {
            "actor_id": str(actor_id or "bank_auto_tag_rules").strip() or "bank_auto_tag_rules",
            "old_version": int(normalized["old_version"]),
            "new_version": int(normalized["new_version"]),
            **normalized["changes"],
            "detached_pending_invoice_tag_references": detached_pending_invoice_references,
            "detached_pending_output_invoice_tag_references": detached_pending_output_invoice_references,
            "detached_no_oa_bank_batch_tag_references": detached_no_oa_references,
            "detached_bank_flow_rule_batch_tag_rule_references": detached_bank_flow_rule_batch_references,
            "detached_turnover_ledger_tag_references": detached_turnover_references,
            "detached_cost_statistics_tag_references": detached_cost_statistics_references,
        }
        self._record_bank_auto_tag_rules_audit(event)
        return self.get_bank_auto_tag_rules_payload(can_save=True)

    def get_no_oa_bank_batch_tag_selection_payload(self) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return self._public_no_oa_bank_batch_tag_selection(
            self._snapshot["no_oa_bank_batch_tag_selection"],
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
        )

    def get_bank_flow_rule_batch_tag_rules_payload(self) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return self._public_bank_transaction_paired_policy(
            self._snapshot["bank_flow_rule_batch_tag_rules"],
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
        )

    def update_no_oa_bank_batch_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        current = self._snapshot["no_oa_bank_batch_tag_selection"]
        requested_version = BankTransactionCategoryService._normalize_version(
            payload.get("expected_version", payload.get("version", 0))
        )
        if requested_version != int(current.get("version") or 1):
            raise AppSettingsValidationError(
                "no_oa_bank_batch_tag_selection_version_conflict",
                "No-OA bank batch tag selection version conflict.",
            )
        next_selection = self._normalize_bank_transaction_requirement_rules(
            {
                "version": int(current.get("version") or 1) + 1,
                "selected_tag_codes": payload.get("selected_tag_codes"),
                "rules": payload.get("rules"),
                "requirements_by_tag_code": payload.get("requirements_by_tag_code"),
            },
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
            include_selected_tag_codes=True,
        )
        next_snapshot = dict(self._snapshot)
        next_snapshot["no_oa_bank_batch_tag_selection"] = next_selection
        if self._state_store is not None:
            self._state_store.save_app_settings(next_snapshot)
        self._snapshot = next_snapshot
        self._configure_category_service(next_snapshot)
        self._record_no_oa_bank_batch_tag_selection_audit(
            {
                "actor_id": actor_id,
                "old_version": int(current.get("version") or 1),
                "new_version": int(next_selection.get("version") or 1),
                "old_selected_tag_codes": list(current.get("selected_tag_codes") or []),
                "new_selected_tag_codes": list(next_selection.get("selected_tag_codes") or []),
                "old_rules": dict(current.get("requirements_by_tag_code") or {}),
                "new_rules": dict(next_selection.get("requirements_by_tag_code") or {}),
            }
        )
        return self.get_no_oa_bank_batch_tag_selection_payload()

    def update_bank_flow_rule_batch_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        normalized = self.normalize_bank_flow_rule_batch_tag_rules_update(
            payload,
            actor_id=actor_id,
        )
        if not bool(normalized["changed"]):
            return dict(normalized["public_payload"])
        self._save_snapshot(dict(normalized["next_snapshot"]))
        self._record_bank_flow_rule_batch_tag_rules_audit(dict(normalized["audit_event"]))
        return dict(normalized["public_payload"])

    def normalize_bank_flow_rule_batch_tag_rules_update(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        """Validate one rule update without mutating settings or enqueueing work."""
        self._refresh_snapshot_from_state_store()
        if "selected_tag_codes" in payload or "selectedTagCodes" in payload:
            raise AppSettingsValidationError(
                "bank_flow_rule_batch_selected_tag_codes_forbidden",
                "Bank flow rule batch tag rules must be updated with rules.",
            )
        self._assert_unique_bank_flow_rule_batch_rule_codes(payload)
        current = self._snapshot["bank_flow_rule_batch_tag_rules"]
        requested_version = BankTransactionCategoryService._normalize_version(
            payload.get("expected_version", payload.get("version", 0))
        )
        if requested_version != int(current.get("version") or 1):
            raise AppSettingsValidationError(
                "bank_flow_rule_batch_tag_rules_version_conflict",
                "Bank flow rule batch tag rules version conflict.",
            )
        next_rules = self._normalize_bank_transaction_requirement_rules(
            {
                "version": int(current.get("version") or 1) + 1,
                "rules": payload.get("rules"),
                "requirements_by_tag_code": payload.get("requirements_by_tag_code"),
            },
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
            include_selected_tag_codes=False,
        )
        current_public = self._public_bank_transaction_paired_policy(
            current,
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
        )
        next_public = self._public_bank_transaction_paired_policy(
            next_rules,
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
        )
        if dict(next_public.get("requirements_by_tag_code") or {}) == dict(
            current_public.get("requirements_by_tag_code") or {}
        ):
            return {
                "changed": False,
                "previous_snapshot": dict(self._snapshot),
                "next_snapshot": dict(self._snapshot),
                "audit_event": {},
                "previous_public_payload": dict(current_public),
                "public_payload": dict(current_public),
            }
        next_snapshot = dict(self._snapshot)
        next_snapshot["bank_flow_rule_batch_tag_rules"] = next_rules
        return {
            "changed": True,
            "previous_snapshot": dict(self._snapshot),
            "next_snapshot": next_snapshot,
            "previous_public_payload": dict(current_public),
            "public_payload": dict(next_public),
            "audit_event": {
                "actor_id": actor_id,
                "old_version": int(current.get("version") or 1),
                "new_version": int(next_rules.get("version") or 1),
                "old_rules": dict(current.get("requirements_by_tag_code") or {}),
                "new_rules": dict(next_rules.get("requirements_by_tag_code") or {}),
            },
        }

    def accept_bank_flow_rule_batch_tag_rules_update(
        self,
        *,
        next_snapshot: dict[str, Any],
        audit_event: dict[str, Any],
    ) -> None:
        """Publish a rule update after its durable transaction commits."""
        normalized_snapshot = self._normalize_settings(
            next_snapshot,
            validate_pending_invoice_tag_groups=False,
        )
        self._snapshot = normalized_snapshot
        self._configure_category_service(normalized_snapshot)
        self._restore_manual_projects()
        self._record_bank_flow_rule_batch_tag_rules_audit(dict(audit_event))

    @staticmethod
    def _assert_unique_bank_flow_rule_batch_rule_codes(payload: dict[str, Any]) -> None:
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, list):
            return
        seen: set[str] = set()
        for item in raw_rules:
            if not isinstance(item, dict):
                continue
            tag_code = str(item.get("tag_code") or item.get("code") or "").strip()
            if not tag_code:
                continue
            if tag_code in seen:
                raise AppSettingsValidationError(
                    "duplicate_bank_flow_rule_batch_tag_rule",
                    f"Duplicate bank flow rule batch tag rule: {tag_code}",
                )
            seen.add(tag_code)

    def get_turnover_ledger_tag_selection_payload(self) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return self._public_turnover_ledger_tag_selection(
            self._snapshot["turnover_ledger_tag_selection"],
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
        )

    def get_turnover_ledger_tag_selection_state(self) -> dict[str, Any]:
        """Return the persisted state needed by the local write boundary rollback."""
        self._refresh_snapshot_from_state_store()
        current = self._snapshot["turnover_ledger_tag_selection"]
        return {
            "version": int(current.get("version") or 1),
            "selected_tag_codes": list(current.get("selected_tag_codes") or []),
        }

    def commit_turnover_ledger_tag_selection_update(
        self,
        *,
        next_snapshot: dict[str, Any],
        audit_event: dict[str, Any],
    ) -> None:
        """Persist one normalized turnover-tag update through the Settings owner."""
        self._refresh_snapshot_from_state_store()
        current = self._snapshot["turnover_ledger_tag_selection"]
        expected_version = int(audit_event.get("old_version") or 0)
        if expected_version != int(current.get("version") or 1):
            raise AppSettingsValidationError(
                "turnover_ledger_tag_selection_version_conflict",
                "Turnover ledger tag selection version conflict.",
            )
        next_selection = self._normalize_turnover_ledger_tag_selection(
            dict(next_snapshot.get("turnover_ledger_tag_selection") or {}),
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
        )
        normalized_snapshot = dict(self._snapshot)
        normalized_snapshot["turnover_ledger_tag_selection"] = next_selection
        self._save_snapshot(normalized_snapshot)
        self._record_turnover_ledger_tag_selection_audit(dict(audit_event))

    def restore_turnover_ledger_tag_selection_state(self, previous_state: dict[str, Any]) -> None:
        """Restore only the turnover-tag field after a local transaction failure."""
        self._refresh_snapshot_from_state_store()
        restored_selection = self._normalize_turnover_ledger_tag_selection(
            dict(previous_state),
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
        )
        restored_snapshot = dict(self._snapshot)
        restored_snapshot["turnover_ledger_tag_selection"] = restored_selection
        self._save_snapshot(restored_snapshot)

    def get_input_invoice_usage_payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]:
        provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(
            state_store=self._state_store,
            audit_service=self._audit_service,
        )
        return provider.payment_status_rules_payload(can_save=can_save)

    def update_input_invoice_usage_payment_status_rules(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(
            state_store=self._state_store,
            audit_service=self._audit_service,
        )
        try:
            updated = provider.update_payment_status_rules(
                payload,
                actor_id=actor_id,
            )
        except InputInvoiceUsagePaymentRulesValidationError as exc:
            raise AppSettingsValidationError(exc.error_code, str(exc)) from exc
        self._refresh_snapshot_from_state_store()
        return updated

    def turnover_ledger_selected_tag_codes(self) -> list[str]:
        payload = self.get_turnover_ledger_tag_selection_payload()
        return [
            str(code)
            for code in list(payload.get("selected_tag_codes") or [])
            if str(code).strip()
        ]

    def get_cost_statistics_tag_selection_payload(self, *, can_save: bool = True) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return self.cost_statistics_tag_selection_payload_from_settings(
            self._snapshot,
            can_save=can_save,
        )

    @staticmethod
    def cost_statistics_tag_selection_payload_from_settings(
        settings_payload: dict[str, Any],
        *,
        can_save: bool = False,
    ) -> dict[str, Any]:
        """Map an already-read settings snapshot without performing repository I/O."""

        payload = AppSettingsService._public_cost_statistics_tag_selection(
            settings_payload.get("cost_statistics_tag_selection")
            if isinstance(settings_payload.get("cost_statistics_tag_selection"), dict)
            else {},
            bank_transaction_tags=(
                settings_payload.get("bank_transaction_tags")
                if isinstance(settings_payload.get("bank_transaction_tags"), dict)
                else {}
            ),
        )
        payload["can_save"] = bool(can_save)
        return payload

    def cost_statistics_selected_tag_codes(self) -> list[str]:
        payload = self.get_cost_statistics_tag_selection_payload(can_save=False)
        return [
            str(code)
            for code in list(payload.get("effective_selected_tag_codes") or payload.get("selected_tag_codes") or [])
            if str(code).strip()
        ]

    def update_cost_statistics_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        current = self._snapshot["cost_statistics_tag_selection"]
        requested_version = BankTransactionCategoryService._normalize_version(
            payload.get("expected_version", payload.get("version", 0))
        )
        if requested_version != int(current.get("version") or 1):
            raise AppSettingsValidationError(
                "cost_statistics_tag_selection_version_conflict",
                "Cost statistics tag selection version conflict.",
            )
        next_selection = self._normalize_cost_statistics_tag_selection(
            {
                "version": int(current.get("version") or 1) + 1,
                "selection_schema_version": COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION,
                "selected_tag_codes": payload.get("selected_tag_codes"),
            },
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
        )
        next_snapshot = dict(self._snapshot)
        next_snapshot["cost_statistics_tag_selection"] = next_selection
        if self._state_store is not None:
            self._state_store.save_app_settings(next_snapshot)
        self._snapshot = next_snapshot
        self._configure_category_service(next_snapshot)
        self._record_cost_statistics_tag_selection_audit(
            {
                "actor_id": actor_id,
                "old_version": int(current.get("version") or 1),
                "new_version": int(next_selection.get("version") or 1),
                "old_selected_tag_codes": (
                    None
                    if current.get("selected_tag_codes") is None
                    else list(current.get("selected_tag_codes") or [])
                ),
                "new_selected_tag_codes": (
                    None
                    if next_selection.get("selected_tag_codes") is None
                    else list(next_selection.get("selected_tag_codes") or [])
                ),
            }
        )
        return self.get_cost_statistics_tag_selection_payload(can_save=True)

    def update_turnover_ledger_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        normalized_update = self.normalize_turnover_ledger_tag_selection_update(payload, actor_id=actor_id)
        next_snapshot = dict(normalized_update["next_snapshot"])
        if self._state_store is not None:
            self._state_store.save_app_settings(next_snapshot)
        self._snapshot = next_snapshot
        self._configure_category_service(next_snapshot)
        self._record_turnover_ledger_tag_selection_audit(dict(normalized_update["audit_event"]))
        return self.get_turnover_ledger_tag_selection_payload()

    def normalize_turnover_ledger_tag_selection_update(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        current = self._snapshot["turnover_ledger_tag_selection"]
        requested_version = BankTransactionCategoryService._normalize_version(
            payload.get("expected_version", payload.get("version", 0))
        )
        if requested_version != int(current.get("version") or 1):
            raise AppSettingsValidationError(
                "turnover_ledger_tag_selection_version_conflict",
                "Turnover ledger tag selection version conflict.",
            )
        next_selection = self._normalize_turnover_ledger_tag_selection(
            {
                "version": int(current.get("version") or 1) + 1,
                "selected_tag_codes": payload.get("selected_tag_codes"),
            },
            bank_transaction_tags=self._snapshot["bank_transaction_tags"],
            validate=True,
        )
        next_snapshot = dict(self._snapshot)
        next_snapshot["turnover_ledger_tag_selection"] = next_selection
        audit_event = {
            "actor_id": actor_id,
            "old_version": int(current.get("version") or 1),
            "new_version": int(next_selection.get("version") or 1),
            "old_selected_tag_codes": list(current.get("selected_tag_codes") or []),
            "new_selected_tag_codes": list(next_selection.get("selected_tag_codes") or []),
        }
        return {
            "next_snapshot": next_snapshot,
            "next_selection": dict(next_selection),
            "audit_event": audit_event,
            "public_payload": self._public_turnover_ledger_tag_selection(
                next_selection,
                bank_transaction_tags=next_snapshot["bank_transaction_tags"],
            ),
        }

    def sync_oa_projects(self, *, actor_id: str) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        self._project_costing_service.sync_projects_from_oa(actor_id=actor_id)
        next_snapshot = dict(self._snapshot)
        next_snapshot["synced_projects"] = self._serialize_synced_projects()
        self._save_snapshot(next_snapshot)
        return self.get_settings_payload()

    def create_manual_project(
        self,
        *,
        actor_id: str,
        project_code: str,
        project_name: str,
        department_name: str | None = None,
        owner_name: str | None = None,
    ) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        project = self._project_costing_service.create_project(
            actor_id=actor_id,
            project_code=project_code,
            project_name=project_name,
            project_status="active",
            department_name=department_name,
            owner_name=owner_name,
        )
        next_snapshot = dict(self._snapshot)
        next_snapshot["manual_projects"] = [
            *self._snapshot["manual_projects"],
            self._serialize_project(project),
        ]
        try:
            self._save_snapshot(next_snapshot)
        except Exception:
            self._project_costing_service.delete_manual_project(project.id)
            raise
        return self.get_settings_payload()

    def delete_project(self, project_id: str) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        normalized_project_id = str(project_id).strip()
        next_snapshot = dict(self._snapshot)
        next_snapshot["completed_project_ids"] = [
            item
            for item in self._snapshot["completed_project_ids"]
            if item != normalized_project_id
        ]
        next_snapshot["manual_projects"] = [
            project
            for project in self._snapshot["manual_projects"]
            if project["id"] != normalized_project_id
        ]
        self._save_snapshot(next_snapshot)
        return self.get_settings_payload()

    def _save_snapshot(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = self._normalize_settings(
            snapshot,
            validate_pending_invoice_tag_groups=False,
        )
        if self._state_store is not None:
            self._state_store.save_app_settings(normalized_snapshot)
        self._snapshot = normalized_snapshot
        self._configure_category_service(normalized_snapshot)
        self._restore_manual_projects()

    def _save_and_verify_bank_auto_tag_rules_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized_snapshot = self._normalize_settings(
            snapshot,
            validate_pending_invoice_tag_groups=False,
        )
        if self._state_store is None:
            return normalized_snapshot
        verified_keys = (
            "bank_transaction_tags",
            "pending_invoice_tag_groups",
            "no_oa_bank_batch_tag_selection",
            "bank_flow_rule_batch_tag_rules",
            "turnover_ledger_tag_selection",
            "cost_statistics_tag_selection",
        )
        try:
            self._state_store.save_app_settings(normalized_snapshot)
            for retry_delay in (0.0, 0.05, 0.15):
                if retry_delay:
                    sleep(retry_delay)
                persisted_snapshot = self._normalize_settings(
                    self._state_store.load_app_settings(),
                    validate_pending_invoice_tag_groups=False,
                )
                if all(persisted_snapshot[key] == normalized_snapshot[key] for key in verified_keys):
                    return normalized_snapshot
        except Exception as exc:
            raise BankAutoTagRulesPersistenceError(
                "bank_auto_tag_rules_persistence_failed",
                "自动标签规则保存失败：无法写入持久化设置源，请稍后重试。",
            ) from exc

        raise BankAutoTagRulesPersistenceError(
            "bank_auto_tag_rules_persistence_failed",
            "自动标签规则保存失败：持久化设置源未返回刚写入的规则版本，请稍后重试。",
        )

    def _restore_manual_projects(self) -> None:
        projects = [
            ProjectMaster(
                id=str(project["id"]),
                project_code=str(project["project_code"]),
                project_name=str(project["project_name"]),
                project_status=str(project.get("project_status") or "active"),
                department_name=project.get("department_name"),
                owner_name=project.get("owner_name"),
            )
            for project in self._snapshot["manual_projects"]
        ]
        self._project_costing_service.restore_manual_projects(projects)

    def _list_known_projects(self) -> list[ProjectMaster]:
        live_projects = self._project_costing_service.list_projects()
        known_ids = {project.id for project in live_projects}
        snapshot_projects = [
            self._deserialize_project(project)
            for project in self._snapshot.get("synced_projects", [])
            if str(project.get("id", "")).strip() and str(project.get("id", "")).strip() not in known_ids
        ]
        return [*live_projects, *snapshot_projects]

    def _serialize_synced_projects(self) -> list[dict[str, Any]]:
        manual_project_ids = {
            str(project["id"])
            for project in self._snapshot["manual_projects"]
        }
        return [
            self._serialize_project(project)
            for project in self._project_costing_service.list_projects()
            if project.id not in manual_project_ids
        ]

    @staticmethod
    def _deserialize_project(project: dict[str, Any]) -> ProjectMaster:
        return ProjectMaster(
            id=str(project["id"]),
            project_code=str(project["project_code"]),
            project_name=str(project["project_name"]),
            project_status=str(project.get("project_status") or "active"),
            department_name=project.get("department_name"),
            owner_name=project.get("owner_name"),
        )

    @staticmethod
    def _serialize_project(project: ProjectMaster) -> dict[str, Any]:
        return {
            "id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "project_status": project.project_status,
            "department_name": project.department_name,
            "owner_name": project.owner_name,
        }

    def get_bank_account_mapping_dict(self) -> dict[str, str]:
        self._refresh_snapshot_from_state_store()
        return {
            item["last4"]: item["bank_name"]
            for item in self._snapshot["bank_account_mappings"]
        }

    def get_bank_account_mappings_payload(self) -> list[dict[str, str]]:
        self._refresh_snapshot_from_state_store()
        return [
            {
                "id": str(item.get("id") or ""),
                "last4": str(item.get("last4") or ""),
                "bank_name": str(item.get("bank_name") or ""),
                "short_name": str(item.get("short_name") or ""),
            }
            for item in self._snapshot["bank_account_mappings"]
        ]

    def get_cost_statistics_source_settings_payload(self) -> dict[str, Any]:
        self._refresh_snapshot_from_state_store()
        return {
            "bank_transaction_tags": dict(self._snapshot.get("bank_transaction_tags") or {}),
            "bank_account_mappings": [
                {
                    "id": str(item.get("id") or ""),
                    "last4": str(item.get("last4") or ""),
                    "bank_name": str(item.get("bank_name") or ""),
                    "short_name": str(item.get("short_name") or ""),
                }
                for item in self._snapshot["bank_account_mappings"]
            ],
        }

    def get_completed_project_ids(self) -> set[str]:
        self._refresh_snapshot_from_state_store()
        return set(self._snapshot["completed_project_ids"])

    def is_project_active(self, project_id: str | None, project_name: str) -> bool:
        normalized_project_id = str(project_id or "").strip()
        if normalized_project_id and normalized_project_id in self.get_completed_project_ids():
            return False
        normalized_project_name = str(project_name or "").strip()
        if not normalized_project_name:
            return True
        payload = self.get_settings_payload()["projects"]
        completed_names = {
            str(project.get("project_name", "")).strip()
            for project in list(payload.get("completed") or [])
            if str(project.get("project_name", "")).strip()
        }
        if normalized_project_name in completed_names:
            return False
        return True

    def get_oa_retention_cutoff_date(self) -> str:
        self._refresh_snapshot_from_state_store()
        return str(self._snapshot["oa_retention"]["cutoff_date"])

    def get_oa_import_settings(self) -> dict[str, list[str]]:
        self._refresh_snapshot_from_state_store()
        return {
            "form_types": list(self._snapshot["oa_import"]["form_types"]),
            "statuses": list(self._snapshot["oa_import"]["statuses"]),
        }

    def get_oa_attachment_invoice_promotion_mode(self) -> str:
        self._refresh_snapshot_from_state_store()
        mode = str(
            self._snapshot.get("oa_import", {}).get(
                "attachment_invoice_promotion_mode",
                DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE,
            )
        ).strip()
        if mode not in OA_ATTACHMENT_INVOICE_PROMOTION_MODES:
            return DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE
        return mode

    def _oa_import_available_options(self) -> dict[str, list[dict[str, str]]]:
        default_options = {
            "available_form_types": [dict(item) for item in OA_IMPORT_FORM_TYPE_OPTIONS],
            "available_statuses": [dict(item) for item in OA_IMPORT_STATUS_OPTIONS],
        }
        provider = self._oa_import_options_provider
        if provider is None:
            return default_options
        try:
            raw_options = provider()
        except Exception:
            return default_options
        if not isinstance(raw_options, dict):
            return default_options
        return {
            "available_form_types": self._normalize_available_options(
                raw_options.get("available_form_types"),
                defaults=OA_IMPORT_FORM_TYPE_OPTIONS,
            ),
            "available_statuses": self._normalize_available_options(
                raw_options.get("available_statuses"),
                defaults=OA_IMPORT_STATUS_OPTIONS,
            ),
        }

    def get_oa_invoice_offset_applicant_names(self) -> list[str]:
        self._refresh_snapshot_from_state_store()
        return list(self._snapshot["oa_invoice_offset"]["applicant_names"])

    def get_allowed_usernames(self) -> list[str]:
        self._refresh_snapshot_from_state_store()
        return list(self._snapshot["allowed_usernames"])

    def get_readonly_export_usernames(self) -> list[str]:
        self._refresh_snapshot_from_state_store()
        return list(self._snapshot["readonly_export_usernames"])

    def get_admin_usernames(self) -> list[str]:
        self._refresh_snapshot_from_state_store()
        return list(self._snapshot["admin_usernames"])

    @staticmethod
    def _normalize_username_list(values: list[Any] | None) -> list[str]:
        return sorted(
            {
                str(username).strip()
                for username in list(values or [])
                if str(username).strip()
            }
        )

    @staticmethod
    def normalize_settings_payload(
        payload: dict[str, Any] | None,
        *,
        validate_pending_invoice_tag_groups: bool = False,
    ) -> dict[str, Any]:
        """Return the canonical persisted App settings payload without performing I/O."""
        return AppSettingsService._normalize_settings(
            payload,
            validate_pending_invoice_tag_groups=validate_pending_invoice_tag_groups,
        )

    @staticmethod
    def _normalize_settings(
        payload: dict[str, Any] | None,
        *,
        validate_pending_invoice_tag_groups: bool,
    ) -> dict[str, Any]:
        raw_payload = payload if isinstance(payload, dict) else {}
        completed_ids = sorted(
            {
                str(project_id).strip()
                for project_id in list(raw_payload.get("completed_project_ids") or [])
                if str(project_id).strip()
            }
        )
        mappings: list[dict[str, str]] = []
        seen_last4: set[str] = set()
        for item in list(raw_payload.get("bank_account_mappings") or []):
            if not isinstance(item, dict):
                continue
            last4 = str(item.get("last4", "")).strip()
            bank_name = str(item.get("bank_name", "")).strip()
            short_name = str(item.get("short_name", "")).strip()
            if len(last4) != 4 or not last4.isdigit() or not bank_name:
                continue
            if last4 in seen_last4:
                continue
            seen_last4.add(last4)
            mappings.append(
                {
                    "id": str(item.get("id") or f"bank_mapping_{last4}"),
                    "last4": last4,
                    "bank_name": bank_name,
                    "short_name": short_name,
                }
            )
        admin_usernames = set(
            AppSettingsService._normalize_username_list(raw_payload.get("admin_usernames"))
        )
        admin_usernames.add(DEFAULT_ADMIN_USERNAME)

        allowed_usernames = set(
            AppSettingsService._normalize_username_list(raw_payload.get("allowed_usernames"))
        )
        allowed_usernames.update(admin_usernames)

        readonly_export_usernames = set(
            AppSettingsService._normalize_username_list(raw_payload.get("readonly_export_usernames"))
        )
        readonly_export_usernames.intersection_update(allowed_usernames)
        readonly_export_usernames.difference_update(admin_usernames)

        full_access_usernames = sorted(
            allowed_usernames.difference(readonly_export_usernames).difference(admin_usernames)
        )
        raw_layouts = raw_payload.get("workbench_column_layouts")
        normalized_layouts: dict[str, list[str]] = {}
        for pane_id, default_keys in DEFAULT_WORKBENCH_COLUMN_LAYOUTS.items():
            raw_keys = raw_layouts.get(pane_id) if isinstance(raw_layouts, dict) else None
            ordered_keys: list[str] = []
            if isinstance(raw_keys, list):
                seen_keys: set[str] = set()
                for item in raw_keys:
                    key = str(item).strip()
                    if not key or key in seen_keys or key not in default_keys:
                        continue
                    seen_keys.add(key)
                    ordered_keys.append(key)
            for key in default_keys:
                if key not in ordered_keys:
                    ordered_keys.append(key)
            normalized_layouts[pane_id] = ordered_keys
        raw_oa_retention = raw_payload.get("oa_retention")
        oa_retention = raw_oa_retention if isinstance(raw_oa_retention, dict) else {}
        cutoff_date = str(oa_retention.get("cutoff_date") or DEFAULT_OA_RETENTION_CUTOFF_DATE).strip()
        if not _is_iso_date(cutoff_date):
            cutoff_date = DEFAULT_OA_RETENTION_CUTOFF_DATE
        raw_oa_import = raw_payload.get("oa_import")
        oa_import = raw_oa_import if isinstance(raw_oa_import, dict) else {}
        form_type_ids = [item["id"] for item in OA_IMPORT_FORM_TYPE_OPTIONS]
        status_ids = [item["id"] for item in OA_IMPORT_STATUS_OPTIONS]
        form_types = AppSettingsService._normalize_option_list(
            oa_import.get("form_types"),
            allowed_values=form_type_ids,
            default_values=DEFAULT_OA_IMPORT_FORM_TYPES,
            preserve_empty="form_types" in oa_import,
        )
        statuses = AppSettingsService._normalize_option_list(
            oa_import.get("statuses"),
            allowed_values=status_ids,
            default_values=DEFAULT_OA_IMPORT_STATUSES,
            preserve_empty="statuses" in oa_import,
        )
        attachment_invoice_promotion_mode = str(
            oa_import.get("attachment_invoice_promotion_mode")
            or oa_import.get("oa_attachment_invoice_promotion_mode")
            or DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE
        ).strip()
        if attachment_invoice_promotion_mode not in OA_ATTACHMENT_INVOICE_PROMOTION_MODES:
            attachment_invoice_promotion_mode = DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE
        raw_oa_invoice_offset = raw_payload.get("oa_invoice_offset")
        oa_invoice_offset = raw_oa_invoice_offset if isinstance(raw_oa_invoice_offset, dict) else {}
        raw_applicant_names = (
            oa_invoice_offset.get("applicant_names")
            if "applicant_names" in oa_invoice_offset
            else DEFAULT_OA_INVOICE_OFFSET_APPLICANTS
        )
        if not isinstance(raw_applicant_names, list):
            raw_applicant_names = []
        applicant_names = AppSettingsService._normalize_username_list(
            raw_applicant_names
        )
        manual_projects: list[dict[str, Any]] = []
        seen_manual_project_ids: set[str] = set()
        for item in list(raw_payload.get("manual_projects") or []):
            if not isinstance(item, dict):
                continue
            project_id = str(item.get("id", "")).strip()
            project_code = str(item.get("project_code", "")).strip()
            project_name = str(item.get("project_name", "")).strip()
            if not project_id or not project_code or not project_name or project_id in seen_manual_project_ids:
                continue
            seen_manual_project_ids.add(project_id)
            manual_projects.append(
                {
                    "id": project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "project_status": str(item.get("project_status") or "active").strip() or "active",
                    "department_name": (
                        str(item.get("department_name")).strip()
                        if item.get("department_name") is not None
                        else None
                    ),
                    "owner_name": (
                        str(item.get("owner_name")).strip()
                        if item.get("owner_name") is not None
                        else None
                    ),
                }
            )
        synced_projects: list[dict[str, Any]] = []
        seen_synced_project_ids: set[str] = set()
        for item in list(raw_payload.get("synced_projects") or []):
            if not isinstance(item, dict):
                continue
            project_id = str(item.get("id", "")).strip()
            project_code = str(item.get("project_code", "")).strip()
            project_name = str(item.get("project_name", "")).strip()
            if not project_id or not project_code or not project_name or project_id in seen_synced_project_ids:
                continue
            seen_synced_project_ids.add(project_id)
            synced_projects.append(
                {
                    "id": project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "project_status": str(item.get("project_status") or "active").strip() or "active",
                    "department_name": (
                        str(item.get("department_name")).strip()
                        if item.get("department_name") is not None
                        else None
                    ),
                    "owner_name": (
                        str(item.get("owner_name")).strip()
                        if item.get("owner_name") is not None
                        else None
                    ),
                }
            )
        bank_transaction_tags = AppSettingsService._normalize_bank_transaction_tags(
            raw_payload.get("bank_transaction_tags")
        )
        pending_invoice_tag_groups = AppSettingsService._normalize_pending_invoice_tag_groups(
            raw_payload.get("pending_invoice_tag_groups"),
            bank_transaction_tags=bank_transaction_tags,
            validate=validate_pending_invoice_tag_groups,
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        pending_output_invoice_tag_groups = AppSettingsService._normalize_pending_invoice_tag_groups(
            raw_payload.get("pending_output_invoice_tag_groups"),
            bank_transaction_tags=bank_transaction_tags,
            validate=validate_pending_invoice_tag_groups,
            group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
        )
        no_oa_bank_batch_tag_selection = AppSettingsService._normalize_bank_transaction_requirement_rules(
            raw_payload.get("no_oa_bank_batch_tag_selection"),
            bank_transaction_tags=bank_transaction_tags,
            validate=False,
            include_selected_tag_codes=True,
        )
        bank_flow_rule_batch_tag_rules = AppSettingsService._normalize_bank_transaction_requirement_rules(
            raw_payload.get("bank_flow_rule_batch_tag_rules", DEFAULT_BANK_FLOW_RULE_BATCH_TAG_RULES),
            bank_transaction_tags=bank_transaction_tags,
            validate=False,
            include_selected_tag_codes=False,
        )
        turnover_ledger_tag_selection = AppSettingsService._normalize_turnover_ledger_tag_selection(
            raw_payload.get("turnover_ledger_tag_selection"),
            bank_transaction_tags=bank_transaction_tags,
            validate=False,
            default_all_external="turnover_ledger_tag_selection" not in raw_payload,
        )
        cost_statistics_tag_selection = AppSettingsService._normalize_cost_statistics_tag_selection(
            raw_payload.get("cost_statistics_tag_selection", DEFAULT_COST_STATISTICS_TAG_SELECTION),
            bank_transaction_tags=bank_transaction_tags,
            validate=False,
        )
        input_invoice_usage_payment_rules = normalize_payment_status_rules_settings(
            raw_payload.get(INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY)
        )
        return {
            "completed_project_ids": completed_ids,
            "manual_projects": manual_projects,
            "synced_projects": synced_projects,
            "bank_account_mappings": mappings,
            "allowed_usernames": sorted(allowed_usernames),
            "readonly_export_usernames": sorted(readonly_export_usernames),
            "admin_usernames": sorted(admin_usernames),
            "full_access_usernames": full_access_usernames,
            "workbench_column_layouts": normalized_layouts,
            "oa_retention": {"cutoff_date": cutoff_date},
            "oa_import": {
                "form_types": form_types,
                "statuses": statuses,
                "attachment_invoice_promotion_mode": attachment_invoice_promotion_mode,
            },
            "oa_invoice_offset": {"applicant_names": applicant_names},
            "bank_transaction_tags": bank_transaction_tags,
            "pending_invoice_tag_groups": pending_invoice_tag_groups,
            "pending_output_invoice_tag_groups": pending_output_invoice_tag_groups,
            "no_oa_bank_batch_tag_selection": no_oa_bank_batch_tag_selection,
            "bank_flow_rule_batch_tag_rules": bank_flow_rule_batch_tag_rules,
            "turnover_ledger_tag_selection": turnover_ledger_tag_selection,
            "cost_statistics_tag_selection": cost_statistics_tag_selection,
            INPUT_INVOICE_USAGE_PAYMENT_RULES_SETTINGS_KEY: input_invoice_usage_payment_rules,
        }

    @staticmethod
    def _normalize_bank_transaction_tags(value: Any) -> dict[str, Any]:
        service = BankTransactionCategoryService(tag_dictionary=value if isinstance(value, dict) else None)
        return service.tag_dictionary_payload()

    @staticmethod
    def _normalize_pending_invoice_tag_groups(
        value: Any,
        *,
        bank_transaction_tags: dict[str, Any],
        validate: bool,
        group_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        labels = group_labels or PENDING_INVOICE_TAG_GROUP_LABELS
        raw_payload = value if isinstance(value, dict) else {}
        version = BankTransactionCategoryService._normalize_version(
            raw_payload.get("version", bank_transaction_tags.get("version", 1))
        )
        if version <= 0:
            version = int(bank_transaction_tags.get("version") or 1)
        raw_groups = raw_payload.get("groups") if isinstance(raw_payload.get("groups"), dict) else raw_payload
        if not isinstance(raw_groups, dict):
            raw_groups = {}

        definitions_by_code = {
            str(definition["code"]): dict(definition)
            for definition in list(bank_transaction_tags.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        groups: dict[str, dict[str, Any]] = {}
        claimed_codes: dict[str, str] = {}
        for group_id, label in labels.items():
            raw_group = raw_groups.get(group_id)
            if isinstance(raw_group, dict):
                raw_codes = raw_group.get("tag_codes")
            elif isinstance(raw_group, list):
                raw_codes = raw_group
            else:
                raw_codes = []
            tag_codes: list[str] = []
            seen_in_group: set[str] = set()
            for item in list(raw_codes or []):
                tag_code = str(item or "").strip()
                if not tag_code or tag_code in seen_in_group:
                    continue
                definition = definitions_by_code.get(tag_code)
                if not isinstance(definition, dict):
                    if validate:
                        raise AppSettingsValidationError(
                            "unknown_bank_transaction_tag",
                            f"Unknown bank transaction tag code in pending invoice group: {tag_code}",
                        )
                elif definition.get("status") == "archived" and validate:
                    raise AppSettingsValidationError(
                        "archived_bank_transaction_tag",
                        f"Archived bank transaction tag cannot be mapped: {tag_code}",
                    )
                if tag_code in claimed_codes:
                    if validate:
                        raise AppSettingsValidationError(
                            "duplicate_pending_invoice_tag_mapping",
                            f"Bank transaction tag {tag_code} is mapped to multiple pending invoice groups.",
                        )
                seen_in_group.add(tag_code)
                claimed_codes[tag_code] = group_id
                tag_codes.append(tag_code)
            groups[group_id] = {
                "label": label,
                "tag_codes": tag_codes,
            }
        return {
            "version": version,
            "groups": groups,
        }

    @staticmethod
    def _public_bank_transaction_tags(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": int(payload.get("version") or 1),
            "definitions": [
                {
                    "code": str(definition["code"]),
                    "label": str(definition["label"]),
                    "path": list(definition.get("path") or []),
                    "source": str(definition["source"]),
                    "status": str(definition["status"]),
                    "output_primary_label": str(
                        definition.get("output_primary_label") or definition.get("label") or definition["code"]
                    ),
                    "output_sub_label": str(definition.get("output_sub_label") or ""),
                }
                for definition in list(payload.get("definitions") or [])
                if isinstance(definition, dict)
            ],
        }

    @staticmethod
    def _public_pending_invoice_tag_groups(
        payload: dict[str, Any],
        *,
        version: int,
        group_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        labels = group_labels or PENDING_INVOICE_TAG_GROUP_LABELS
        groups = payload.get("groups") if isinstance(payload.get("groups"), dict) else {}
        return {
            "version": version,
            "groups": {
                group_id: {
                    "label": str(groups.get(group_id, {}).get("label") or label)
                    if isinstance(groups.get(group_id), dict)
                    else label,
                    "tag_codes": [
                        str(tag_code)
                        for tag_code in list(groups.get(group_id, {}).get("tag_codes") or [])
                    ]
                    if isinstance(groups.get(group_id), dict)
                    else [],
                }
                for group_id, label in labels.items()
            },
        }

    @staticmethod
    def _active_bank_transaction_tag_definitions(bank_transaction_tags: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            dict(definition)
            for definition in list(bank_transaction_tags.get("definitions") or [])
            if isinstance(definition, dict)
            and str(definition.get("code") or "").strip()
            and str(definition.get("status") or "active") == "active"
        ]

    @staticmethod
    def _active_turnover_ledger_tag_definitions(bank_transaction_tags: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            definition
            for definition in AppSettingsService._active_bank_transaction_tag_definitions(bank_transaction_tags)
            if is_external_turnover_definition(definition)
            and normalize_turnover_action_type(definition.get("turnover_action_type"))
        ]

    @staticmethod
    def _normalize_bank_transaction_requirement_rules(
        value: Any,
        *,
        bank_transaction_tags: dict[str, Any],
        validate: bool,
        include_selected_tag_codes: bool,
    ) -> dict[str, Any]:
        raw_payload = value if isinstance(value, dict) else {}
        version = BankTransactionCategoryService._normalize_version(
            raw_payload.get("version", DEFAULT_NO_OA_BANK_BATCH_TAG_SELECTION["version"])
        )
        if version <= 0:
            version = int(DEFAULT_NO_OA_BANK_BATCH_TAG_SELECTION["version"])
        definitions_by_code = {
            str(definition.get("code") or "").strip(): definition
            for definition in AppSettingsService._no_oa_bank_batch_auto_rule_tags(bank_transaction_tags)
            if str(definition.get("code") or "").strip()
        }
        requirements_by_tag_code: dict[str, dict[str, bool]] = {}

        def ensure_active(tag_code: str) -> bool:
            definition = definitions_by_code.get(tag_code)
            if not isinstance(definition, dict):
                if validate:
                    raise AppSettingsValidationError(
                        "unknown_bank_transaction_tag",
                        f"Unknown bank transaction requirement rule tag code: {tag_code}",
                    )
                return False
            if str(definition.get("status") or "active") != "active":
                if validate:
                    raise AppSettingsValidationError(
                        "archived_bank_transaction_tag",
                        f"Archived bank transaction tag cannot enter requirement rules: {tag_code}",
                    )
                return False
            return True

        raw_rules = raw_payload.get("rules")
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if not isinstance(item, dict):
                    continue
                tag_code = str(item.get("tag_code") or item.get("code") or "").strip()
                if not tag_code or not ensure_active(tag_code):
                    continue
                requirements_by_tag_code[tag_code] = {
                    "requires_oa": bool(item.get("requires_oa")),
                    "requires_invoice": bool(item.get("requires_invoice")),
                }

        raw_requirements = raw_payload.get("requirements_by_tag_code")
        if isinstance(raw_requirements, dict):
            for raw_code, item in raw_requirements.items():
                tag_code = str(raw_code or "").strip()
                if not tag_code or not ensure_active(tag_code):
                    continue
                rule = item if isinstance(item, dict) else {}
                requirements_by_tag_code[tag_code] = {
                    "requires_oa": bool(rule.get("requires_oa")),
                    "requires_invoice": bool(rule.get("requires_invoice")),
                }

        if include_selected_tag_codes:
            for item in list(raw_payload.get("selected_tag_codes") or []):
                tag_code = str(item or "").strip()
                if not tag_code or tag_code in requirements_by_tag_code:
                    continue
                if not ensure_active(tag_code):
                    continue
                requirements_by_tag_code[tag_code] = {"requires_oa": False, "requires_invoice": False}
        normalized = {
            "version": version,
            "requirements_by_tag_code": requirements_by_tag_code,
        }
        if include_selected_tag_codes:
            normalized["selected_tag_codes"] = [
                code
                for code, rule in requirements_by_tag_code.items()
                if not bool(rule.get("requires_oa")) and not bool(rule.get("requires_invoice"))
            ]
        return normalized

    @staticmethod
    def _public_no_oa_bank_batch_tag_selection(
        payload: dict[str, Any],
        *,
        bank_transaction_tags: dict[str, Any],
    ) -> dict[str, Any]:
        active_tags = AppSettingsService._no_oa_bank_batch_auto_rule_tags(bank_transaction_tags)
        active_codes = {tag["code"] for tag in active_tags}
        raw_requirements = payload.get("requirements_by_tag_code") if isinstance(payload.get("requirements_by_tag_code"), dict) else {}
        requirements_by_tag_code = {
            str(code): {
                "requires_oa": bool(rule.get("requires_oa")) if isinstance(rule, dict) else False,
                "requires_invoice": bool(rule.get("requires_invoice")) if isinstance(rule, dict) else False,
            }
            for code, rule in dict(raw_requirements or {}).items()
            if str(code)
        }
        if not requirements_by_tag_code:
            for tag_code in list(payload.get("selected_tag_codes") or []):
                code = str(tag_code or "").strip()
                if code:
                    requirements_by_tag_code[code] = {"requires_oa": False, "requires_invoice": False}
        selected = [
            code
            for code, rule in requirements_by_tag_code.items()
            if code in active_codes and not rule["requires_oa"] and not rule["requires_invoice"]
        ]
        inactive_selected = [
            code
            for code in requirements_by_tag_code
            if code not in active_codes
        ]
        rules = [
            {
                "tag_code": tag["code"],
                "requires_oa": bool(requirements_by_tag_code.get(tag["code"], {}).get("requires_oa", True)),
                "requires_invoice": bool(requirements_by_tag_code.get(tag["code"], {}).get("requires_invoice", True)),
            }
            for tag in active_tags
        ]
        return {
            "version": int(payload.get("version") or 1),
            "bank_auto_tag_rules_version": int(bank_transaction_tags.get("version") or 1),
            "selected_tag_codes": selected,
            "inactive_selected_tag_codes": inactive_selected,
            "active_tags": active_tags,
            "rules": rules,
            "requirements_by_tag_code": {
                rule["tag_code"]: {
                    "requires_oa": rule["requires_oa"],
                    "requires_invoice": rule["requires_invoice"],
                }
                for rule in rules
            },
        }

    @staticmethod
    def _public_bank_transaction_paired_policy(
        payload: dict[str, Any],
        *,
        bank_transaction_tags: dict[str, Any],
    ) -> dict[str, Any]:
        active_tags = AppSettingsService._no_oa_bank_batch_auto_rule_tags(bank_transaction_tags)
        raw_requirements = payload.get("requirements_by_tag_code") if isinstance(payload.get("requirements_by_tag_code"), dict) else {}
        requirements_by_tag_code = {
            str(code): {
                "requires_oa": bool(rule.get("requires_oa")) if isinstance(rule, dict) else False,
                "requires_invoice": bool(rule.get("requires_invoice")) if isinstance(rule, dict) else False,
            }
            for code, rule in dict(raw_requirements or {}).items()
            if str(code)
        }
        rules = [
            {
                "tag_code": tag["code"],
                "requires_oa": bool(requirements_by_tag_code.get(tag["code"], {}).get("requires_oa", True)),
                "requires_invoice": bool(requirements_by_tag_code.get(tag["code"], {}).get("requires_invoice", True)),
            }
            for tag in active_tags
        ]
        return {
            "version": int(payload.get("version") or 1),
            "bank_auto_tag_rules_version": int(bank_transaction_tags.get("version") or 1),
            "active_tags": active_tags,
            "rules": rules,
            "requirements_by_tag_code": {
                rule["tag_code"]: {
                    "requires_oa": rule["requires_oa"],
                    "requires_invoice": rule["requires_invoice"],
                }
                for rule in rules
            },
        }

    @staticmethod
    def _no_oa_bank_batch_auto_rule_tags(bank_transaction_tags: dict[str, Any]) -> list[dict[str, Any]]:
        auto_rules_payload = BankTransactionCategoryService.auto_tag_rules_payload(
            bank_transaction_tags,
            can_save=False,
        )
        active_rules = [
            rule
            for rule in list(auto_rules_payload.get("active_rules") or [])
            if isinstance(rule, dict) and str(rule.get("code") or "").strip()
        ]
        system_rule = auto_rules_payload.get("system_rule") if isinstance(auto_rules_payload.get("system_rule"), dict) else {}
        definitions_by_code = {
            str(definition.get("code") or "").strip(): definition
            for definition in AppSettingsService._active_bank_transaction_tag_definitions(bank_transaction_tags)
            if str(definition.get("code") or "").strip()
        }

        ordered_rules: list[dict[str, Any]] = []
        system_code = str(system_rule.get("code") or "internal_transfer").strip()
        if system_code:
            system_definition = definitions_by_code.get(system_code, {})
            ordered_rules.append({
                "code": system_code,
                "label": str(system_rule.get("label") or system_definition.get("label") or system_code),
                "path": list(system_definition.get("path") or []),
                "source": str(system_rule.get("source") or system_definition.get("source") or "system"),
                "status": str(system_rule.get("status") or system_definition.get("status") or "active"),
                "direction": str(system_definition.get("direction") or system_rule.get("direction") or "any"),
                "output_primary_label": str(
                    system_definition.get("output_primary_label")
                    or system_rule.get("label")
                    or system_definition.get("label")
                    or system_code
                ),
                "output_sub_label": str(system_definition.get("output_sub_label") or ""),
            })
        ordered_rules.extend(active_rules)

        active_tags: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for rule in ordered_rules:
            code = str(rule.get("code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            active_tags.append({
                "code": code,
                "label": str(rule.get("label") or rule.get("output_sub_label") or rule.get("output_primary_label") or code),
                "path": list(rule.get("path") or definitions_by_code.get(code, {}).get("path") or []),
                "source": str(rule.get("source") or definitions_by_code.get(code, {}).get("source") or "custom"),
                "status": str(rule.get("status") or "active"),
                "direction": str(definitions_by_code.get(code, {}).get("direction") or rule.get("direction") or "any"),
                "output_primary_label": str(rule.get("output_primary_label") or rule.get("label") or code),
                "output_sub_label": str(rule.get("output_sub_label") or ""),
            })
        return active_tags

    @staticmethod
    def _cost_statistics_active_tag_definitions(bank_transaction_tags: dict[str, Any]) -> list[dict[str, Any]]:
        active_tags: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for tag in AppSettingsService._no_oa_bank_batch_auto_rule_tags(bank_transaction_tags):
            code = str(tag.get("code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            path = [str(item).strip() for item in list(tag.get("path") or []) if str(item).strip()]
            primary = str(tag.get("output_primary_label") or tag.get("label") or code).strip() or code
            sub = str(tag.get("output_sub_label") or tag.get("label") or primary).strip() or primary
            active_tags.append(
                {
                    "code": code,
                    "label": str(tag.get("label") or sub or primary or code),
                    "path": path if path else ([primary] if primary == sub else [primary, sub]),
                    "source": str(tag.get("source") or "custom"),
                    "status": str(tag.get("status") or "active"),
                    "direction": str(tag.get("direction") or "any"),
                    "output_primary_label": primary,
                    "output_sub_label": sub,
                }
            )
        active_tags.append(
            {
                "code": COST_STATISTICS_UNCATEGORIZED_TAG_CODE,
                "label": "未分类",
                "path": ["未分类", "未分类"],
                "source": "system",
                "status": "active",
                "direction": "any",
                "output_primary_label": "未分类",
                "output_sub_label": "未分类",
            }
        )
        return active_tags

    @staticmethod
    def _normalize_cost_statistics_tag_selection(
        value: Any,
        *,
        bank_transaction_tags: dict[str, Any],
        validate: bool,
    ) -> dict[str, Any]:
        raw_payload = value if isinstance(value, dict) else {}
        version = BankTransactionCategoryService._normalize_version(
            raw_payload.get("version", DEFAULT_COST_STATISTICS_TAG_SELECTION["version"])
        )
        if version <= 0:
            version = int(DEFAULT_COST_STATISTICS_TAG_SELECTION["version"])
        selection_schema_version = BankTransactionCategoryService._normalize_version(
            raw_payload.get("selection_schema_version", 1)
        )
        active_tags = AppSettingsService._cost_statistics_active_tag_definitions(bank_transaction_tags)
        active_codes = {
            str(tag.get("code") or "").strip()
            for tag in active_tags
            if str(tag.get("code") or "").strip()
        }
        if raw_payload.get("selected_tag_codes") is None:
            return {
                "version": version,
                "selection_schema_version": COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION,
                "selected_tag_codes": None,
            }
        selected_tag_codes: list[str] = []
        seen: set[str] = set()
        for item in list(raw_payload.get("selected_tag_codes") or []):
            tag_code = str(item or "").strip()
            if not tag_code or tag_code in seen:
                continue
            if tag_code not in active_codes:
                if validate:
                    raise AppSettingsValidationError(
                        "unknown_cost_statistics_tag",
                        f"Unknown bank transaction tag code in cost statistics selection: {tag_code}",
                    )
                continue
            seen.add(tag_code)
            selected_tag_codes.append(tag_code)
        if selection_schema_version < COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION:
            for tag in active_tags:
                direction = str(tag.get("direction") or "any").strip().lower()
                tag_code = str(tag.get("code") or "").strip()
                if direction not in {"income", "in", "收入", "收款", "credit"} or not tag_code or tag_code in seen:
                    continue
                seen.add(tag_code)
                selected_tag_codes.append(tag_code)
            version += 1
        return {
            "version": version,
            "selection_schema_version": COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION,
            "selected_tag_codes": selected_tag_codes,
        }

    @staticmethod
    def _public_cost_statistics_tag_selection(
        payload: dict[str, Any],
        *,
        bank_transaction_tags: dict[str, Any],
    ) -> dict[str, Any]:
        active_tags = AppSettingsService._cost_statistics_active_tag_definitions(bank_transaction_tags)
        active_codes = [str(tag.get("code") or "").strip() for tag in active_tags if str(tag.get("code") or "").strip()]
        active_code_set = set(active_codes)
        raw_selected = payload.get("selected_tag_codes")
        default_selection_applied = raw_selected is None
        selected = (
            list(active_codes)
            if default_selection_applied
            else [
                str(tag_code)
                for tag_code in list(raw_selected or [])
                if str(tag_code) in active_code_set
            ]
        )
        inactive_selected = (
            []
            if default_selection_applied
            else [
                str(tag_code)
                for tag_code in list(raw_selected or [])
                if str(tag_code) and str(tag_code) not in active_code_set
            ]
        )
        return {
            "version": int(payload.get("version") or 1),
            "selection_schema_version": int(
                payload.get("selection_schema_version") or COST_STATISTICS_TAG_SELECTION_SCHEMA_VERSION
            ),
            "bank_auto_tag_rules_version": int(bank_transaction_tags.get("version") or 1),
            "default_selection_applied": default_selection_applied,
            "selected_tag_codes": selected,
            "effective_selected_tag_codes": selected,
            "inactive_selected_tag_codes": inactive_selected,
            "active_tags": active_tags,
        }

    @staticmethod
    def _normalize_turnover_ledger_tag_selection(
        value: Any,
        *,
        bank_transaction_tags: dict[str, Any],
        validate: bool,
        default_all_external: bool = False,
    ) -> dict[str, Any]:
        raw_payload = value if isinstance(value, dict) else {}
        version = BankTransactionCategoryService._normalize_version(
            raw_payload.get("version", DEFAULT_TURNOVER_LEDGER_TAG_SELECTION["version"])
        )
        if version <= 0:
            version = int(DEFAULT_TURNOVER_LEDGER_TAG_SELECTION["version"])
        active_external_by_code = {
            str(definition.get("code") or "").strip(): definition
            for definition in AppSettingsService._active_turnover_ledger_tag_definitions(bank_transaction_tags)
            if str(definition.get("code") or "").strip()
        }
        definitions_by_code = {
            str(definition.get("code") or "").strip(): definition
            for definition in list(bank_transaction_tags.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        raw_codes = (
            list(active_external_by_code.keys())
            if default_all_external and "selected_tag_codes" not in raw_payload
            else list(raw_payload.get("selected_tag_codes") or [])
        )
        selected_tag_codes: list[str] = []
        seen: set[str] = set()
        for item in raw_codes:
            tag_code = str(item or "").strip()
            if not tag_code or tag_code in seen:
                continue
            definition = definitions_by_code.get(tag_code)
            if not isinstance(definition, dict):
                if validate:
                    raise AppSettingsValidationError(
                        "unknown_bank_transaction_tag",
                        f"Unknown bank transaction tag code in turnover ledger selection: {tag_code}",
                    )
                continue
            if tag_code not in active_external_by_code:
                if validate:
                    raise AppSettingsValidationError(
                        "invalid_turnover_ledger_tag",
                        f"Bank transaction tag cannot enter turnover ledger selection: {tag_code}",
                    )
                selected_tag_codes.append(tag_code)
                seen.add(tag_code)
                continue
            seen.add(tag_code)
            selected_tag_codes.append(tag_code)
        return {
            "version": version,
            "selected_tag_codes": selected_tag_codes,
        }

    @staticmethod
    def _public_turnover_ledger_tag_selection(
        payload: dict[str, Any],
        *,
        bank_transaction_tags: dict[str, Any],
    ) -> dict[str, Any]:
        active_tags = [
            {
                "code": str(definition.get("code") or ""),
                "label": str(definition.get("label") or definition.get("code") or ""),
                "path": list(definition.get("path") or []),
                "source": str(definition.get("source") or ""),
                "status": str(definition.get("status") or "active"),
                "output_primary_label": str(
                    definition.get("output_primary_label") or definition.get("label") or definition.get("code") or ""
                ),
                "output_sub_label": str(definition.get("output_sub_label") or ""),
                "turnover_role": str(definition.get("turnover_role") or EXTERNAL_TURNOVER_ROLE),
                "turnover_action_type": str(definition.get("turnover_action_type") or ""),
            }
            for definition in AppSettingsService._active_turnover_ledger_tag_definitions(bank_transaction_tags)
        ]
        active_codes = {tag["code"] for tag in active_tags}
        selected = [
            str(tag_code)
            for tag_code in list(payload.get("selected_tag_codes") or [])
            if str(tag_code) in active_codes
        ]
        inactive_selected = [
            str(tag_code)
            for tag_code in list(payload.get("selected_tag_codes") or [])
            if str(tag_code) and str(tag_code) not in active_codes
        ]
        return {
            "version": int(payload.get("version") or 1),
            "selected_tag_codes": selected,
            "inactive_selected_tag_codes": inactive_selected,
            "active_tags": active_tags,
        }

    def _configure_category_service(self, snapshot: dict[str, Any]) -> None:
        tag_dictionary = (
            snapshot.get("bank_transaction_tags")
            if isinstance(snapshot.get("bank_transaction_tags"), dict)
            else default_bank_transaction_tag_dictionary_payload()
        )
        if self._bank_transaction_category_service is not None:
            self._bank_transaction_category_service.configure_tag_dictionary(tag_dictionary)
        configure_auto = getattr(self._bank_transaction_auto_category_service, "configure_tag_dictionary", None)
        if callable(configure_auto):
            configure_auto(tag_dictionary)

    @staticmethod
    def _tag_settings_comparable(snapshot: dict[str, Any]) -> dict[str, Any]:
        tags = AppSettingsService._public_bank_transaction_tags(snapshot["bank_transaction_tags"])
        groups = AppSettingsService._public_pending_invoice_tag_groups(
            snapshot["pending_invoice_tag_groups"],
            version=int(tags["version"]),
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        output_groups = AppSettingsService._public_pending_invoice_tag_groups(
            snapshot["pending_output_invoice_tag_groups"],
            version=int(tags["version"]),
            group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
        )
        tags_without_version = {key: value for key, value in tags.items() if key != "version"}
        groups_without_version = {key: value for key, value in groups.items() if key != "version"}
        output_groups_without_version = {key: value for key, value in output_groups.items() if key != "version"}
        return {
            "bank_transaction_tags": tags_without_version,
            "pending_invoice_tag_groups": groups_without_version,
            "pending_output_invoice_tag_groups": output_groups_without_version,
        }

    def _prepare_tag_settings_event(
        self,
        previous_snapshot: dict[str, Any],
        next_snapshot: dict[str, Any],
        *,
        actor_id: str | None,
    ) -> dict[str, Any] | None:
        previous_comparable = self._tag_settings_comparable(previous_snapshot)
        next_comparable = self._tag_settings_comparable(next_snapshot)
        tags_changed = (
            previous_comparable["bank_transaction_tags"]
            != next_comparable["bank_transaction_tags"]
        )
        groups_changed = (
            previous_comparable["pending_invoice_tag_groups"]
            != next_comparable["pending_invoice_tag_groups"]
            or previous_comparable["pending_output_invoice_tag_groups"]
            != next_comparable["pending_output_invoice_tag_groups"]
        )
        if not tags_changed and not groups_changed:
            return None
        affected_groups = self._affected_pending_invoice_groups(
            previous_snapshot["pending_invoice_tag_groups"],
            next_snapshot["pending_invoice_tag_groups"],
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        affected_groups.extend(
            f"income:{group_id}"
            for group_id in self._affected_pending_invoice_groups(
                previous_snapshot["pending_output_invoice_tag_groups"],
                next_snapshot["pending_output_invoice_tag_groups"],
                group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
            )
        )
        return {
            "actor_id": str(actor_id or "workbench_settings").strip() or "workbench_settings",
            "tags_changed": tags_changed,
            "groups_changed": groups_changed,
            "affected_groups": affected_groups,
            "before_summary": self._tag_settings_summary(previous_snapshot),
            "after_summary": self._tag_settings_summary(next_snapshot),
            "new_version": int(next_snapshot["bank_transaction_tags"]["version"]),
        }

    def _apply_tag_settings_versions(
        self,
        previous_snapshot: dict[str, Any],
        normalized_snapshot: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        if event.get("tags_changed"):
            normalized_snapshot["bank_transaction_tags"]["version"] = (
                int(previous_snapshot["bank_transaction_tags"].get("version") or 1) + 1
            )
        else:
            normalized_snapshot["bank_transaction_tags"]["version"] = int(
                previous_snapshot["bank_transaction_tags"].get("version") or 1
            )
        affected_expense_groups = self._affected_pending_invoice_groups(
            previous_snapshot["pending_invoice_tag_groups"],
            normalized_snapshot["pending_invoice_tag_groups"],
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
        )
        affected_income_groups = self._affected_pending_invoice_groups(
            previous_snapshot["pending_output_invoice_tag_groups"],
            normalized_snapshot["pending_output_invoice_tag_groups"],
            group_labels=PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS,
        )
        normalized_snapshot["pending_invoice_tag_groups"]["version"] = (
            int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1) + 1
            if affected_expense_groups
            else int(previous_snapshot["pending_invoice_tag_groups"].get("version") or 1)
        )
        normalized_snapshot["pending_output_invoice_tag_groups"]["version"] = (
            int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1) + 1
            if affected_income_groups
            else int(previous_snapshot["pending_output_invoice_tag_groups"].get("version") or 1)
        )
        event["new_version"] = int(normalized_snapshot["bank_transaction_tags"]["version"])
        event["new_versions"] = {
            "bank_transaction_tags": int(normalized_snapshot["bank_transaction_tags"]["version"]),
            "pending_invoice_tag_groups": int(normalized_snapshot["pending_invoice_tag_groups"]["version"]),
            "pending_output_invoice_tag_groups": int(normalized_snapshot["pending_output_invoice_tag_groups"]["version"]),
        }

    @staticmethod
    def _affected_pending_invoice_groups(
        previous_groups_payload: dict[str, Any],
        next_groups_payload: dict[str, Any],
        *,
        group_labels: dict[str, str] | None = None,
    ) -> list[str]:
        labels = group_labels or PENDING_INVOICE_TAG_GROUP_LABELS
        previous_groups = previous_groups_payload.get("groups") if isinstance(previous_groups_payload.get("groups"), dict) else {}
        next_groups = next_groups_payload.get("groups") if isinstance(next_groups_payload.get("groups"), dict) else {}
        affected = []
        for group_id in labels:
            previous_codes = (
                list(previous_groups.get(group_id, {}).get("tag_codes") or [])
                if isinstance(previous_groups.get(group_id), dict)
                else []
            )
            next_codes = (
                list(next_groups.get(group_id, {}).get("tag_codes") or [])
                if isinstance(next_groups.get(group_id), dict)
                else []
            )
            if previous_codes != next_codes:
                affected.append(group_id)
        return sorted(affected)

    @staticmethod
    def _tag_settings_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
        tags = snapshot["bank_transaction_tags"]
        definitions = list(tags.get("definitions") or [])
        groups = snapshot["pending_invoice_tag_groups"].get("groups")
        groups = groups if isinstance(groups, dict) else {}
        output_groups = snapshot["pending_output_invoice_tag_groups"].get("groups")
        output_groups = output_groups if isinstance(output_groups, dict) else {}
        return {
            "version": int(tags.get("version") or 1),
            "definition_count": len(definitions),
            "active_definition_count": sum(
                1
                for definition in definitions
                if isinstance(definition, dict) and definition.get("status") == "active"
            ),
            "group_tag_counts": {
                group_id: len(list(groups.get(group_id, {}).get("tag_codes") or []))
                if isinstance(groups.get(group_id), dict)
                else 0
                for group_id in PENDING_INVOICE_TAG_GROUP_LABELS
            },
            "output_group_tag_counts": {
                group_id: len(list(output_groups.get(group_id, {}).get("tag_codes") or []))
                if isinstance(output_groups.get(group_id), dict)
                else 0
                for group_id in PENDING_OUTPUT_INVOICE_TAG_GROUP_LABELS
            },
        }

    def _record_tag_settings_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        metadata = {
            "before_summary": event["before_summary"],
            "after_summary": event["after_summary"],
            "affected_groups": list(event["affected_groups"]),
            "new_version": event["new_version"],
        }
        if event.get("tags_changed"):
            self._audit_service.record_action(
                actor_id=str(event["actor_id"]),
                action="bank_transaction_tags_updated",
                entity_type="app_settings",
                entity_id="bank_transaction_tags",
                metadata=metadata,
            )
        if event.get("groups_changed"):
            self._audit_service.record_action(
                actor_id=str(event["actor_id"]),
                action="pending_invoice_tag_groups_updated",
                entity_type="app_settings",
                entity_id="pending_invoice_tag_groups",
                metadata=metadata,
            )

    def _record_pending_invoice_rules_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event["actor_id"]),
            action="pending_invoice_rule_groups_updated",
            entity_type="app_settings",
            entity_id=str(event.get("settings_key") or "pending_invoice_tag_groups"),
            metadata={
                "direction": str(event.get("direction") or "expense"),
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "affected_groups": list(event.get("affected_groups") or []),
                "before_summary": event.get("before_summary"),
                "after_summary": event.get("after_summary"),
            },
        )

    def _record_bank_auto_tag_rules_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "bank_auto_tag_rules"),
            action="bank_auto_tag_rules_updated",
            entity_type="app_settings",
            entity_id="bank_auto_tag_rules",
            metadata={
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "added_tags": list(event.get("added_tags") or []),
                "renamed_tags": list(event.get("renamed_tags") or []),
                "archived_codes": list(event.get("archived_codes") or []),
                "reenabled_codes": list(event.get("reenabled_codes") or []),
                "priority_changes": list(event.get("priority_changes") or []),
                "rule_changes": list(event.get("rule_changes") or []),
                "rule_payload_changes": list(event.get("rule_payload_changes") or []),
                "source": dict(event.get("source") or {}),
                "reused_codes": list(event.get("reused_codes") or []),
                "added_codes": list(event.get("added_codes") or []),
                "skipped_rows": list(event.get("skipped_rows") or []),
                "detached_pending_invoice_tag_references": list(
                    event.get("detached_pending_invoice_tag_references") or []
                ),
                "detached_pending_output_invoice_tag_references": list(
                    event.get("detached_pending_output_invoice_tag_references") or []
                ),
                "detached_no_oa_bank_batch_tag_references": list(
                    event.get("detached_no_oa_bank_batch_tag_references") or []
                ),
                "detached_bank_flow_rule_batch_tag_rule_references": list(
                    event.get("detached_bank_flow_rule_batch_tag_rule_references") or []
                ),
                "detached_turnover_ledger_tag_references": list(
                    event.get("detached_turnover_ledger_tag_references") or []
                ),
                "detached_cost_statistics_tag_references": list(
                    event.get("detached_cost_statistics_tag_references") or []
                ),
            },
        )

    def _record_no_oa_bank_batch_tag_selection_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "no_oa_bank_batch_tag_selection"),
            action="no_oa_bank_batch_tag_selection_updated",
            entity_type="app_settings",
            entity_id="no_oa_bank_batch_tag_selection",
            metadata={
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "old_selected_tag_codes": list(event.get("old_selected_tag_codes") or []),
                "new_selected_tag_codes": list(event.get("new_selected_tag_codes") or []),
                "old_rules": dict(event.get("old_rules") or {}),
                "new_rules": dict(event.get("new_rules") or {}),
            },
        )

    def _record_bank_flow_rule_batch_tag_rules_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "bank_flow_rule_batch_tag_rules"),
            action="bank_flow_rule_batch_tag_rules_updated",
            entity_type="app_settings",
            entity_id="bank_flow_rule_batch_tag_rules",
            metadata={
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "old_rules": dict(event.get("old_rules") or {}),
                "new_rules": dict(event.get("new_rules") or {}),
                "eligibility_changed_tag_codes": list(event.get("eligibility_changed_tag_codes") or []),
                "affected_months": list(event.get("affected_months") or []),
            },
        )

    def _record_turnover_ledger_tag_selection_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "turnover_ledger_tag_selection"),
            action="turnover_ledger_tag_selection_updated",
            entity_type="app_settings",
            entity_id="turnover_ledger_tag_selection",
            metadata={
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "old_selected_tag_codes": list(event.get("old_selected_tag_codes") or []),
                "new_selected_tag_codes": list(event.get("new_selected_tag_codes") or []),
            },
        )

    def _record_cost_statistics_tag_selection_audit(self, event: dict[str, Any]) -> None:
        if self._audit_service is None:
            return
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "cost_statistics_tag_selection"),
            action="cost_statistics_tag_selection_updated",
            entity_type="app_settings",
            entity_id="cost_statistics_tag_selection",
            metadata={
                "old_version": int(event.get("old_version") or 0),
                "new_version": int(event.get("new_version") or 0),
                "old_selected_tag_codes": event.get("old_selected_tag_codes"),
                "new_selected_tag_codes": event.get("new_selected_tag_codes"),
            },
        )

    @staticmethod
    def _pending_invoice_reference_map(value: Any) -> dict[str, list[dict[str, Any]]]:
        return AppSettingsService._pending_invoice_reference_map_for_labels(
            value,
            group_labels=PENDING_INVOICE_TAG_GROUP_LABELS,
            domain="pending_invoice_tag_groups",
            label_prefix="待找发票规则",
        )

    @staticmethod
    def _pending_invoice_reference_map_for_labels(
        value: Any,
        *,
        group_labels: dict[str, str],
        domain: str,
        label_prefix: str,
    ) -> dict[str, list[dict[str, Any]]]:
        raw_payload = value if isinstance(value, dict) else {}
        raw_groups = raw_payload.get("groups") if isinstance(raw_payload.get("groups"), dict) else raw_payload
        if not isinstance(raw_groups, dict):
            raw_groups = {}
        references: dict[str, list[dict[str, Any]]] = {}
        for group_id, default_label in group_labels.items():
            group = raw_groups.get(group_id)
            if isinstance(group, dict):
                tag_codes = group.get("tag_codes")
                label = str(group.get("label") or default_label)
            elif isinstance(group, list):
                tag_codes = group
                label = default_label
            else:
                tag_codes = []
                label = default_label
            for item in list(tag_codes or []):
                tag_code = str(item or "").strip()
                if not tag_code:
                    continue
                references.setdefault(tag_code, []).append(
                    {
                        "domain": domain,
                        "label": f"{label_prefix}：{label}",
                        "tag_code": tag_code,
                    }
                )
        return references

    @staticmethod
    def _detach_pending_invoice_tag_references(
        value: Any,
        *,
        tag_codes: set[str],
        group_labels: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        labels = group_labels or PENDING_INVOICE_TAG_GROUP_LABELS
        normalized_codes = {str(code or "").strip() for code in tag_codes if str(code or "").strip()}
        raw_payload = value if isinstance(value, dict) else {}
        raw_groups = raw_payload.get("groups") if isinstance(raw_payload.get("groups"), dict) else raw_payload
        if not isinstance(raw_groups, dict) or not normalized_codes:
            return dict(raw_payload), []

        next_groups: dict[str, dict[str, Any]] = {}
        detached: list[dict[str, str]] = []
        for group_id, default_label in labels.items():
            raw_group = raw_groups.get(group_id)
            if isinstance(raw_group, dict):
                label = str(raw_group.get("label") or default_label)
                raw_codes = raw_group.get("tag_codes")
            elif isinstance(raw_group, list):
                label = default_label
                raw_codes = raw_group
            else:
                label = default_label
                raw_codes = []
            next_codes: list[str] = []
            seen_codes: set[str] = set()
            for item in list(raw_codes or []):
                tag_code = str(item or "").strip()
                if not tag_code or tag_code in seen_codes:
                    continue
                seen_codes.add(tag_code)
                if tag_code in normalized_codes:
                    detached.append({"group_id": group_id, "label": label, "tag_code": tag_code})
                    continue
                next_codes.append(tag_code)
            next_groups[group_id] = {"label": label, "tag_codes": next_codes}

        return {**dict(raw_payload), "groups": next_groups}, detached

    @staticmethod
    def _detach_bank_transaction_requirement_rule_references(
        value: Any,
        *,
        tag_codes: set[str],
        include_selected_tag_codes: bool,
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        normalized_codes = {str(code or "").strip() for code in tag_codes if str(code or "").strip()}
        raw_payload = value if isinstance(value, dict) else {}
        selected: list[str] = []
        requirements: dict[str, dict[str, bool]] = {}
        detached: list[dict[str, str]] = []
        seen: set[str] = set()
        if include_selected_tag_codes:
            for item in list(raw_payload.get("selected_tag_codes") or []):
                tag_code = str(item or "").strip()
                if not tag_code or tag_code in seen:
                    continue
                seen.add(tag_code)
                if tag_code in normalized_codes:
                    detached.append({"tag_code": tag_code})
                    continue
                selected.append(tag_code)
                requirements.setdefault(tag_code, {"requires_oa": False, "requires_invoice": False})
        for raw_code, raw_rule in dict(raw_payload.get("requirements_by_tag_code") or {}).items():
            tag_code = str(raw_code or "").strip()
            if not tag_code:
                continue
            if tag_code in normalized_codes:
                if {"tag_code": tag_code} not in detached:
                    detached.append({"tag_code": tag_code})
                continue
            rule = raw_rule if isinstance(raw_rule, dict) else {}
            requirements[tag_code] = {
                "requires_oa": bool(rule.get("requires_oa")),
                "requires_invoice": bool(rule.get("requires_invoice")),
            }
        current_version = BankTransactionCategoryService._normalize_version(raw_payload.get("version", 1)) or 1
        next_version = current_version + 1 if detached else current_version
        normalized = {
            "version": next_version,
            "requirements_by_tag_code": requirements,
        }
        if include_selected_tag_codes:
            normalized = {
                **dict(raw_payload),
                **normalized,
                "selected_tag_codes": selected,
            }
        return normalized, detached

    @staticmethod
    def _detach_turnover_ledger_tag_references(
        value: Any,
        *,
        tag_codes: set[str],
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        normalized_codes = {str(code or "").strip() for code in tag_codes if str(code or "").strip()}
        raw_payload = value if isinstance(value, dict) else {}
        selected: list[str] = []
        detached: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in list(raw_payload.get("selected_tag_codes") or []):
            tag_code = str(item or "").strip()
            if not tag_code or tag_code in seen:
                continue
            seen.add(tag_code)
            if tag_code in normalized_codes:
                detached.append({"tag_code": tag_code})
                continue
            selected.append(tag_code)
        current_version = BankTransactionCategoryService._normalize_version(raw_payload.get("version", 1)) or 1
        next_version = current_version + 1 if detached else current_version
        return {
            **dict(raw_payload),
            "version": next_version,
            "selected_tag_codes": selected,
        }, detached

    @staticmethod
    def _detach_cost_statistics_tag_references(
        value: Any,
        *,
        tag_codes: set[str],
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        normalized_codes = {
            str(code or "").strip()
            for code in tag_codes
            if str(code or "").strip() and str(code or "").strip() != COST_STATISTICS_UNCATEGORIZED_TAG_CODE
        }
        raw_payload = value if isinstance(value, dict) else {}
        if raw_payload.get("selected_tag_codes") is None:
            current_version = BankTransactionCategoryService._normalize_version(raw_payload.get("version", 1)) or 1
            return {
                **dict(raw_payload),
                "version": current_version,
                "selected_tag_codes": None,
            }, []
        selected: list[str] = []
        detached: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in list(raw_payload.get("selected_tag_codes") or []):
            tag_code = str(item or "").strip()
            if not tag_code or tag_code in seen:
                continue
            seen.add(tag_code)
            if tag_code in normalized_codes:
                detached.append({"tag_code": tag_code})
                continue
            selected.append(tag_code)
        current_version = BankTransactionCategoryService._normalize_version(raw_payload.get("version", 1)) or 1
        next_version = current_version + 1 if detached else current_version
        return {
            **dict(raw_payload),
            "version": next_version,
            "selected_tag_codes": selected,
        }, detached

    @staticmethod
    def _normalize_option_list(
        values: Any,
        *,
        allowed_values: list[str],
        default_values: list[str],
        preserve_empty: bool,
    ) -> list[str]:
        if not isinstance(values, list):
            return list(default_values)
        allowed_set = set(allowed_values)
        normalized = []
        seen = set()
        for item in values:
            value = str(item).strip()
            if value not in allowed_set or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        if normalized or preserve_empty:
            return [value for value in allowed_values if value in seen]
        return list(default_values)

    @staticmethod
    def _normalize_available_options(
        values: Any,
        *,
        defaults: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        allowed_labels = {str(item["id"]): str(item["label"]) for item in defaults}
        seen: set[str] = set()
        normalized: list[dict[str, str]] = []
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                option_id = str(item.get("id", "")).strip()
                if option_id not in allowed_labels or option_id in seen:
                    continue
                seen.add(option_id)
                normalized.append({"id": option_id, "label": allowed_labels[option_id]})
        if normalized:
            return normalized
        return [dict(item) for item in defaults]


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
