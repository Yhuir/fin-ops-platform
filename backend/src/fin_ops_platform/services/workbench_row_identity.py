from __future__ import annotations


OA_ATTACHMENT_INVOICE_PREFIX = "oa-att-inv-"
WORKBENCH_ROW_IDENTITY_SEPARATOR = "\x1f"


def canonical_workbench_row_type(value: object, *, unknown: str = "unknown") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"oa", "oa_application"}:
        return "oa"
    if normalized in {"bank", "bank_transaction"}:
        return "bank"
    if normalized in {
        "invoice",
        "invoice_record",
        "formal",
        "formal_invoice",
        "input",
        "input_invoice",
        "output",
        "output_invoice",
        "etc_summary",
        "etc_invoice_summary",
    }:
        return "invoice"
    return unknown


def workbench_row_identity_key(row_type: object, row_id: object) -> str:
    canonical_type = canonical_workbench_row_type(row_type, unknown="")
    normalized_id = str(row_id or "").strip()
    if not canonical_type or not normalized_id:
        raise ValueError("Workbench row identity requires a canonical row type and row id.")
    if WORKBENCH_ROW_IDENTITY_SEPARATOR in normalized_id:
        raise ValueError("Workbench row id contains the reserved identity separator.")
    return f"{canonical_type}{WORKBENCH_ROW_IDENTITY_SEPARATOR}{normalized_id}"


def parse_workbench_row_identity_key(value: object) -> tuple[str, str] | None:
    raw_key = str(value or "")
    row_type, separator, row_id = raw_key.partition(WORKBENCH_ROW_IDENTITY_SEPARATOR)
    if not separator:
        return None
    canonical_type = canonical_workbench_row_type(row_type, unknown="")
    normalized_id = row_id.strip()
    if not canonical_type or not normalized_id:
        return None
    return canonical_type, normalized_id


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
