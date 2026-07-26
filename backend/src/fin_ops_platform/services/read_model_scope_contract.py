from __future__ import annotations

from typing import Any, Protocol

from fin_ops_platform.services.read_model_scope_policy import (
    DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ReadModelScopeError,
    ReadModelScopePolicyRegistry,
)


class ReadModelScopeContractRepository(Protocol):
    def list_policy_managed_dirty_scopes(self) -> list[dict[str, Any]]: ...
    def list_policy_managed_outbox_events(self) -> list[dict[str, Any]]: ...
    def list_policy_managed_readiness(self) -> list[dict[str, Any]]: ...
    def list_orphaned_import_fact_dirty_scopes(self) -> list[dict[str, Any]]: ...
    def delete_dirty_scope(self, row_id: str) -> int: ...
    def delete_outbox_event(self, row_id: str) -> int: ...
    def delete_readiness(
        self,
        *,
        tenant_id: str,
        read_model_key: str,
        scope_type: str,
        scope_key: str,
    ) -> int: ...
    def record_repair_audit(self, event: dict[str, Any]) -> str: ...


class ReadModelScopeContractService:
    def __init__(
        self,
        repository: ReadModelScopeContractRepository,
        *,
        scope_policy_registry: ReadModelScopePolicyRegistry = (
            DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY
        ),
    ) -> None:
        self._repository = repository
        self._scope_policy_registry = scope_policy_registry

    def check_orphaned_import_fact_dirty_scopes(self) -> dict[str, Any]:
        return self.repair_orphaned_import_fact_dirty_scopes(apply=False)

    def check_invalid_read_model_refresh_scopes(self) -> dict[str, Any]:
        return self.repair_invalid_read_model_refresh_scopes(apply=False)

    def repair_invalid_read_model_refresh_scopes(
        self,
        *,
        apply: bool,
        reason: str = "invalid_read_model_refresh_scope_repair",
    ) -> dict[str, Any]:
        rows = self._invalid_read_model_refresh_scope_rows()
        cleanup = {
            "applied": apply,
            "deleted": {
                "job.read_model_dirty_scopes": 0,
                "job.outbox_events": 0,
                "read_model.app_status_readiness": 0,
            },
        }
        if apply:
            for item in rows:
                location = str(item.get("location") or "")
                row = dict(item.get("row") or {})
                if location == "job.read_model_dirty_scopes":
                    cleanup["deleted"][location] += self._repository.delete_dirty_scope(
                        str(row.get("id") or "")
                    )
                elif location == "job.outbox_events":
                    cleanup["deleted"][location] += self._repository.delete_outbox_event(
                        str(row.get("id") or "")
                    )
                elif location == "read_model.app_status_readiness":
                    cleanup["deleted"][location] += self._repository.delete_readiness(
                        tenant_id=str(row.get("tenant_id") or "default"),
                        read_model_key=str(
                            row.get("read_model_key")
                            or item.get("scope_type")
                            or ""
                        ),
                        scope_type=str(
                            row.get("scope_type") or item.get("scope_type") or ""
                        ),
                        scope_key=str(
                            row.get("scope_key") or item.get("scope_key") or ""
                        ),
                    )
        report = _invalid_scope_report(rows, cleanup=cleanup)
        if apply and rows:
            report["repair_audit"] = self._record_repair_audit(
                event_type="invalid_read_model_refresh_scope_repair",
                object_id="invalid_read_model_refresh_scopes",
                reason=reason,
                report=report,
            )
        return report

    def repair_orphaned_import_fact_dirty_scopes(
        self,
        *,
        apply: bool,
        reason: str = "orphaned_import_fact_dirty_scope_repair",
    ) -> dict[str, Any]:
        list_scopes = getattr(
            self._repository,
            "list_orphaned_import_fact_dirty_scopes",
            None,
        )
        rows = (
            [dict(row) for row in list_scopes()]
            if callable(list_scopes)
            else []
        )
        cleanup = {
            "applied": apply,
            "deleted": {"job.read_model_dirty_scopes": 0},
        }
        if apply:
            for row in rows:
                cleanup["deleted"][
                    "job.read_model_dirty_scopes"
                ] += self._repository.delete_dirty_scope(str(row.get("id") or ""))
        report = _orphaned_import_fact_report(rows, cleanup=cleanup)
        if apply and rows:
            report["repair_audit"] = self._record_repair_audit(
                event_type="orphaned_import_fact_dirty_scope_repair",
                object_id="import_facts_changed",
                reason=reason,
                report=report,
            )
        return report

    def _invalid_read_model_refresh_scope_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sources = (
            (
                "job.read_model_dirty_scopes",
                self._repository.list_policy_managed_dirty_scopes,
            ),
            (
                "job.outbox_events",
                self._repository.list_policy_managed_outbox_events,
            ),
            (
                "read_model.app_status_readiness",
                self._repository.list_policy_managed_readiness,
            ),
        )
        for location, list_rows in sources:
            for row in list_rows():
                scope_type = str(row.get("scope_type") or "").strip()
                scope_key = str(row.get("scope_key") or "").strip()
                try:
                    self._scope_policy_registry.normalize_and_validate(
                        scope_type,
                        [scope_key],
                    )
                except ReadModelScopeError as exc:
                    rows.append(
                        {
                            "location": location,
                            "scope_type": scope_type,
                            "scope_key": scope_key,
                            "error": str(exc),
                            "row": dict(row),
                        }
                    )
        return rows

    def _record_repair_audit(
        self,
        *,
        event_type: str,
        object_id: str,
        reason: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        record = getattr(self._repository, "record_repair_audit", None)
        if not callable(record):
            return {
                "enabled": True,
                "recorded": False,
                "event_id": "",
                "reason": "repository_does_not_support_audit",
            }
        event_id = record(
            {
                "event_type": event_type,
                "object_type": "read_model_runtime_repair",
                "object_id": object_id,
                "reason": reason,
                "payload": {
                    "reason": reason,
                    "cleanup": report.get("cleanup") or {},
                    "items": report.get("items") or [],
                    "rollback": report.get("rollback") or {},
                },
            }
        )
        return {
            "enabled": True,
            "recorded": True,
            "event_id": event_id,
        }


def _invalid_scope_report(
    rows: list[dict[str, Any]],
    *,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    items = [_invalid_scope_item(row) for row in rows]
    return {
        "action": "invalid_read_model_refresh_scope_check",
        "ok": not rows,
        "invalid_scope_count": len(rows),
        "summary": {
            location: sum(1 for item in items if item["location"] == location)
            for location in (
                "job.read_model_dirty_scopes",
                "job.outbox_events",
                "read_model.app_status_readiness",
            )
        },
        "cleanup": cleanup,
        "items": items,
        "rollback": {
            "strategy": "restore deleted runtime rows from items[].row if operator cleanup is reverted.",
            "manifest_item_count": len(items),
        },
        "repair_audit": {
            "enabled": bool(cleanup.get("applied")),
            "recorded": False,
            "event_id": "",
        },
    }


def _orphaned_import_fact_report(
    rows: list[dict[str, Any]],
    *,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    items = [
        {
            **_base_item(
                row,
                location="job.read_model_dirty_scopes",
            ),
            "category": "orphaned_import_fact_dirty_scope",
            "proposed_action": "delete_orphaned_legacy_import_fact_dirty_scope",
        }
        for row in rows
    ]
    return {
        "action": "orphaned_import_fact_dirty_scope_check",
        "ok": not rows,
        "orphaned_dirty_scope_count": len(rows),
        "cleanup": cleanup,
        "items": items,
        "rollback": {
            "strategy": "restore deleted job.read_model_dirty_scopes rows from items[].row if operator cleanup is reverted.",
            "manifest_item_count": len(items),
        },
        "repair_audit": {
            "enabled": bool(cleanup.get("applied")),
            "recorded": False,
            "event_id": "",
        },
    }


def _invalid_scope_item(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item.get("row") or {})
    location = str(item.get("location") or "")
    return {
        **_base_item(row, location=location),
        "category": "invalid_read_model_refresh_scope",
        "scope_type": str(item.get("scope_type") or row.get("scope_type") or ""),
        "scope_key": str(item.get("scope_key") or row.get("scope_key") or ""),
        "policy_error": str(item.get("error") or ""),
        "proposed_action": "delete_invalid_runtime_row_no_replacement",
    }


def _base_item(
    row: dict[str, Any],
    *,
    location: str,
) -> dict[str, Any]:
    return {
        "location": location,
        "row_id": str(row.get("id") or ""),
        "tenant_id": str(row.get("tenant_id") or "default"),
        "scope_type": str(row.get("scope_type") or ""),
        "scope_key": str(row.get("scope_key") or ""),
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "reason": str(row.get("reason") or ""),
        "last_error": str(row.get("last_error") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "rollback_hint": f"restore {location} row from item.row before rerun",
        "row": dict(row),
    }
