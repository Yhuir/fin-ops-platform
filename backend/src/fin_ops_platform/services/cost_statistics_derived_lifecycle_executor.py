from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService


class CostStatisticsDerivedLifecycleExecutor:
    def __init__(
        self,
        *,
        runtime_service: CostStatisticsRuntimeService,
        enqueue_refresh: Callable[..., bool],
    ) -> None:
        self._runtime_service = runtime_service
        self._enqueue_refresh = enqueue_refresh

    def execute(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        reason = str(domain_plan.get("reason") or "derived_lifecycle_cost_statistics")
        target_scope_keys = ["all"] if "all" in scope_keys else scope_keys
        enqueued = self._enqueue_refresh(
            target_scope_keys or ["all"],
            reason=reason,
            metadata=self._read_model_refresh_metadata(domain_plan),
        )
        deleted_scope_keys = (
            self._runtime_service.refresh_scope_keys_from_scope_keys(list(target_scope_keys or ["all"]))
            if enqueued
            else []
        )

        return {
            "deleted_counts": {"cost_statistics_read_models": len(deleted_scope_keys)},
            "invalidated_scopes": deleted_scope_keys,
            "enqueued_jobs": ["cost_statistics.read_model.refresh"] if enqueued else [],
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]

    @staticmethod
    def _read_model_refresh_metadata(domain_plan: dict[str, object]) -> dict[str, object] | None:
        metadata = domain_plan.get("metadata")
        if not isinstance(metadata, dict):
            return None
        refresh_metadata: dict[str, object] = {}
        for key in (
            "source",
            "case_id",
            "action_name",
            "downstream_scope_types",
            "invoice_usage_scope_types",
            "pending_invoice_scope_keys",
        ):
            if key in metadata:
                refresh_metadata[key] = metadata[key]
        action_name = str(metadata.get("action_name") or "").strip()
        if action_name:
            refresh_metadata["action_name"] = action_name
        return refresh_metadata or None
