from __future__ import annotations

from typing import Any, Callable


DerivedLifecycleExecutor = Callable[..., dict[str, object]]


class PendingInvoiceLifecycleService:
    def __init__(
        self,
        *,
        audit_service: Any,
        execute_derived_data_lifecycle_event: DerivedLifecycleExecutor,
        relation_tag_projection_service: Any | None = None,
    ) -> None:
        self._audit_service = audit_service
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event
        self._relation_tag_projection_service = relation_tag_projection_service

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

    def finalize_manual_invoice(self, event: dict[str, object]) -> None:
        affected_months = [
            str(month)
            for month in list(event.get("affected_months") or [])
            if str(month).strip()
        ]
        action = str(event.get("action") or "pending_invoice_manual_invoice_confirmed")
        source = str(event.get("source") or event.get("entity_type") or "")
        if not source:
            source = (
                "pending_invoice_attach_existing_invoice"
                if action == "pending_invoice_attach_existing_invoice_confirmed"
                else "pending_invoice_manual_invoice"
            )
        self._execute_derived_data_lifecycle_event(
            action,
            months=affected_months,
            metadata={"source": source, **dict(event)},
            schedule_cost_warmup=False,
        )
        if self._relation_tag_projection_service is not None:
            try:
                setattr(self._relation_tag_projection_service, "_index_cache_key", "")
                setattr(self._relation_tag_projection_service, "_index_cache", {})
            except Exception:
                pass
