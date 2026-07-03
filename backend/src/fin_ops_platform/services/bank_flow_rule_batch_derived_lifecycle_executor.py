from __future__ import annotations

import re
from typing import Callable


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class BankFlowRuleBatchDerivedLifecycleExecutor:
    def __init__(self, *, enqueue_refresh: Callable[..., bool]) -> None:
        self._enqueue_refresh = enqueue_refresh

    def execute(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        months = self._months_from_lifecycle_scope_keys(scope_keys)
        target_scope_keys = months if months else ["all"]
        enqueued = self._enqueue_refresh(
            target_scope_keys,
            reason=str(domain_plan.get("reason") or "derived_lifecycle_bank_flow_rule_batch"),
            metadata=self._read_model_refresh_metadata(domain_plan),
        )
        return {
            "deleted_counts": {"bank_flow_rule_batch_read_models": 0},
            "invalidated_scopes": target_scope_keys,
            "enqueued_jobs": ["bank_flow_rule_batch.read_model.refresh"] if enqueued else [],
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]

    @staticmethod
    def _months_from_lifecycle_scope_keys(scope_keys: list[str]) -> list[str]:
        return sorted(
            {
                part
                for scope_key in list(scope_keys or [])
                for part in str(scope_key).split(":")
                if SEARCH_MONTH_RE.match(str(part).strip())
            }
        )

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
