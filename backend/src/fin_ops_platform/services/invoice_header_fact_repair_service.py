from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService

INVOICE_HEADER_REPAIR_SOURCE_SHA256 = (
    "c1080bb92a64553956ea76a363022cc4034e9673cbfaa1f55528a208411abb00"
)

# Exact facts verified against the authoritative ``发票基础信息`` sheet.
INVOICE_HEADER_REPAIR_FACTS: tuple[dict[str, str], ...] = (
    {
        "digital_invoice_no": "26112000002267204866",
        "amount": "880.54",
        "tax_amount": "114.46",
        "total_with_tax": "995.00",
    },
    {
        "digital_invoice_no": "26117000000807937983",
        "amount": "55.89",
        "tax_amount": "7.26",
        "total_with_tax": "63.15",
    },
    {
        "digital_invoice_no": "26117000000961988740",
        "amount": "35.23",
        "tax_amount": "4.57",
        "total_with_tax": "39.80",
    },
    {
        "digital_invoice_no": "26132000001895606506",
        "amount": "26368.17",
        "tax_amount": "3427.87",
        "total_with_tax": "29796.04",
    },
    {
        "digital_invoice_no": "26332000005466462076",
        "amount": "7366.37",
        "tax_amount": "957.63",
        "total_with_tax": "8324.00",
    },
    {
        "digital_invoice_no": "26332000005535582781",
        "amount": "23.01",
        "tax_amount": "2.99",
        "total_with_tax": "26.00",
    },
    {
        "digital_invoice_no": "26532000000934969021",
        "amount": "4052.22",
        "tax_amount": "526.78",
        "total_with_tax": "4579.00",
    },
    {
        "digital_invoice_no": "26532000001007198071",
        "amount": "134.65",
        "tax_amount": "1.35",
        "total_with_tax": "136.00",
    },
    {
        "digital_invoice_no": "26532000001019712241",
        "amount": "87.13",
        "tax_amount": "0.87",
        "total_with_tax": "88.00",
    },
    {
        "digital_invoice_no": "26532000001022027821",
        "amount": "56.43",
        "tax_amount": "0.57",
        "total_with_tax": "57.00",
    },
    {
        "digital_invoice_no": "26537000000290991842",
        "amount": "242.91",
        "tax_amount": "31.57",
        "total_with_tax": "274.48",
    },
)

_DETAIL_ONLY_FIELDS = (
    "tax_classification_code",
    "specific_business_type",
    "taxable_item_name",
    "specification_model",
    "unit",
    "quantity",
    "unit_price",
    "tax_rate",
)


def build_invoice_header_fact_repair_plan(
    snapshot: list[dict[str, Any]],
    *,
    source_sha256: str,
    expected_target_count: int,
) -> dict[str, Any]:
    if source_sha256 != INVOICE_HEADER_REPAIR_SOURCE_SHA256:
        raise ValueError("Invoice header repair source SHA-256 is not authorized.")
    if expected_target_count != len(INVOICE_HEADER_REPAIR_FACTS):
        raise ValueError("Invoice header repair target count does not match the authorized manifest.")
    expected_numbers = {fact["digital_invoice_no"] for fact in INVOICE_HEADER_REPAIR_FACTS}
    rows_by_number: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        invoice_no = _text(row.get("digital_invoice_no"))
        if invoice_no not in expected_numbers or invoice_no in rows_by_number:
            raise ValueError("Invoice header repair targets must resolve exactly once.")
        rows_by_number[invoice_no] = dict(row)
    if set(rows_by_number) != expected_numbers:
        raise ValueError("Invoice header repair did not resolve every authorized invoice.")

    prior_repair_fingerprints = {
        _text(
            dict(row.get("raw_payload") or {})
            .get("normalized_payload", {})
            .get("invoice_header_repair_fingerprint")
        )
        for row in snapshot
    }
    prior_repair_fingerprints.discard("")
    if len(prior_repair_fingerprints) > 1:
        raise ValueError("Invoice header repair targets have inconsistent repair provenance.")
    source_fingerprint = (
        next(iter(prior_repair_fingerprints))
        if len(prior_repair_fingerprints) == 1
        else _fingerprint({"source_sha256": source_sha256, "snapshot": snapshot})
    )
    updates: list[dict[str, Any]] = []
    restore_rows: list[dict[str, Any]] = []
    for fact in INVOICE_HEADER_REPAIR_FACTS:
        current = rows_by_number[fact["digital_invoice_no"]]
        if _text(current.get("invoice_type")) != InvoiceType.INPUT.value:
            raise ValueError("Invoice header repair only accepts input invoices.")
        if _text(current.get("invoice_month")) != "2026-06":
            raise ValueError("Invoice header repair target month changed.")
        before = {
            "invoice_id": _text(current.get("invoice_id")),
            "digital_invoice_no": fact["digital_invoice_no"],
            "amount": _money(current.get("amount")),
            "signed_amount": _money(current.get("signed_amount")),
            "tax_amount": _money(current.get("tax_amount")),
            "total_with_tax": _money(current.get("total_with_tax")),
            "tax_rate": _text(current.get("tax_rate")),
            "raw_payload": dict(current.get("raw_payload") or {}),
        }
        restore_rows.append(before)
        after = {
            "amount": _money(fact["amount"]),
            "signed_amount": _money(fact["amount"]),
            "tax_amount": _money(fact["tax_amount"]),
            "total_with_tax": _money(fact["total_with_tax"]),
            "tax_rate": "",
        }
        normalized_before = dict(
            before["raw_payload"].get("normalized_payload") or before["raw_payload"]
        )
        already_authoritative = (
            normalized_before.get("source_sheet_name") == "发票基础信息"
            and normalized_before.get("source_sheet_role") == "invoice_header"
            and normalized_before.get("source_workbook_sha256") == source_sha256
            and not any(_text(normalized_before.get(field)) for field in _DETAIL_ONLY_FIELDS)
        )
        if all(before[field] == after[field] for field in after) and already_authoritative:
            continue
        raw_payload = dict(before["raw_payload"])
        normalized_payload = dict(normalized_before)
        normalized_payload.update({key: value for key, value in after.items() if key != "tax_rate"})
        for field in _DETAIL_ONLY_FIELDS:
            normalized_payload[field] = None
        normalized_payload.update(
            {
                "source_sheet_name": "发票基础信息",
                "source_sheet_role": "invoice_header",
                "source_workbook_sha256": source_sha256,
                "invoice_header_repair_fingerprint": source_fingerprint,
            }
        )
        raw_payload["normalized_payload"] = normalized_payload
        updates.append(
            {
                "invoice_id": before["invoice_id"],
                "digital_invoice_no": fact["digital_invoice_no"],
                "invoice_month": "2026-06",
                "before": before,
                **after,
                "raw_payload": raw_payload,
            }
        )
    return {
        "source_fingerprint": source_fingerprint,
        "source_sha256": source_sha256,
        "target_count": len(snapshot),
        "update_count": len(updates),
        "updates": updates,
        "affected_months": ["2026-06"],
        "rollback_manifest": {"restore_invoices": restore_rows},
    }


def public_invoice_header_fact_repair_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "operation": "invoice_header_fact_repair",
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "source_sha256": plan["source_sha256"],
        "target_count": plan["target_count"],
        "update_count": plan["update_count"],
        "affected_months": plan["affected_months"],
        "completion": completion,
        "rollback_manifest": plan["rollback_manifest"],
        "authorized_write_scope": [
            "app.invoices",
            "ops.operation_events",
        ],
    }


def _money(value: Any) -> str:
    return format(Decimal(str(value or "0")).quantize(Decimal("0.01")), "f")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_verified_financial_repair_plan(
    snapshot: list[dict[str, Any]], *, invoice_ids: list[str],
    sources: list[dict[str, Any]], cache_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Correct only explicit existing facts using verified tax header originals."""
    if not invoice_ids or len(invoice_ids) != len(set(invoice_ids)):
        raise ValueError("Explicit unique invoice IDs are required.")
    if {row["invoice_id"] for row in snapshot} != set(invoice_ids) or len(snapshot) != len(invoice_ids):
        raise ValueError("Every repair invoice must resolve exactly once.")
    identities = InvoiceIdentityService()
    target_keys = {identities.canonical_key_for_mapping(row) for row in snapshot}
    facts: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for source in sources:
        for row in source["rows"]:
            key = identities.canonical_key_for_mapping(row)
            if key not in target_keys:
                continue
            if any(row.get(field) in (None, "") for field in ("amount", "tax_amount", "total_with_tax", "invoice_date")):
                raise ValueError(f"Tax header {key} lacks explicit financial fields.")
            values = tuple(_money(row[field]) for field in ("amount", "tax_amount", "total_with_tax"))
            if Decimal(values[0]) + Decimal(values[1]) != Decimal(values[2]):
                raise ValueError(f"Tax header {key} has inconsistent amounts.")
            if key in facts:
                old = facts[key][0]
                if values != tuple(_money(old[field]) for field in ("amount", "tax_amount", "total_with_tax")) or str(old["invoice_date"]) != str(row["invoice_date"]):
                    raise ValueError(f"Tax originals disagree for {key}.")
            else:
                facts[key] = row, source
    fingerprint = _fingerprint({"snapshot": snapshot, "sources": sources, "caches": cache_rows})
    updates = []
    target_keys = set()
    for current in snapshot:
        key = identities.canonical_key_for_mapping(current)
        if not key or key not in facts:
            raise ValueError(f"No tax original proves invoice {current['invoice_id']}.")
        target_keys.add(key)
        fact, source = facts[key]
        if current["invoice_type"] != "input" or str(current["invoice_date"])[:10] != str(fact["invoice_date"])[:10]:
            raise ValueError(f"Invoice date/type differs from tax original: {key}.")
        if _money(current["total_with_tax"]) != _money(fact["total_with_tax"]):
            raise ValueError(f"Repair may not change the invoice total: {key}.")
        amounts = {field: _money(fact[field]) for field in ("amount", "tax_amount", "total_with_tax")}
        amounts["signed_amount"] = amounts["amount"]
        if all(_money(current[field]) == value for field, value in amounts.items()):
            continue
        raw = dict(current["raw_payload"] or {})
        normalized = dict(raw.get("normalized_payload") or raw)
        normalized.update(amounts)
        normalized.update(source_sheet_name="发票基础信息", source_sheet_role="invoice_header",
                          source_workbook_sha256=source["sha256"],
                          financial_repair_source_file_id=source["file_id"],
                          financial_repair_fingerprint=fingerprint)
        raw["normalized_payload"] = normalized
        updates.append({"invoice_id": current["invoice_id"], "identity_key": key,
                        "before": current, "raw_payload": raw, **amounts})
    invalidate_keys = sorted({row["source_attachment_key"] for row in cache_rows
        if any(identities.canonical_key_for_mapping(item) in target_keys
               for item in row["invoices"] if isinstance(item, dict))})
    return {"source_fingerprint": fingerprint, "updates": updates,
            "target_count": len(snapshot), "update_count": len(updates),
            "invalidate_cache_keys": invalidate_keys,
            "affected_months": sorted({str(row["invoice_date"])[:7] for row in snapshot}),
            "sources": [{key: source[key] for key in ("file_id", "sha256", "filename")} for source in sources]}
