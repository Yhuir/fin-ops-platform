from __future__ import annotations

from typing import Callable


class BankAccountBalanceDerivedLifecycleExecutor:
    def __init__(self, *, enqueue_refresh: Callable[..., bool]) -> None:
        self._enqueue_refresh = enqueue_refresh

    def execute(self, domain_plan: dict[str, object]) -> dict[str, object]:
        enqueued = self._enqueue_refresh(
            reason=str(domain_plan.get("reason") or "derived_lifecycle_bank_account_balance")
        )
        return {
            "deleted_counts": {"bank_account_balance_read_models": 0},
            "invalidated_scopes": ["all"],
            "enqueued_jobs": ["bank_account_balance.read_model.refresh"] if enqueued else [],
        }
