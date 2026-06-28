from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.audit import AuditTrailService


class BankDetailCategoryMutationSideEffectPort:
    """Explicit side-effect boundary for bank detail category mutations."""

    def __init__(
        self,
        *,
        enqueue_turnover_ledger_refresh: Callable[..., bool],
        invalidate_workbench_after_category_mutation: Callable[[list[str]], bool],
        audit_service: AuditTrailService,
    ) -> None:
        self._enqueue_turnover_ledger_refresh = enqueue_turnover_ledger_refresh
        self._invalidate_workbench_after_category_mutation = invalidate_workbench_after_category_mutation
        self._audit_service = audit_service

    def after_mutation(
        self,
        *,
        transaction_id: str,
        actor_id: str,
        action: str,
        affected_months: list[str],
        metadata: dict[str, object],
    ) -> None:
        self._enqueue_turnover_ledger_refresh(
            ["all"],
            reason="bank_detail_category_confirmation_changed",
        )
        self._invalidate_workbench_after_category_mutation(affected_months)
        self._audit_service.record_action(
            actor_id=actor_id,
            action=action,
            entity_type="bank_transaction_category_confirmation",
            entity_id=str(transaction_id or ""),
            metadata={
                "transaction_id": str(transaction_id or ""),
                "affected_months": list(affected_months or []),
                **dict(metadata),
            },
        )
