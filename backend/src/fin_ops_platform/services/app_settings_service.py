from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fin_ops_platform.domain.models import ProjectMaster
from fin_ops_platform.services.access_control_service import DEFAULT_ADMIN_USERNAME
from fin_ops_platform.services.bank_transaction_category_service import (
    BankAutoTagRulesValidationError,
    BankTransactionCategoryService,
    default_bank_transaction_tag_dictionary_payload,
)
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.state_store import ApplicationStateStore

DEFAULT_OA_RETENTION_CUTOFF_DATE = "2026-01-01"
DEFAULT_OA_INVOICE_OFFSET_APPLICANTS = ["周洁莹"]
DEFAULT_OA_IMPORT_FORM_TYPES = ["payment_request", "expense_claim"]
DEFAULT_OA_IMPORT_STATUSES = ["completed"]
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


class AppSettingsValidationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class AppSettingsService:
    def __init__(
        self,
        state_store: ApplicationStateStore | None,
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

    def get_settings_payload(self) -> dict[str, Any]:
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
                "available_form_types": oa_import_options["available_form_types"],
                "available_statuses": oa_import_options["available_statuses"],
            },
            "oa_invoice_offset": {
                "applicant_names": list(self._snapshot["oa_invoice_offset"]["applicant_names"]),
            },
            "bank_transaction_tags": self._public_bank_transaction_tags(self._snapshot["bank_transaction_tags"]),
            "pending_invoice_tag_groups": self._public_pending_invoice_tag_groups(
                self._snapshot["pending_invoice_tag_groups"],
                version=int(self._snapshot["bank_transaction_tags"]["version"]),
            ),
        }

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
        bank_transaction_tags: dict[str, Any] | None = None,
        pending_invoice_tag_groups: dict[str, Any] | None = None,
        actor_id: str | None = None,
        after_bank_transaction_tag_settings_saved: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        previous_snapshot = dict(self._snapshot)
        self._validate_bank_transaction_tag_settings_update(
            previous_snapshot,
            bank_transaction_tags=bank_transaction_tags,
            pending_invoice_tag_groups=pending_invoice_tag_groups,
        )
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
                "bank_transaction_tags": (
                    bank_transaction_tags
                    if bank_transaction_tags is not None
                    else self._snapshot.get("bank_transaction_tags", {})
                ),
                "pending_invoice_tag_groups": (
                    pending_invoice_tag_groups
                    if pending_invoice_tag_groups is not None
                    else self._snapshot.get("pending_invoice_tag_groups", {})
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
            version = int(previous_snapshot["bank_transaction_tags"]["version"]) + 1
            normalized_snapshot["bank_transaction_tags"]["version"] = version
            normalized_snapshot["pending_invoice_tag_groups"]["version"] = version
            tag_settings_event["new_version"] = version
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

    def get_bank_auto_tag_rules_payload(
        self,
        *,
        can_save: bool = True,
        read_model_status: str | None = None,
    ) -> dict[str, Any]:
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
        after_bank_auto_tag_rules_saved: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        previous_snapshot = dict(self._snapshot)
        previous_tags = previous_snapshot["bank_transaction_tags"]
        normalized = BankTransactionCategoryService.normalize_auto_tag_rules_update(
            payload,
            previous_tag_dictionary=previous_tags,
            references_by_code=self._pending_invoice_reference_map(previous_snapshot["pending_invoice_tag_groups"]),
        )
        next_tags = normalized["tag_dictionary"]
        if not normalized["changes"]["changed"]:
            return self.get_bank_auto_tag_rules_payload(can_save=True)

        next_snapshot = dict(self._snapshot)
        next_snapshot["bank_transaction_tags"] = next_tags
        next_snapshot["pending_invoice_tag_groups"] = {
            **self._snapshot["pending_invoice_tag_groups"],
            "version": int(next_tags["version"]),
        }
        try:
            if self._state_store is not None:
                self._state_store.save_app_settings(next_snapshot)
        except Exception:
            raise
        self._snapshot = next_snapshot
        self._configure_category_service(next_snapshot)
        event = {
            "actor_id": str(actor_id or "bank_auto_tag_rules").strip() or "bank_auto_tag_rules",
            "old_version": int(normalized["old_version"]),
            "new_version": int(normalized["new_version"]),
            **normalized["changes"],
        }
        self._record_bank_auto_tag_rules_audit(event)
        if after_bank_auto_tag_rules_saved is not None:
            after_bank_auto_tag_rules_saved(dict(event))
        return self.get_bank_auto_tag_rules_payload(can_save=True)

    def sync_oa_projects(self, *, actor_id: str) -> dict[str, Any]:
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
        return {
            item["last4"]: item["bank_name"]
            for item in self._snapshot["bank_account_mappings"]
        }

    def get_completed_project_ids(self) -> set[str]:
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
        return str(self._snapshot["oa_retention"]["cutoff_date"])

    def get_oa_import_settings(self) -> dict[str, list[str]]:
        return {
            "form_types": list(self._snapshot["oa_import"]["form_types"]),
            "statuses": list(self._snapshot["oa_import"]["statuses"]),
        }

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
        return list(self._snapshot["oa_invoice_offset"]["applicant_names"])

    def get_allowed_usernames(self) -> list[str]:
        return list(self._snapshot["allowed_usernames"])

    def get_readonly_export_usernames(self) -> list[str]:
        return list(self._snapshot["readonly_export_usernames"])

    def get_admin_usernames(self) -> list[str]:
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
            },
            "oa_invoice_offset": {"applicant_names": applicant_names},
            "bank_transaction_tags": bank_transaction_tags,
            "pending_invoice_tag_groups": pending_invoice_tag_groups,
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
    ) -> dict[str, Any]:
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
        for group_id, label in PENDING_INVOICE_TAG_GROUP_LABELS.items():
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
                }
                for definition in list(payload.get("definitions") or [])
                if isinstance(definition, dict)
            ],
        }

    @staticmethod
    def _public_pending_invoice_tag_groups(payload: dict[str, Any], *, version: int) -> dict[str, Any]:
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
                for group_id, label in PENDING_INVOICE_TAG_GROUP_LABELS.items()
            },
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
        )
        tags_without_version = {key: value for key, value in tags.items() if key != "version"}
        groups_without_version = {key: value for key, value in groups.items() if key != "version"}
        return {
            "bank_transaction_tags": tags_without_version,
            "pending_invoice_tag_groups": groups_without_version,
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
        )
        if not tags_changed and not groups_changed:
            return None
        affected_groups = self._affected_pending_invoice_groups(
            previous_snapshot["pending_invoice_tag_groups"],
            next_snapshot["pending_invoice_tag_groups"],
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

    @staticmethod
    def _affected_pending_invoice_groups(
        previous_groups_payload: dict[str, Any],
        next_groups_payload: dict[str, Any],
    ) -> list[str]:
        previous_groups = previous_groups_payload.get("groups") if isinstance(previous_groups_payload.get("groups"), dict) else {}
        next_groups = next_groups_payload.get("groups") if isinstance(next_groups_payload.get("groups"), dict) else {}
        affected = []
        for group_id in PENDING_INVOICE_TAG_GROUP_LABELS:
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
            },
        )

    @staticmethod
    def _validate_bank_transaction_tag_settings_update(
        previous_snapshot: dict[str, Any],
        *,
        bank_transaction_tags: dict[str, Any] | None,
        pending_invoice_tag_groups: dict[str, Any] | None,
    ) -> None:
        previous_tags = previous_snapshot["bank_transaction_tags"]
        previous_version = int(previous_tags.get("version") or 1)
        if isinstance(bank_transaction_tags, dict):
            requested_version = BankTransactionCategoryService._normalize_version(
                bank_transaction_tags.get("version", 1)
            )
            if requested_version <= 0:
                requested_version = 1
            if requested_version != previous_version:
                raise AppSettingsValidationError(
                    "bank_transaction_tags_version_conflict",
                    "Bank transaction tag settings version conflict.",
                )

        if not isinstance(bank_transaction_tags, dict):
            return

        next_tags = AppSettingsService._normalize_bank_transaction_tags(bank_transaction_tags)
        previous_definitions = {
            str(definition["code"]): dict(definition)
            for definition in list(previous_tags.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        next_definitions = {
            str(definition["code"]): dict(definition)
            for definition in list(next_tags.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        newly_archived_codes = {
            code
            for code, previous_definition in previous_definitions.items()
            if previous_definition.get("status") != "archived"
            and next_definitions.get(code, {}).get("status") == "archived"
        }
        if not newly_archived_codes:
            return

        mapped_codes = AppSettingsService._pending_invoice_tag_codes_for_archive_guard(
            pending_invoice_tag_groups,
            fallback_groups=previous_snapshot["pending_invoice_tag_groups"],
        )
        blocked_codes = sorted(newly_archived_codes.intersection(mapped_codes))
        if blocked_codes:
            raise AppSettingsValidationError(
                "bank_transaction_tag_in_use_by_pending_invoice_filter",
                f"Bank transaction tag is still mapped to pending invoice filters: {blocked_codes[0]}",
            )

    @staticmethod
    def _pending_invoice_tag_codes_for_archive_guard(
        value: Any,
        *,
        fallback_groups: dict[str, Any],
    ) -> set[str]:
        raw_payload = value if isinstance(value, dict) else fallback_groups
        raw_groups = raw_payload.get("groups") if isinstance(raw_payload.get("groups"), dict) else raw_payload
        if not isinstance(raw_groups, dict):
            raw_groups = {}
        mapped_codes: set[str] = set()
        for group_id in PENDING_INVOICE_TAG_GROUP_LABELS:
            raw_group = raw_groups.get(group_id)
            if isinstance(raw_group, dict):
                raw_codes = raw_group.get("tag_codes")
            elif isinstance(raw_group, list):
                raw_codes = raw_group
            else:
                raw_codes = []
            mapped_codes.update(
                str(item or "").strip()
                for item in list(raw_codes or [])
                if str(item or "").strip()
            )
        return mapped_codes

    @staticmethod
    def _pending_invoice_reference_map(value: Any) -> dict[str, list[dict[str, Any]]]:
        raw_payload = value if isinstance(value, dict) else {}
        raw_groups = raw_payload.get("groups") if isinstance(raw_payload.get("groups"), dict) else raw_payload
        if not isinstance(raw_groups, dict):
            raw_groups = {}
        references: dict[str, list[dict[str, Any]]] = {}
        for group_id, default_label in PENDING_INVOICE_TAG_GROUP_LABELS.items():
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
                        "domain": "pending_invoice_tag_groups",
                        "label": f"待找发票规则：{label}",
                        "tag_code": tag_code,
                    }
                )
        return references

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
