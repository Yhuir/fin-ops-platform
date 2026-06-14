from __future__ import annotations


OA_ATTACHMENT_INVOICE_PREFIX = "oa-att-inv-"


def row_type_for_workbench_row_id(row_id: object, *, unknown: str = "unknown") -> str:
    normalized = str(row_id or "").strip().lower()
    if not normalized:
        return unknown
    if normalized.startswith(OA_ATTACHMENT_INVOICE_PREFIX):
        return "invoice"
    if normalized.startswith(("oa-", "oa_")):
        return "oa"
    if normalized.startswith(("bk-", "bk_", "txn-", "txn_", "bank-", "bank_")):
        return "bank"
    if normalized.startswith(("iv-", "iv_", "inv-", "inv_", "invoice-", "invoice_", "etc-summary-")):
        return "invoice"
    return unknown


def looks_like_invoice_workbench_row_id(row_id: object) -> bool:
    return row_type_for_workbench_row_id(row_id, unknown="") == "invoice"


def looks_like_bank_workbench_row_id(row_id: object) -> bool:
    return row_type_for_workbench_row_id(row_id, unknown="") == "bank"


def looks_like_oa_workbench_row_id(row_id: object) -> bool:
    return row_type_for_workbench_row_id(row_id, unknown="") == "oa"
