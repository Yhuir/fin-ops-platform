"""从准确登记的原件恢复票种；不重写金额、身份或业务关系。"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService
from fin_ops_platform.services.invoice_kind import invoice_kind_fields

SOURCE_METADATA_FIELDS = ("invoice_source", "is_positive_invoice", "risk_level", "issuer", "remark")


def build_source_attribute_repair_plan(
    snapshot: list[dict[str, Any]], sources: list[dict[str, Any]], unavailable: list[dict[str, str]]
) -> dict[str, Any]:
    identities = InvoiceIdentityService()
    candidates: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for source in sources:
        for row in source["rows"]:
            key = identities.canonical_key_for_mapping(row)
            if key and not key.startswith("tax:"):
                candidates.setdefault(key, []).append((row, {k: v for k, v in source.items() if k != "rows"}))
    updates, states = [], Counter()
    for current in snapshot:
        invoice_id = current["invoice_id"]
        raw = deepcopy(current["raw_payload"])
        payload = dict(raw.get("normalized_payload") or raw)
        facts = [
            (row, source)
            for row, source in candidates.get(identities.canonical_key_for_mapping(current), [])
            if invoice_id in source["invoice_ids"]
        ]
        conflicts = any(
            current.get("buyer_tax_no")
            and row.get("buyer_tax_no")
            and str(row["buyer_tax_no"]) != str(current["buyer_tax_no"])
            for row, _ in facts
        )
        conflicts = conflicts or any(
            current.get("invoice_date")
            and (row.get("invoice_date") or row.get("issue_date"))
            and str(current["invoice_date"]) != str(row.get("invoice_date") or row.get("issue_date"))[:10]
            for row, _ in facts
        )
        provided = [
            (row, source, invoice_kind_fields(row.get("invoice_kind")))
            for row, source in facts
            if row.get("invoice_kind")
        ]
        codes = {item["invoice_kind_code"] or item["invoice_kind"] for _, _, item in provided}
        # The registered export can name the toll subtype while the same PDF
        # explicitly names its general-invoice parent. Retain both originals,
        # and use the explicitly supplied subtype without deriving a new label.
        toll_general = codes == {"toll", "vat_general"}
        conflicts = conflicts or (len(codes) > 1 and not toll_general)
        evidence = [
            {
                "file_id": source["file_id"],
                "sha256": source["sha256"],
                "source_kind": source["source_kind"],
                "source_row_number": row.get("source_row_number"),
                "source_sheet_name": row.get("source_sheet_name"),
                "invoice_kind": row.get("invoice_kind"),
            }
            for row, source in facts
        ]
        if conflicts:
            fields = invoice_kind_fields(None, missing_status="conflict")
        elif provided:
            fields = (
                next(item for _, _, item in provided if item["invoice_kind_code"] == "toll")
                if toll_general
                else provided[0][2]
            )
        else:
            fields = invoice_kind_fields(
                None,
                missing_status=(
                    "unreadable"
                    if facts and all(source["source_kind"] in ("oa_attachment", "etc_pdf") for _, source in facts)
                    else "not_provided"
                )
                if facts
                else "source_unavailable",
            )
        fields["invoice_kind_evidence"] = evidence
        # Only the source that already owns the financial group can restore its
        # metadata. Never assemble a new cross-file financial/identity group.
        owner_id = payload.get("financial_repair_source_file_id")
        owner = next((row for row, source in facts if source["file_id"] == owner_id), None)
        if owner is None and len(facts) == 1:
            owner = facts[0][0]
        fields.update(
            {
                field: owner.get(field) if owner is not None and not conflicts else None
                for field in SOURCE_METADATA_FIELDS
            }
        )
        states[fields["invoice_kind_status"]] += 1
        if any(payload.get(k) != v for k, v in fields.items()):
            payload.update(fields)
            raw["normalized_payload"] = payload
            updates.append({"invoice_id": invoice_id, "before": current, "raw_payload": raw})
    return {
        "updates": updates,
        "target_count": len(snapshot),
        "update_count": len(updates),
        "classification_counts": dict(states),
        "unavailable_sources": unavailable,
        "rollback_manifest": {
            "version": 1,
            "repair_type": "invoice_source_attributes",
            "invoices": [u["before"] for u in updates],
        },
    }
