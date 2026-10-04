from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.imports import normalize_name
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
    return "" if value is None else str(value).strip()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


VERIFIED_PARTY_FIELDS = ("seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no")


def _source_money(value: Any) -> str | None:
    if value is None or value == "":
        return None
    number = Decimal(str(value).replace(",", ""))
    if not number.is_finite():
        raise ValueError("Original financial values must be finite.")
    return format(number.quantize(Decimal("0.01")), "f")


def _source_financial_fact(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize explicit source fields; absence is never replaced with arithmetic."""
    tax = row.get("tax_amount")
    text = row.get("tax_amount_text")
    if tax in ("*", "免税", "不征税"):
        text, tax = tax, None
    result = {field: _source_money(row.get(field)) for field in ("amount", "total_with_tax")}
    result.update(tax_amount=_source_money(tax), tax_amount_text=text or None,
                  tax_rate=_text(row.get("tax_rate")) or None)
    values = [result[field] for field in ("amount", "tax_amount", "total_with_tax")]
    if all(value is not None for value in values) and Decimal(values[0]) + Decimal(values[1]) != Decimal(values[2]):
        raise ValueError("Tax original has inconsistent amounts.")
    if all(value is None for value in values):
        raise ValueError("Tax original lacks explicit financial fields.")
    return result


def build_verified_financial_repair_plan(
    snapshot: list[dict[str, Any]], *, invoice_ids: list[str],
    sources: list[dict[str, Any]], cache_rows: list[dict[str, Any]],
    repair_party_fields: bool = False,
) -> dict[str, Any]:
    """Repair original invoice values and detail rows without changing business identity."""
    if not invoice_ids or len(invoice_ids) != len(set(invoice_ids)):
        raise ValueError("Explicit unique invoice IDs are required.")
    if {row["invoice_id"] for row in snapshot} != set(invoice_ids) or len(snapshot) != len(invoice_ids):
        raise ValueError("Every repair invoice must resolve exactly once.")
    identities = InvoiceIdentityService()
    target_keys = {identities.canonical_key_for_mapping(row) for row in snapshot}
    facts: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for source in sources:
        for row in source["rows"]:
            key = identities.canonical_key_for_mapping(row)
            if key not in target_keys:
                continue
            if not row.get("invoice_date"):
                raise ValueError(f"Tax original {key} lacks an explicit date.")
            fact = {**row, **_source_financial_fact(row)}
            lines = []
            for line in row.get("source_line_items") or []:
                item = {**line, **_source_financial_fact(line)}
                item.pop("inferred_fields", None)
                lines.append(item)
            fact["source_line_items"] = lines
            if repair_party_fields and any(not _text(fact.get(field)) for field in VERIFIED_PARTY_FIELDS):
                raise ValueError(f"Tax header {key} lacks explicit party fields.")
            if key in facts:
                previous = facts[key][0][0]
                if repair_party_fields and any(_text(previous.get(field)) != _text(fact.get(field)) for field in VERIFIED_PARTY_FIELDS):
                    raise ValueError(f"Tax originals disagree on party fields for {key}.")
                compared = ("amount", "tax_amount", "total_with_tax", "tax_rate", "tax_amount_text", "invoice_date")
                positions = {"source_row_number", "source_sheet_name", "source_region_key"}
                previous_lines = [{field: value for field, value in line.items() if field not in positions}
                                  for line in previous["source_line_items"]]
                current_lines = [{field: value for field, value in line.items() if field not in positions}
                                 for line in fact["source_line_items"]]
                if previous_lines != current_lines or any(previous.get(field) != fact.get(field) for field in compared):
                    raise ValueError(f"Tax originals disagree for {key}.")
            facts.setdefault(key, []).append((fact, source))
    fingerprint = _fingerprint({"snapshot": snapshot, "sources": sources, "caches": cache_rows, "repair_party_fields": repair_party_fields})
    updates = []
    verified_invoice_facts = []
    changed_keys = set()
    for current in snapshot:
        key = identities.canonical_key_for_mapping(current)
        if not key or key not in facts:
            raise ValueError(f"No tax original proves invoice {current['invoice_id']}.")
        raw = dict(current["raw_payload"] or {})
        normalized = dict(raw["normalized_payload"] if "normalized_payload" in raw else raw)
        prior_source_id = normalized.get("financial_repair_source_file_id")
        prior_source_sha256 = normalized.get("source_workbook_sha256")
        fact, source = next((candidate for candidate in facts[key]
                             if candidate[1]["file_id"] == prior_source_id
                             and candidate[1]["sha256"] == prior_source_sha256), facts[key][0])
        if current["invoice_type"] not in {"input", "output"} or str(current["invoice_date"])[:10] != str(fact["invoice_date"])[:10]:
            raise ValueError(f"Invoice date/type differs from tax original: {key}.")
        if fact.get("invoice_type") and fact["invoice_type"] != current["invoice_type"]:
            raise ValueError(f"Invoice date/type differs from tax original: {key}.")
        if _source_money(current["total_with_tax"]) != fact["total_with_tax"]:
            raise ValueError(f"Repair may not change the invoice total: {key}.")
        values = {field: fact[field] for field in ("amount", "tax_amount", "total_with_tax", "tax_rate", "tax_amount_text")}
        values["signed_amount"] = values["amount"]
        party = {field: _text(fact[field]) for field in VERIFIED_PARTY_FIELDS} if repair_party_fields else {}
        if party:
            party["counterparty_name"] = party["seller_name"] if current["invoice_type"] == "input" else party["buyer_name"]
        same = all(_source_money(current.get(field)) == values[field] for field in ("amount", "signed_amount", "tax_amount", "total_with_tax"))
        same = same and (_text(current.get("tax_rate")) or None) == values["tax_rate"]
        same = same and normalized.get("tax_amount_text") == values["tax_amount_text"]
        same = same and normalized.get("source_line_items") == fact["source_line_items"]
        same = same and normalized.get("source_line_count") == len(fact["source_line_items"])
        same = same and all(field in normalized and _source_money(normalized[field]) == values[field]
                            for field in ("amount", "signed_amount", "tax_amount", "total_with_tax"))
        same = same and "tax_rate" in normalized and (_text(normalized["tax_rate"]) or None) == values["tax_rate"]
        same = same and "tax_amount_text" in normalized
        same = same and "inferred_fields" not in normalized and "inferred_fields" not in raw
        same = same and all(_text(current.get(field)) == value and _text(normalized.get(field)) == value
                            for field, value in party.items())
        same = same and bool(_text(normalized.get("financial_repair_fingerprint")))
        same = same and prior_source_id == source["file_id"] and prior_source_sha256 == source["sha256"]
        verified_invoice_facts.append({
            "invoice_id": current["invoice_id"],
            "repair_fingerprint": normalized["financial_repair_fingerprint"] if same else fingerprint,
            "source_file_id": source["file_id"], "source_sha256": source["sha256"],
            "invoice_type": current["invoice_type"], "identity_key": key,
            "invoice_date": str(current["invoice_date"])[:10],
            "after": {**values, "source_line_items": fact["source_line_items"]},
            "party_after": party,
        })
        if same:
            continue
        normalized.pop("inferred_fields", None)
        raw.pop("inferred_fields", None)
        normalized.update(values)
        normalized.update(party)
        normalized["source_line_items"] = fact["source_line_items"]
        normalized["source_line_count"] = len(fact["source_line_items"])
        if party:
            counterparty = dict(normalized.get("counterparty") or {})
            counterparty.update(name=party["counterparty_name"], normalized_name=normalize_name(party["counterparty_name"]))
            counterparty["tax_no"] = party["seller_tax_no"] if current["invoice_type"] == "input" else party["buyer_tax_no"]
            normalized["counterparty"] = counterparty
        normalized.update(source_sheet_name=fact.get("source_sheet_name"), source_sheet_role="invoice_header",
                          financial_repair_source_kind=source.get("source_kind", "invoice_export"),
                          source_workbook_sha256=source["sha256"], financial_repair_source_file_id=source["file_id"],
                          financial_repair_fingerprint=fingerprint)
        raw["normalized_payload"] = normalized
        updates.append({"invoice_id": current["invoice_id"], "identity_key": key,
                        "before": current, "raw_payload": raw, **values, "party_fields": party})
        changed_keys.add(key)
    invalidate_keys = sorted({row["source_attachment_key"] for row in cache_rows
        if any(identities.canonical_key_for_mapping(item) in changed_keys
               for item in row["invoices"] if isinstance(item, dict))})
    manifest = {"version": 1, "repair_type": "invoice_source_values", "source_fingerprint": fingerprint,
                "invoices": [item["before"] for item in updates],
                "attachment_caches": [row for row in cache_rows if row["source_attachment_key"] in invalidate_keys]}
    return {"source_fingerprint": fingerprint, "updates": updates,
            "verified_invoice_facts": verified_invoice_facts,
            "target_count": len(snapshot), "update_count": len(updates),
            "invalidate_cache_keys": invalidate_keys, "rollback_manifest": manifest,
            "rollback_manifest_fingerprint": _fingerprint(manifest),
            "affected_months": sorted({str(row["invoice_date"])[:7] for row in snapshot}),
            "sources": [{key: source[key] for key in ("file_id", "sha256", "filename")} for source in sources]}
