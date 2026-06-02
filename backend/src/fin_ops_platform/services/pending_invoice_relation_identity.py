from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PendingInvoiceRelationIdentity:
    oa_row_ids: list[str]
    bank_transaction_ids: list[str]
    invoice_ids: list[str]
    relation_case_ids: list[str]
    invalid_oa_row_ids: list[str]


def pending_invoice_relation_identity(relations: list[dict[str, Any]]) -> PendingInvoiceRelationIdentity:
    oa_row_ids: list[str] = []
    bank_transaction_ids: list[str] = []
    invoice_ids: list[str] = []
    relation_case_ids: list[str] = []
    invalid_oa_row_ids: list[str] = []
    seen: dict[str, set[str]] = {
        "oa": set(),
        "bank": set(),
        "invoice": set(),
        "case": set(),
        "invalid_oa": set(),
    }

    for relation in list(relations or []):
        if not isinstance(relation, dict):
            continue
        case_id = _clean_text(relation.get("case_id"))
        if case_id and case_id not in seen["case"]:
            seen["case"].add(case_id)
            relation_case_ids.append(case_id)
        row_ids = [_clean_text(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [_clean_text(row_type) for row_type in list(relation.get("row_types") or [])]
        for index, row_id in enumerate(row_ids):
            if not row_id:
                continue
            row_type = row_types[index] if index < len(row_types) and row_types[index] else infer_pending_invoice_relation_row_type(row_id)
            if row_type == "oa":
                if is_valid_pending_invoice_oa_row_id(row_id):
                    _append_unique(oa_row_ids, row_id, seen["oa"])
                else:
                    _append_unique(invalid_oa_row_ids, row_id, seen["invalid_oa"])
            elif row_type == "bank":
                _append_unique(bank_transaction_ids, row_id, seen["bank"])
            elif row_type == "invoice":
                _append_unique(invoice_ids, row_id, seen["invoice"])

    return PendingInvoiceRelationIdentity(
        oa_row_ids=oa_row_ids,
        bank_transaction_ids=bank_transaction_ids,
        invoice_ids=invoice_ids,
        relation_case_ids=relation_case_ids,
        invalid_oa_row_ids=invalid_oa_row_ids,
    )


def infer_pending_invoice_relation_row_type(row_id: str) -> str:
    normalized = _clean_text(row_id).lower()
    if is_reserved_relation_identifier(normalized):
        return "unknown"
    if normalized.startswith("oa-att-inv-"):
        return "invoice"
    if normalized.startswith("oa-"):
        return "oa"
    if normalized.startswith(("bk-", "txn-", "txn_", "bank-")):
        return "bank"
    if normalized.startswith(("iv-", "inv-", "invoice-")):
        return "invoice"
    if normalized.startswith("etc-summary-"):
        return "invoice"
    return "unknown"


def is_valid_pending_invoice_oa_row_id(value: object) -> bool:
    text = _clean_text(value)
    if not text or is_reserved_relation_identifier(text):
        return False
    return text.lower().startswith("oa-")


def is_reserved_relation_identifier(value: object) -> bool:
    text = _clean_text(value).lower()
    return text.startswith(("candidate:", "case:", "case-", "exception:"))


def sanitize_pending_invoice_oa_summaries(summaries: object) -> tuple[list[dict[str, Any]], list[str]]:
    valid: list[dict[str, Any]] = []
    invalid_ids: list[str] = []
    seen_valid: set[str] = set()
    seen_invalid: set[str] = set()
    for item in list(summaries or []) if isinstance(summaries, list) else []:
        if not isinstance(item, dict):
            continue
        oa_id = _clean_text(item.get("id"))
        if not is_valid_pending_invoice_oa_row_id(oa_id):
            if oa_id:
                _append_unique(invalid_ids, oa_id, seen_invalid)
            continue
        if oa_id in seen_valid:
            continue
        seen_valid.add(oa_id)
        valid.append(dict(item))
    return valid, invalid_ids


def _append_unique(target: list[str], value: str, seen: set[str]) -> None:
    if value in seen:
        return
    seen.add(value)
    target.append(value)


def _clean_text(value: object) -> str:
    return str(value or "").strip()
