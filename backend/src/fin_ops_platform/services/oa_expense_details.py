"""Public OA expense details. Pure projection; no I/O or attachment payloads."""
from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_draft_prefill import OA_INVOICE_KIND_OPTIONS, OA_PAYMENT_METHOD_OPTIONS

OA_EXPENSE_FIELDS = (
    ("project_name", "项目名称"),
    ("amount", "报销金额"),
    ("expense_type", "费用类型"),
    ("expense_content", "费用内容"),
    ("fee_description", "费用说明"),
    ("reimbursement_date", "报销日期"),
    ("payment_method", "支付方式"),
    ("invoice_kind", "发票种类"),
    ("ticket_count", "票据张数"),
    ("attachment_file_count", "附件文件数"),
)


def oa_expense_detail_sections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": f"费用明细 {index}",
            "fields": [
                {"label": label, "value": str(item[key]) if item.get(key) not in (None, "") else "—"}
                for key, label in OA_EXPENSE_FIELDS
            ],
        }
        for index, item in enumerate(items, start=1)
    ]


def public_oa_expense_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: item[key] for key, _ in OA_EXPENSE_FIELDS if key in item}
        for item in items
    ]


def oa_expense_source_metadata(item: dict[str, Any]) -> dict[str, str]:
    """Exact fields from the OA reimbursement schedule, preserving unknown codes."""
    payment = str(item.get("detailPaymentMethod") or "").strip()
    invoice = str(item.get("detailTypeOfInvoice") or "").strip()
    count = item.get("detailNumberOfBills")
    return {
        "payment_method": dict(OA_PAYMENT_METHOD_OPTIONS).get(payment, payment),
        "invoice_kind": dict(OA_INVOICE_KIND_OPTIONS).get(invoice, invoice),
        "ticket_count": "" if count is None else str(count).strip(),
    }
