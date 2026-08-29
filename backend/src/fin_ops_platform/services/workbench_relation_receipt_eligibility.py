from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.workbench_invoice_direction import normalize_invoice_kind_from_row


_CNY_ALIASES = frozenset({"CNY", "RMB", "人民币", "人民币元", "元"})


def normalize_receipt_currency(value: Any) -> str:
    normalized = "".join(str(value or "").upper().split())
    return "CNY" if normalized in _CNY_ALIASES else normalized


def _detail_value(row: dict[str, Any], key: str) -> Any:
    detail_fields = row.get("detail_fields")
    if not isinstance(detail_fields, dict):
        return None
    return detail_fields.get(key)


def workbench_relation_receipt_action(
    rows_by_type: dict[str, list[dict[str, Any]]],
    *,
    case_id: str,
    zone: str,
) -> dict[str, Any] | None:
    """Return the single receipt action exposed by an eligible active relation."""

    oa_rows = rows_by_type.get("oa", [])
    bank_rows = rows_by_type.get("bank", [])
    invoice_rows = rows_by_type.get("invoice", [])
    if zone != "paired" or oa_rows or not bank_rows or not invoice_rows:
        return None
    if any(str(_detail_value(row, "txn_direction") or "").strip().lower() != "inflow" for row in bank_rows):
        return None
    try:
        if any(Decimal(str(_detail_value(row, "amount"))) <= Decimal("0") for row in bank_rows):
            return None
    except (InvalidOperation, TypeError, ValueError):
        return None
    if any(normalize_invoice_kind_from_row(row) != "output" for row in invoice_rows):
        return None
    if any(
        not str(
            row.get("digital_invoice_no")
            or row.get("digitalInvoiceNo")
            or row.get("invoice_no")
            or row.get("invoiceNo")
            or ""
        ).strip()
        for row in invoice_rows
    ):
        return None
    currencies = {
        normalize_receipt_currency(_detail_value(row, "currency"))
        for row in [*bank_rows, *invoice_rows]
    }
    if currencies != {"CNY"}:
        return None
    if any(
        not str(
            row.get("counterparty_name_raw")
            or row.get("normalized_counterparty_name")
            or row.get("counterparty_name")
            or ""
        ).strip()
        for row in bank_rows
    ):
        return None
    return {
        "eligible": True,
        "case_id": case_id,
        "label": "待补收据",
        "action_label": "打印收据",
    }
