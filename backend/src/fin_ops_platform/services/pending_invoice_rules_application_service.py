from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.pending_invoice_rules import (
    editable_pending_invoice_tag_groups_payload,
    pending_invoice_rules_payload,
)


class AppSettingsPendingInvoiceRulesGateway:
    def __init__(self, app_settings_service: Any) -> None:
        self._app_settings_service = app_settings_service

    def get_pending_invoice_settings_payload(self) -> dict[str, Any]:
        return self._app_settings_service.get_pending_invoice_settings_payload()

    def update_pending_invoice_rule_groups(
        self,
        *,
        direction: str,
        editable_groups: dict[str, Any],
        actor_id: str,
        after_bank_transaction_tag_settings_saved: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        current = self.get_pending_invoice_settings_payload()
        access_control = current.get("access_control") if isinstance(current.get("access_control"), dict) else {}
        projects = current.get("projects") if isinstance(current.get("projects"), dict) else {}
        normalized_direction = str(direction or "").strip()
        self._app_settings_service.update_settings(
            completed_project_ids=list(projects.get("completed_project_ids") or projects.get("completed") or []),
            bank_account_mappings=list(current.get("bank_account_mappings") or []),
            allowed_usernames=list(access_control.get("allowed_usernames") or []),
            readonly_export_usernames=list(access_control.get("readonly_export_usernames") or []),
            admin_usernames=list(access_control.get("admin_usernames") or []),
            workbench_column_layouts=current.get("workbench_column_layouts") if isinstance(current.get("workbench_column_layouts"), dict) else {},
            oa_retention=current.get("oa_retention") if isinstance(current.get("oa_retention"), dict) else {},
            oa_import=current.get("oa_import") if isinstance(current.get("oa_import"), dict) else {},
            oa_invoice_offset=current.get("oa_invoice_offset") if isinstance(current.get("oa_invoice_offset"), dict) else {},
            bank_transaction_tags=None,
            pending_invoice_tag_groups=editable_groups if normalized_direction != "income" else None,
            pending_output_invoice_tag_groups=editable_groups if normalized_direction == "income" else None,
            actor_id=actor_id or "pending_invoice_rules",
            after_bank_transaction_tag_settings_saved=after_bank_transaction_tag_settings_saved,
        )


class PendingInvoiceRulesApplicationService:
    def __init__(
        self,
        *,
        settings_gateway: Any | None = None,
        app_settings_service: Any | None = None,
        persist_callback: Callable[[], None] | None = None,
        invalidate_read_model_scopes: Callable[[str], None] | None = None,
        after_bank_transaction_tag_settings_saved: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if settings_gateway is None:
            if app_settings_service is None:
                raise ValueError("settings_gateway is required for pending invoice rules.")
            settings_gateway = AppSettingsPendingInvoiceRulesGateway(app_settings_service)
        self._settings_gateway = settings_gateway
        self._persist_callback = persist_callback
        self._invalidate_read_model_scopes = invalidate_read_model_scopes
        self._after_bank_transaction_tag_settings_saved = after_bank_transaction_tag_settings_saved

    def get_rules(self, *, direction: str, can_save: bool) -> dict[str, Any]:
        rules_payload = pending_invoice_rules_payload(
            self._settings_gateway.get_pending_invoice_settings_payload(),
            direction=direction,
        )
        rules_payload["permissions"] = {"can_save": bool(can_save)}
        return rules_payload

    def update_rules(self, *, direction: str, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        pending_invoice_tag_groups = payload.get("pending_invoice_tag_groups", payload)
        if str(direction or "").strip() == "income":
            pending_invoice_tag_groups = payload.get("pending_output_invoice_tag_groups", pending_invoice_tag_groups)
        if not isinstance(pending_invoice_tag_groups, dict):
            raise ValueError("pending_invoice_tag_groups must be an object.")

        editable_groups = editable_pending_invoice_tag_groups_payload(
            pending_invoice_tag_groups,
            direction=direction,
        )
        self._settings_gateway.update_pending_invoice_rule_groups(
            direction=direction,
            editable_groups=editable_groups,
            actor_id=actor_id or "pending_invoice_rules",
            after_bank_transaction_tag_settings_saved=self._after_bank_transaction_tag_settings_saved,
        )
        if self._persist_callback is not None:
            self._persist_callback()
        if self._invalidate_read_model_scopes is not None:
            self._invalidate_read_model_scopes("pending_invoice_rules_update")
        rules_payload = pending_invoice_rules_payload(
            self._settings_gateway.get_pending_invoice_settings_payload(),
            direction=direction,
        )
        rules_payload["permissions"] = {"can_save": True}
        return rules_payload
