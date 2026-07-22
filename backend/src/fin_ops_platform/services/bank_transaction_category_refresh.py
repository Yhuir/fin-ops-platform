from __future__ import annotations

from typing import Any

from fin_ops_platform.services.pending_invoice_scope_planner import (
    pending_invoice_read_model_scope_keys_for_import_state,
)
from fin_ops_platform.services.read_model_scope_policy import (
    DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
)


CATEGORY_REFRESH_SCOPE_TYPES = (
    "bank_detail",
    "bank_flow_rule_batch",
    "workbench",
    "workbench_relation",
    "invoice_lifecycle",
    "cost_statistics",
    "search",
    "turnover_ledger",
)


def bank_transaction_category_refreshes(
    months: list[str],
    *,
    reason: str = "bank_transaction_category_changed",
    metadata: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    normalized_months = sorted(
        {
            str(month).strip()
            for month in list(months or [])
            if len(str(month).strip()) == 7 and str(month).strip()[4] == "-"
        }
    )
    if not normalized_months:
        raise ValueError("bank transaction category refresh requires an affected month.")

    targets: list[dict[str, object]] = []
    for scope_type in CATEGORY_REFRESH_SCOPE_TYPES:
        scope_keys = DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(
            scope_type,
            normalized_months,
        )
        targets.extend(
            _target(scope_type, scope_key, reason=reason, metadata=metadata)
            for scope_key in scope_keys
        )
    pending_scope_keys = pending_invoice_read_model_scope_keys_for_import_state(normalized_months)
    targets.extend(
        _target("pending_invoice", scope_key, reason=reason, metadata=metadata)
        for scope_key in DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(
            "pending_invoice",
            pending_scope_keys,
        )
    )
    return targets


def turnover_category_refresh_requests(months: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for target in bank_transaction_category_refreshes(months):
        grouped.setdefault(str(target["scope_type"]), []).append(str(target["scope_key"]))
    return [
        {
            "scope_type": scope_type,
            "scope_keys": scope_keys,
            "reason": "bank_transaction_category_changed",
        }
        for scope_type, scope_keys in grouped.items()
    ]


def _target(
    scope_type: str,
    scope_key: str,
    *,
    reason: str,
    metadata: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "reason": reason,
        **({"metadata": dict(metadata)} if metadata else {}),
    }
