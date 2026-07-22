from __future__ import annotations

from typing import Any


class PendingInvoiceLifecycleService:
    def __init__(
        self,
        *,
        audit_service: Any,
    ) -> None:
        self._audit_service = audit_service

    def record_manual_invoice_audit(self, event: dict[str, object]) -> None:
        action = str(event.get("action") or "pending_invoice_manual_invoice_confirmed")
        entity_type = str(event.get("entity_type") or event.get("source") or "")
        if not entity_type:
            entity_type = (
                "pending_invoice_attach_existing_invoice"
                if action == "pending_invoice_attach_existing_invoice_confirmed"
                else "pending_invoice_manual_invoice"
            )
        self._audit_service.record_action(
            actor_id=str(event.get("actor_id") or "pending_invoice"),
            action=action,
            entity_type=entity_type,
            entity_id=str(event.get("request_id") or event.get("invoice_id") or ""),
            metadata=dict(event),
        )
