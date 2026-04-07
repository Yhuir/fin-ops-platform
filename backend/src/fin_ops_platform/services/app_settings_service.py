from __future__ import annotations

from typing import Any

from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.state_store import ApplicationStateStore


class AppSettingsService:
    def __init__(
        self,
        state_store: ApplicationStateStore | None,
        project_costing_service: ProjectCostingService,
    ) -> None:
        self._state_store = state_store
        self._project_costing_service = project_costing_service
        self._snapshot = self._normalize_settings(
            state_store.load_app_settings() if state_store is not None else {}
        )

    def get_settings_payload(self) -> dict[str, Any]:
        completed_ids = set(self._snapshot["completed_project_ids"])
        active_projects: list[dict[str, Any]] = []
        completed_projects: list[dict[str, Any]] = []
        for project in self._project_costing_service.list_projects():
            payload = {
                "id": project.id,
                "project_code": project.project_code,
                "project_name": project.project_name,
                "project_status": "completed" if project.id in completed_ids else "active",
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
            },
        }

    def update_settings(
        self,
        *,
        completed_project_ids: list[str],
        bank_account_mappings: list[dict[str, Any]],
        allowed_usernames: list[str],
    ) -> dict[str, Any]:
        self._snapshot = self._normalize_settings(
            {
                "completed_project_ids": completed_project_ids,
                "bank_account_mappings": bank_account_mappings,
                "allowed_usernames": allowed_usernames,
            }
        )
        if self._state_store is not None:
            self._state_store.save_app_settings(self._snapshot)
        return self.get_settings_payload()

    def get_bank_account_mapping_dict(self) -> dict[str, str]:
        return {
            item["last4"]: item["bank_name"]
            for item in self._snapshot["bank_account_mappings"]
        }

    def get_completed_project_ids(self) -> set[str]:
        return set(self._snapshot["completed_project_ids"])

    def get_allowed_usernames(self) -> list[str]:
        return list(self._snapshot["allowed_usernames"])

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
        allowed_usernames = sorted(
            {
                str(username).strip()
                for username in list(raw_payload.get("allowed_usernames") or [])
                if str(username).strip()
            }
        )
        return {
            "completed_project_ids": completed_ids,
            "bank_account_mappings": mappings,
            "allowed_usernames": allowed_usernames,
        }
