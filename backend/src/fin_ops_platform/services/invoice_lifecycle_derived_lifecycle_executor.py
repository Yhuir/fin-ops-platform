from __future__ import annotations

class InvoiceLifecycleDerivedLifecycleExecutor:
    def execute(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        target_scope_keys = scope_keys or ["all"]
        return {
            "deleted_counts": {"invoice_lifecycle_read_models": 0},
            "invalidated_scopes": target_scope_keys,
            "enqueued_jobs": [],
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]
