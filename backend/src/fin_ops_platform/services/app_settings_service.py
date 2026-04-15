from __future__ import annotations

from datetime import datetime
from typing import Any

from fin_ops_platform.domain.models import ProjectMaster
from fin_ops_platform.services.access_control_service import DEFAULT_ADMIN_USERNAME
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.state_store import ApplicationStateStore

DEFAULT_OA_RETENTION_CUTOFF_DATE = "2026-01-01"
DEFAULT_OA_INVOICE_OFFSET_APPLICANTS = ["周洁莹"]
DEFAULT_WORKBENCH_COLUMN_LAYOUTS = {
    "oa": ["applicant", "projectName", "amount", "counterparty", "reason"],
    "bank": ["counterparty", "amount", "loanRepaymentDate", "note"],
    "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
}


class AppSettingsService:
    def __init__(
        self,
        state_store: ApplicationStateStore | None,
        project_costing_service: ProjectCostingService,
        oa_role_sync_service: OARoleSyncService | None = None,
    ) -> None:
        self._state_store = state_store
        self._project_costing_service = project_costing_service
        self._oa_role_sync_service = oa_role_sync_service
        self._snapshot = self._normalize_settings(
            state_store.load_app_settings() if state_store is not None else {}
        )
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
            "oa_invoice_offset": {
                "applicant_names": list(self._snapshot["oa_invoice_offset"]["applicant_names"]),
            },
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
        oa_invoice_offset: dict[str, Any] | None = None,
        manual_projects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_snapshot = self._normalize_settings(
            {
                "completed_project_ids": completed_project_ids,
                "bank_account_mappings": bank_account_mappings,
                "allowed_usernames": allowed_usernames,
                "readonly_export_usernames": readonly_export_usernames or [],
                "admin_usernames": admin_usernames or [],
                "workbench_column_layouts": workbench_column_layouts or {},
                "oa_retention": oa_retention or {},
                "oa_invoice_offset": oa_invoice_offset or {},
                "manual_projects": (
                    manual_projects
                    if manual_projects is not None
                    else self._snapshot.get("manual_projects", [])
                ),
                "synced_projects": self._snapshot.get("synced_projects", []),
            }
        )
        previous_snapshot = dict(self._snapshot)
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
        self._restore_manual_projects()
        return self.get_settings_payload()

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
        normalized_snapshot = self._normalize_settings(snapshot)
        if self._state_store is not None:
            self._state_store.save_app_settings(normalized_snapshot)
        self._snapshot = normalized_snapshot
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
    def _normalize_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
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
            "oa_invoice_offset": {"applicant_names": applicant_names},
        }


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
