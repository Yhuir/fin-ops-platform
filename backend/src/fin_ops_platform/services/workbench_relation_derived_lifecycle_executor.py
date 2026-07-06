from __future__ import annotations

from typing import Callable


class WorkbenchRelationDerivedLifecycleExecutor:
    def __init__(self, *, enqueue_refresh: Callable[..., bool]) -> None:
        self._enqueue_refresh = enqueue_refresh

    def execute(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        target_scope_keys = scope_keys or ["all"]
        enqueued = self._enqueue_refresh(
            target_scope_keys,
            reason=str(domain_plan.get("reason") or "derived_lifecycle_workbench_relation"),
            metadata=self._read_model_refresh_metadata(domain_plan),
        )
        return {
            "deleted_counts": {"workbench_relation_read_models": 0},
            "invalidated_scopes": target_scope_keys,
            "enqueued_jobs": ["workbench_relation.read_model.refresh"] if enqueued else [],
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
            "row_ids",
            "case_ids",
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
