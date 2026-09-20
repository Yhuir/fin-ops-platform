"""Read-only relation history partitions and OA/bank display alignment; never writes ownership."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_row_source_alias_map
from fin_ops_platform.services.workbench_pair_relation_service import WITHDRAW_RESTORABLE_CONFIRM_OPERATION_TYPES
from fin_ops_platform.services.workbench_relation_alignment_service import (
    WorkbenchRelationAlignmentService,
    evidenced_payment_pairs,
    payment_conflicts,
    row_payment_evidence,
)


def members(relation: dict[str, Any]) -> frozenset[tuple[str, str]]:
    ids, types = relation.get("row_ids", []), relation.get("row_types", [])
    if len(ids) != len(types):
        raise ValueError("Display history requires exact typed members.")
    return frozenset(zip(types, ids, strict=True))


def relation_history_partitions(
    relations: list[dict[str, Any]], history: list[dict[str, Any]],
) -> list[list[frozenset[tuple[str, str]]]]:
    """Partition exact active snapshots by their merge history, without amount inference."""
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

    return [partition(relation, len(history)) for relation in relations]


def apply_display_subgroups(groups: list[dict[str, Any]], history: list[dict[str, Any]]) -> None:
    service = WorkbenchRelationAlignmentService()
    eligible = [group for group in groups
                if len(group.get("oa_rows", [])) >= 2 and group.get("bank_rows")
                and not any(row.get("expense_items") for row in group["oa_rows"])]
    partitions = relation_history_partitions([
        {"case_id": group.get("case_id"), "row_ids": group["formal_member_ids"],
         "row_types": group["formal_member_types"]} for group in eligible
    ], history)
    for group, parts in zip(eligible, partitions, strict=True):
        oa_rows, bank_rows = group["oa_rows"], group["bank_rows"]
        oa_by_id = {r["id"]: r for r in oa_rows}
        bank_by_id = {r["id"]: r for r in bank_rows}
        available = {("oa", k) for k in oa_by_id} | {("bank", k) for k in bank_by_id}
        oa_evidence = {k: row_payment_evidence(r) for k, r in oa_by_id.items()}
        bank_evidence = {k: row_payment_evidence(r) for k, r in bank_by_id.items()}
        proven_pairs = evidenced_payment_pairs(list(oa_evidence.values()), list(bank_evidence.values())).pairs
        aliases = oa_row_source_alias_map(oa_rows)
        explicit_pairs = {
            bid: source for bid, row in bank_by_id.items()
            if (source := service.bank_source_oa_id(row, aliases))
        }
        resolved: list[frozenset[tuple[str, str]]] = []
        for part in parts:
            part = part & available
            po = [oa_evidence[k] for t, k in part if t == "oa"]
            pb = [bank_evidence[k] for t, k in part if t == "bank"]
            crossing_pair = any((("oa", oid) in part) != (("bank", bid) in part) for oid, bid in proven_pairs.items())
            crossing_pair = crossing_pair or any((("oa", oid) in part) != (("bank", bid) in part) for bid, oid in explicit_pairs.items())
            if (
                po and pb and part != available and not crossing_pair
                and all(item.amount > 0 for item in [*po, *pb])
                and sum(item.amount for item in po) == sum(item.amount for item in pb)
                and all(any(not payment_conflicts(o, b) for o in po) for b in pb)
                and all(any(not payment_conflicts(o, b) for b in pb) for o in po)
            ):
                resolved.append(part)
        used = set().union(*resolved) if resolved else set()
        remaining = available - used
        # Only singleton-sided remainder closes by total; a generic many-to-many
        # remainder remains a shared block rather than invented row ownership.
        remaining_oa = [oa_by_id[k] for t, k in remaining if t == "oa"]
        remaining_bank = [bank_by_id[k] for t, k in remaining if t == "bank"]
        if remaining_oa and remaining_bank:
            rows = {
                f"{r['type']}:{r['id']}": {**r, "id": f"{r['type']}:{r['id']}",
                    "source_aliases": [*r.get("source_aliases", []), r["id"]]}
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
                and all(any(not payment_conflicts(oa_evidence[o["id"]], bank_evidence[b["id"]]) for o in ro) for b in rb)
                and all(any(not payment_conflicts(oa_evidence[o["id"]], bank_evidence[b["id"]]) for b in rb) for o in ro)
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
