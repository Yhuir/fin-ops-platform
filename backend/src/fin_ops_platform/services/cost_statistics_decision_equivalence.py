"""Compare complete cost decisions at write/maintenance boundaries, never on list reads."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from fin_ops_platform.services.cost_statistics_scope import PROJECT_COST_SCOPE_KEY, read_project_cost_scope


def automatic_task(snapshot: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    """Calculate all sources in this relation, including those outside the selected UI scope."""
    group = next((g for g in snapshot["cost_groups"] if g["group_id"] == case_id), None)
    if group is None:
        return None
    scope = read_project_cost_scope(snapshot["settings"])
    codes = {str(row.get("bank_tag_code") or "uncategorized") for row in group["bank_rows"]}
    settings = {**snapshot["settings"], PROJECT_COST_SCOPE_KEY: {
        **scope, "selected_tag_codes": sorted(codes | set(scope["selected_tag_codes"]))}}
    records = {key: record for key, record in snapshot["manual_allocations"].items() if key != case_id}
    policy = CostStatisticsPolicy({**snapshot, "settings": settings, "manual_allocations": records})
    return next((task for task in policy.allocation_tasks if task["relation_case_id"] == case_id), None)


def automatic_equivalence_reason(record: dict[str, Any], task: dict[str, Any] | None) -> str:
    """An empty reason proves the full decision is redundant; explicit human semantics remain."""
    if task is None:
        return "no_current_cost_task"
    if task["status"] != "allocated":
        return "automatic_unresolved"
    if record["source_fingerprint"] != task["source_fingerprint"]:
        return "facts_changed"
    if record["manual_items"] or record["oa_cost_tag_overrides"]:
        return "manual_content"
    if Decimal(record["non_cost_amount"]) != 0 or record["non_cost_reason"]:
        return "non_cost_decision"
    if record["oa_amount_locks"] != {u["unit_id"]: u["lock_oa_amount"] for u in task["units"]}:
        return "amount_lock_decision"
    source = record["source_allocations"]
    if source is None:
        return "missing_sources"
    if source["refund_links"] or source["non_cost_lines"]:
        return "refund_or_non_cost_decision"
    def lines(rows: list[dict[str, Any]]) -> list[tuple[str, str, Decimal]]:
        return sorted((line["unit_id"], line["bank_transaction_id"], Decimal(line["amount"])) for line in rows)
    if lines(source["cost_lines"]) != lines(task["source_allocations"]["cost_lines"]):
        return "different_sources"
    def amounts(rows: list[dict[str, Any]]) -> list[tuple[str, Decimal]]:
        return sorted((line["unit_id"], Decimal(line["amount"])) for line in rows)
    if amounts(record["allocations"]) != amounts(task["allocations"]):
        return "different_amounts"
    return ""
