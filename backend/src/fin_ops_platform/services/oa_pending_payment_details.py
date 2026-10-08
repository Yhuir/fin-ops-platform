from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.bank_transaction_unit import original_bank_transaction
from fin_ops_platform.services.source_record_details import (
    bank_source_detail,
    invoice_source_detail,
    oa_source_detail,
    source_detail_sections,
    source_invoice_groups,
    source_relation_sections,
)


def oa_pending_payment_source_detail(facts: dict[str, Any], kind: str, identifier: str) -> dict[str, Any]:
    if kind == "oa":
        records = [*facts.get("completed_records", []), *facts.get("in_progress_records", [])]
    else:
        records = facts["bank_transactions" if kind == "bank" else "invoices"]
    record = next((item for item in records if item.id == identifier), None)
    if record is None:
        raise ValueError("Source detail identity is absent from the authorized canonical snapshot")
    if kind == "oa":
        payload = oa_source_detail(record)
    elif kind == "bank":
        payload = bank_source_detail(original_bank_transaction(record), labels=facts["bank_labels"][original_bank_transaction(record).id])
    else:
        payload = invoice_source_detail(next(group for group in source_invoice_groups(records) if any(line.id == identifier for line in group["line_items"])))
    sections = source_detail_sections(kind, payload)
    return {"id": record.id, "title": {"oa": "OA详情", "bank": "银行流水详情", "invoice": "发票详情"}[kind],
            "detailAvailable": True, "sections": sections}


def oa_pending_payment_relation_details_from_row(row: dict[str, Any], *, kind: str, facts: dict[str, Any]) -> dict[str, Any]:
    normalized_kind = _text(kind)
    if normalized_kind not in {"oa", "bank", "invoice"}:
        raise ValueError("kind must be oa, bank or invoice.")
    relation_payload = {
        "oa": _mapping(row.get("oa")),
        "bank": _mapping(row.get("bankTransaction")),
        "invoice": _mapping(row.get("invoice")),
    }[normalized_kind]
    title = {
        "oa": "OA关联明细",
        "bank": "支出流水关联明细",
        "invoice": "发票关联明细",
    }[normalized_kind]
    summaries = [summary for summary in list(relation_payload.get("summaries") or []) if isinstance(summary, dict)]
    oa = _mapping(row.get("oa"))
    return {
        "rowId": row.get("id"),
        "oaId": oa.get("id"),
        "kind": normalized_kind,
        "title": title,
        "subtitle": _text(oa.get("applicantName")) or _text(oa.get("projectName")) or _text(oa.get("id")),
        "detailAvailable": relation_payload.get("detailMode") != "none",
        "relationCount": relation_payload.get("relationCount", 0),
        "hasMultiple": relation_payload.get("hasMultiple", False),
        "summaries": deepcopy(summaries),
        "sections": source_relation_sections(normalized_kind, summaries,
            groups=source_invoice_groups(facts["invoices"]), transactions=facts["bank_transactions"],
            oa_records=[*facts.get("completed_records", []), *facts.get("in_progress_records", [])], bank_labels=facts.get("bank_labels")),
        "relations": _relation_summaries_from_row(row),
    }


def _relation_summaries_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    relations: dict[str, dict[str, Any]] = {}
    for section_key in ("oa", "bankTransaction", "invoice"):
        section = _mapping(row.get(section_key))
        for summary in list(section.get("summaries") or []):
            if not isinstance(summary, dict):
                continue
            case_id = _text(summary.get("relationCaseId"))
            if case_id:
                relations[case_id] = {"caseId": case_id}
    return list(relations.values())


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
