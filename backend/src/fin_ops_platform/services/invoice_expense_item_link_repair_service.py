from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from typing import Any

from fin_ops_platform.services.invoice_expense_item_links import (
    explicit_expense_item_links,
    replace_explicit_expense_item_links,
    source_links,
)


def build_invoice_expense_item_link_repair_plan(
    snapshot: list[dict[str, Any]],
    *,
    invoice_ids: list[str],
    case_id: str,
    oa_row_id: str,
    expense_item_id: str,
    expected_total: str,
) -> dict[str, Any]:
    normalized_ids = sorted({_text(value) for value in invoice_ids if _text(value)})
    if not normalized_ids or len(normalized_ids) != len(invoice_ids):
        raise ValueError("Invoice provenance repair requires unique, non-empty invoice ids.")
    if not all((_text(case_id), _text(oa_row_id), _text(expense_item_id))):
        raise ValueError("Invoice provenance repair requires case, OA row, and expense item ids.")

    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        invoice_id = _text(row.get("invoice_id"))
        if invoice_id not in normalized_ids or invoice_id in rows_by_id:
            raise ValueError("Invoice provenance repair targets must resolve exactly once.")
        rows_by_id[invoice_id] = dict(row)
    if set(rows_by_id) != set(normalized_ids):
        raise ValueError("Invoice provenance repair did not resolve every requested invoice.")

    actual_total = sum(
        (_money(rows_by_id[invoice_id].get("total_with_tax")) for invoice_id in normalized_ids),
        Decimal("0"),
    )
    authorized_total = _money(expected_total)
    if actual_total != authorized_total:
        raise ValueError("Invoice provenance repair total does not match the authorized total.")

    source_snapshot = []
    updates = []
    for invoice_id in normalized_ids:
        row = rows_by_id[invoice_id]
        current_source_links = source_links(row.get("source_links"))
        source_snapshot.append(
            {
                "invoice_id": invoice_id,
                "digital_invoice_no": _text(row.get("digital_invoice_no")),
                "total_with_tax": format(_money(row.get("total_with_tax")), "f"),
                "source_links": current_source_links,
            }
        )
        expense_links = explicit_expense_item_links(current_source_links)
        if any(
            _text(link.get("source_expense_item_id")) != _text(expense_item_id)
            or _text(link.get("derived_from_oa_id")) != _text(oa_row_id)
            for link in expense_links
        ):
            raise ValueError("Invoice provenance repair found a conflicting OA expense-item link.")
        if expense_links:
            continue
        updates.append(
            {
                "invoice_id": invoice_id,
                "before_source_links": current_source_links,
                "source_links": replace_explicit_expense_item_links(
                    current_source_links,
                    case_id=case_id,
                    targets=[(oa_row_id, expense_item_id)],
                    entry_method="historical_repair",
                ),
            }
        )

    source_fingerprint = _fingerprint(
        {
            "case_id": _text(case_id),
            "oa_row_id": _text(oa_row_id),
            "expense_item_id": _text(expense_item_id),
            "expected_total": format(authorized_total, "f"),
            "snapshot": source_snapshot,
        }
    )
    return {
        "source_fingerprint": source_fingerprint,
        "case_id": _text(case_id),
        "oa_row_id": _text(oa_row_id),
        "expense_item_id": _text(expense_item_id),
        "target_count": len(normalized_ids),
        "target_total": format(actual_total, "f"),
        "update_count": len(updates),
        "updates": updates,
        "rollback_manifest": {
            "restore_invoice_source_links": [
                {
                    "invoice_id": item["invoice_id"],
                    "source_links": item["source_links"],
                }
                for item in source_snapshot
            ]
        },
    }


def public_invoice_expense_item_link_repair_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "operation": "invoice_expense_item_link_repair",
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "case_id": plan["case_id"],
        "oa_row_id": plan["oa_row_id"],
        "expense_item_id": plan["expense_item_id"],
        "target_count": plan["target_count"],
        "target_total": plan["target_total"],
        "update_count": plan["update_count"],
        "completion": completion,
        "rollback_manifest": plan["rollback_manifest"],
        "authorized_write_scope": ["app.invoices", "ops.operation_events"],
    }


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
