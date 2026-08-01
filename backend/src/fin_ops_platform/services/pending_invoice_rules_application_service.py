from __future__ import annotations

from typing import Any

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
        expected_version: int | None = None,
    ) -> dict[str, Any] | None:
        return self._app_settings_service.update_pending_invoice_rule_groups(
            direction=direction,
            editable_groups=editable_groups,
            expected_version=expected_version,
            actor_id=actor_id,
        )


class PendingInvoiceRulesApplicationService:
    def __init__(
        self,
        *,
        settings_gateway: Any | None = None,
        app_settings_service: Any | None = None,
    ) -> None:
        if settings_gateway is None:
            if app_settings_service is None:
                raise ValueError("settings_gateway is required for pending invoice rules.")
            settings_gateway = AppSettingsPendingInvoiceRulesGateway(app_settings_service)
        self._settings_gateway = settings_gateway

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
        expected_version = _optional_int(pending_invoice_tag_groups.get("version"))
        self._settings_gateway.update_pending_invoice_rule_groups(
            direction=direction,
            editable_groups=editable_groups,
            expected_version=expected_version,
            actor_id=actor_id or "pending_invoice_rules",
        )
        rules_payload = pending_invoice_rules_payload(
            self._settings_gateway.get_pending_invoice_settings_payload(),
            direction=direction,
        )
        rules_payload["permissions"] = {"can_save": True}
        return rules_payload


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
