from __future__ import annotations

from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService


class CostStatisticsDerivedLifecycleExecutor:
    def __init__(
        self,
        *,
        runtime_service: CostStatisticsRuntimeService,
    ) -> None:
        self._runtime_service = runtime_service

    def execute(self, domain_plan: dict[str, object], *, schedule_warmup: bool) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        reason = str(domain_plan.get("reason") or "derived_lifecycle_cost_statistics")
        persist_empty = reason != "pending_invoice_rules_changed"
        if "all" in scope_keys:
            deleted_scope_keys = self._runtime_service.invalidate_read_models(
                schedule_warmup=schedule_warmup,
                persist_empty=persist_empty,
            )
        else:
            deleted_scope_keys = self._runtime_service.invalidate_read_model_scopes(
                scope_keys,
                reason=reason,
                schedule_warmup=schedule_warmup,
                persist_empty=persist_empty,
            )

        enqueued_jobs: list[str] = []
        if not schedule_warmup and not deleted_scope_keys:
            target_scope_keys = ["all"] if "all" in scope_keys else scope_keys
            deleted_scope_keys = list(target_scope_keys or ["all"])
        if schedule_warmup:
            enqueued_jobs.append("cost_statistics_cache_warmup")

        return {
            "deleted_counts": {"cost_statistics_cache_scopes": len(deleted_scope_keys)},
            "invalidated_scopes": deleted_scope_keys,
            "enqueued_jobs": enqueued_jobs,
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]
