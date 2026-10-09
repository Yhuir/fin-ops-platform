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
