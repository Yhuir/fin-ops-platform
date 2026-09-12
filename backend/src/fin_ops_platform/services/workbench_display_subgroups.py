"""Read-only OA/bank display partitions; never creates relation ownership."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_service import WITHDRAW_RESTORABLE_CONFIRM_OPERATION_TYPES
from fin_ops_platform.services.workbench_relation_alignment_service import WorkbenchRelationAlignmentService


def members(relation: dict[str, Any]) -> frozenset[tuple[str, str]]:
    ids, types = relation.get("row_ids", []), relation.get("row_types", [])
    if len(ids) != len(types):
        raise ValueError("Display history requires exact typed members.")
    return frozenset(zip(types, ids, strict=True))


def apply_display_subgroups(groups: list[dict[str, Any]], history: list[dict[str, Any]]) -> None:
    # Histories are ordered oldest to newest by the repository. Index exact
    # snapshots, not just case IDs: a reused case cannot supply stale evidence.
    index: dict[tuple[str, frozenset[tuple[str, str]]], list[tuple[int, dict[str, Any]]]] = {}
    for position, event in enumerate(history):
        if event.get("operation_type") not in WITHDRAW_RESTORABLE_CONFIRM_OPERATION_TYPES:
            continue
        for after in event.get("after_relations", []):
            index.setdefault((after["case_id"], members(after)), []).append((position, event))

    def partition(relation: dict[str, Any], ceiling: int) -> list[frozenset[tuple[str, str]]]:
        current = members(relation)
        events = index.get((relation.get("case_id", ""), current), [])
        event_pair = next((item for item in reversed(events) if item[0] < ceiling), None)
        if event_pair is None:
            return [current]
        position, event = event_pair
        children = [r for r in event.get("before_relations", []) if members(r) and members(r) <= current]
        usage = Counter(member for r in children for member in members(r))
        if any(count > 1 for count in usage.values()):
            return [current]
        result = [part for child in children for part in partition(child, position)]
        remainder = current - set(usage)
        if remainder:
            result.append(frozenset(remainder))
        return result or [current]

    service = WorkbenchRelationAlignmentService()
    for group in groups:
        oa_rows, bank_rows = group.get("oa_rows", []), group.get("bank_rows", [])
        if len(oa_rows) < 2 or not bank_rows or any(row.get("expense_items") for row in oa_rows):
            continue
        current = {
            "case_id": group.get("case_id"),
            "row_ids": group["formal_member_ids"],
            "row_types": group["formal_member_types"],
        }
        oa_by_id = {r["id"]: r for r in oa_rows}
        bank_by_id = {r["id"]: r for r in bank_rows}
        available = {("oa", k) for k in oa_by_id} | {("bank", k) for k in bank_by_id}
        parts = partition(current, len(history))
        resolved: list[frozenset[tuple[str, str]]] = []
        for part in parts:
            part = part & available
            if any(t == "oa" for t, _ in part) and any(t == "bank" for t, _ in part) and part != available:
                resolved.append(part)
        used = set().union(*resolved) if resolved else set()
        remaining = available - used
        # Only singleton-sided remainder closes by total; a generic many-to-many
        # remainder remains a shared block rather than invented row ownership.
        remaining_oa = [oa_by_id[k] for t, k in remaining if t == "oa"]
        remaining_bank = [bank_by_id[k] for t, k in remaining if t == "bank"]
        if remaining_oa and remaining_bank:
            rows = {
                f"{r['type']}:{r['id']}": {**r, "id": f"{r['type']}:{r['id']}"}
                for r in [*remaining_oa, *remaining_bank]
            }
            alignment = service.align_relation(rows_by_id=rows, relation={"row_ids": list(rows)})
            for link in alignment["links"]:
                if link["bank_row_ids"]:
                    part = frozenset([("oa", link["oa_row_id"][3:]), *[("bank", k[5:]) for k in link["bank_row_ids"]]])
                    resolved.append(part)
                    remaining -= part
            ro = [oa_by_id[k] for t, k in remaining if t == "oa"]
            rb = [bank_by_id[k] for t, k in remaining if t == "bank"]
            oa_amounts = [service._money(r.get("amount")) for r in ro]
            bank_amounts = [service._bank_amount(r) for r in rb]
            directions = {r.get("txn_direction") for r in rb}
            if (
                ro
                and rb
                and (len(ro) == 1 or len(rb) == 1)
                and all(a is not None and a > 0 for a in [*oa_amounts, *bank_amounts])
                and len(directions) == 1
                and sum(oa_amounts) == sum(bank_amounts)
            ):
                resolved.append(frozenset(remaining))
                remaining = set()
        if remaining:
            resolved.append(frozenset(remaining))
        oa_order = {r["id"]: i for i, r in enumerate(oa_rows)}
        resolved.sort(key=lambda part: min((oa_order[k] for t, k in part if t == "oa"), default=len(oa_rows)))
        group["display_subgroups"] = [
            {
                "resolved": part != remaining,
                "oa_row_ids": [r["id"] for r in oa_rows if ("oa", r["id"]) in part],
                "bank_row_ids": [r["id"] for r in bank_rows if ("bank", r["id"]) in part],
            }
            for part in resolved
            if part
        ]
