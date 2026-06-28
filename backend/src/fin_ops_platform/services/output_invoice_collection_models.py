from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fin_ops_platform.services.scope_keys import normalized_scope_keys


OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION = "output-invoice-collections:v3"

MANUAL_COLLECTION_STATUS_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "code": "pending_collection",
        "label": "待收款",
        "severity": "warning",
        "matchedRuleId": "manual_pending_collection",
    },
    {
        "code": "pending_red_invoice",
        "label": "待冲红",
        "severity": "warning",
        "matchedRuleId": "manual_pending_red_invoice",
    },
    {
        "code": "collected",
        "label": "已收款",
        "severity": "success",
        "matchedRuleId": "manual_collected",
    },
)

MANUAL_COLLECTION_STATUS_BY_CODE = {str(item["code"]): dict(item) for item in MANUAL_COLLECTION_STATUS_OPTIONS}
RED_REFUND_STATUS_CODES = {"collected_red_refunded", "red_invoiced_no_collection"}
RECEIPT_STATUS_VALUES = {"issued", "pending", "not_available", "blocked", "voided", "reissued"}


@dataclass(frozen=True)
class OutputInvoiceCollectionRowRef:
    row_id: str
    invoice_id: str
    invoice_identity_key: str
    invoice_date: str | None
    invoice_no: str | None
    buyer_name: str | None
    taxable_item_name: str | None
    total_with_tax: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "OutputInvoiceCollectionRowRef":
        invoice = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
        return cls(
            row_id=str(row.get("id") or "").strip(),
            invoice_id=str(row.get("invoiceId") or "").strip(),
            invoice_identity_key=str(row.get("invoiceIdentityKey") or "").strip(),
            invoice_date=str(invoice.get("invoiceDate") or invoice.get("issueDate") or "").strip() or None,
            invoice_no=str(invoice.get("displayNo") or invoice.get("invoiceNo") or "").strip() or None,
            buyer_name=str(invoice.get("buyerName") or "").strip() or None,
            taxable_item_name=str(invoice.get("taxableItemName") or "").strip() or None,
            total_with_tax=str(invoice.get("totalWithTax") or "0.00"),
        )


def output_invoice_collection_scope_key(row: dict[str, Any]) -> str:
    invoice = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
    invoice_date = str(invoice.get("invoiceDate") or invoice.get("issueDate") or "").strip()
    if len(invoice_date) >= 7 and invoice_date[4] == "-":
        return invoice_date[:7]
    return "all"


def output_invoice_collection_freshness_metadata(row: dict[str, Any]) -> dict[str, object]:
    scope_key = output_invoice_collection_scope_key(row)
    return {"affected_scope_keys": normalized_scope_keys([scope_key], fallback="all")}
