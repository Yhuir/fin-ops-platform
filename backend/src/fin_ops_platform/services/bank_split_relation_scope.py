"""Resolve a unique purpose total inside an existing relation, without changing ownership."""
from decimal import Decimal
from typing import Any


def bank_split_comparison_rows(
    rows: list[dict[str, Any]], *, target: Decimal | None,
) -> list[dict[str, Any]]:
    """Split principal and other purposes may support different documents.

    Only a complete, unique purpose bucket matching the document total is selected.
    Mixed directions, missing values and ambiguous totals retain the entire evidence
    set so ordinary reconciliation exposes the unresolved difference.
    """
    if target is None or target <= 0 or not rows or not all(row.get("is_split") for row in rows):
        return rows
    principal = [row for row in rows if row.get("turnover_role") == "external_turnover"]
    other = [row for row in rows if row.get("turnover_role") != "external_turnover"]
    if not principal or not other:
        return rows
    directions = {row.get("txn_direction") for row in rows}
    if len(directions) != 1 or not directions <= {"outflow", "inflow"}:
        return rows
    if any(row.get("amount") in (None, "") for row in rows):
        return rows
    sums = [sum((Decimal(str(row["amount"])) for row in bucket), Decimal(0)) for bucket in (principal, other)]
    matches = [bucket for bucket, total in zip((principal, other), sums, strict=True) if total == target]
    return matches[0] if len(matches) == 1 else rows
