from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.invoice_expense_item_links import source_links
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    canonical_oa_expense_item_ids,
    invoice_ownership_parent_oa_id,
    oa_row_source_ids,
)


def invoice_needs_expense_assignment(links: Any) -> bool:
    """Manual ownership is authoritative, including conflicts requiring a human."""
    return not any(
        link.get("source_type") == "oa_expense_item_invoice"
        or (link.get("source_type") == "oa_attachment_invoice" and link.get("source_expense_item_id"))
        for link in source_links(links)
    )


def plan_invoice_expense_assignments(
    oa_rows: list[dict[str, Any]], invoice_rows: list[dict[str, Any]],
) -> dict[str, list[tuple[str, str]]]:
    """Infer only unique whole-item ownership inside one established relation.

    Supporting documents are deliberately irrelevant. No subset-sum search,
    allocations, fuzzy names, ordering tie-breaks, or cross-relation inference.
    """
    items: dict[tuple[str, str], tuple[str, Decimal]] = {}
    owner_aliases: dict[str, set[str]] = {}
    covered: set[tuple[str, str]] = set()
    aliases_to_owners: dict[str, set[str]] = defaultdict(set)
    oa_by_id = {str(oa["id"]): oa for oa in oa_rows}
    for oa in oa_rows:
        owner = str(oa["id"])
        owner_aliases[owner] = {owner, *oa_row_source_ids(oa)}
        for alias in owner_aliases[owner]:
            aliases_to_owners[alias].add(owner)
        currency = str(oa.get("currency") or "CNY")
        for item in oa.get("expense_items") or []:
            amount = _positive_money(item.get("amount"))
            if item.get("id") and amount is not None:
                items[(owner, str(item["id"]))] = (currency, amount)
    for invoice in invoice_rows:
        links = source_links(invoice.get("source_links"))
        explicit = [link for link in links if link.get("source_type") == "oa_expense_item_invoice"]
        ownership = explicit or [link for link in links if link.get("source_type") == "oa_attachment_invoice"]
        for link in ownership:
            item_id = str(link.get("source_expense_item_id") or "")
            for owner in aliases_to_owners.get(invoice_ownership_parent_oa_id(link), ()):
                if (owner, item_id) in items:
                    covered.add((owner, item_id))
                else:
                    # Historical item aliases retain the canonical linking contract.
                    covered.update((owner, key) for key in canonical_oa_expense_item_ids(
                        oa_row=oa_by_id[owner], invoice_row={"source_links": [link]},
                    ))
    remaining_items = {key: value for key, value in items.items() if key not in covered}
    invoices: dict[str, tuple[str, Decimal]] = {}
    parents: dict[str, set[str]] = {}
    for row in invoice_rows:
        links = source_links(row.get("source_links"))
        if not invoice_needs_expense_assignment(links):
            continue
        if row.get("invoice_type") != "input" or row.get("source_kind") == "etc_invoice_summary":
            continue
        amount = _positive_money(row.get("total_with_tax"))
        if amount is None or row.get("etc_invoice_id") or row.get("etc_submission_batch_id"):
            continue
        invoice_id = str(row["id"])
        invoices[invoice_id] = (str(row.get("currency") or "CNY"), amount)
        parents[invoice_id] = {parent for link in links if (parent := invoice_ownership_parent_oa_id(link))}

    def allowed(invoice_id: str, target: tuple[str, str]) -> bool:
        return not parents[invoice_id] or parents[invoice_id].issubset(owner_aliases[target[0]])

    item_buckets: dict[tuple[str, Decimal], list[tuple[str, str]]] = defaultdict(list)
    for target, money in remaining_items.items():
        item_buckets[money].append(target)
    invoice_buckets: dict[tuple[tuple[str, Decimal], tuple[str, ...]], list[str]] = defaultdict(list)
    for invoice_id, money in invoices.items():
        invoice_buckets[(money, tuple(sorted(parents[invoice_id])))].append(invoice_id)
    options: dict[tuple[tuple[str, Decimal], tuple[str, ...]], list[tuple[str, str]]] = {}
    claimant_counts: dict[tuple[str, str], int] = defaultdict(int)
    for signature, ids in invoice_buckets.items():
        targets = [target for target in item_buckets[signature[0]] if allowed(ids[0], target)]
        options[signature] = targets
        for target in targets:
            claimant_counts[target] += len(ids)
    result = {
        ids[0]: options[signature] for signature, ids in invoice_buckets.items()
        if len(ids) == 1 and len(options[signature]) == 1 and claimant_counts[options[signature][0]] == 1
    }
    assigned = {target for targets in result.values() for target in targets}
    leftovers = [target for target in remaining_items if target not in assigned]
    remaining_invoices = [invoice_id for invoice_id in invoices if invoice_id not in result]
    if len(leftovers) == 1 and remaining_invoices:
        target = leftovers[0]
        currency, total = remaining_items[target]
        if all(invoices[key][0] == currency and allowed(key, target) for key in remaining_invoices):
            if sum((invoices[key][1] for key in remaining_invoices), Decimal(0)) == total:
                result.update({key: [target] for key in remaining_invoices})
    return dict(sorted(result.items()))


def _positive_money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount > 0 and amount == amount.quantize(Decimal(".01")) else None
    except (InvalidOperation, ValueError):
        return None
