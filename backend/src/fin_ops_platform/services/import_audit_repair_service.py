from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from fin_ops_platform.services.import_file_service import aggregate_invoice_line_rows


def build_import_audit_repair_plan(snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    source_fingerprint = _fingerprint(snapshot)
    bank_rows = _bank_row_plan(
        snapshot.get("bank_files") or [],
        snapshot.get("bank_transactions") or [],
        snapshot.get("bank_rows") or [],
    )
    invoice_updates = _invoice_update_plan(snapshot.get("invoice_rows") or [])
    return {
        "source_fingerprint": source_fingerprint,
        "bank_rows": bank_rows,
        "invoice_updates": invoice_updates,
        "affected_invoice_months": sorted(
            {_text(update.get("invoice_month")) for update in invoice_updates if _text(update.get("invoice_month"))}
        ),
        "rollback_manifest": {
            "delete_bank_row_ids": [row["row_id"] for row in bank_rows],
            "restore_invoices": [update["before"] for update in invoice_updates],
        },
    }


def public_repair_report(plan: dict[str, Any], *, mode: str, written: bool) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "bank_row_count": len(plan["bank_rows"]),
        "invoice_update_count": len(plan["invoice_updates"]),
        "affected_invoice_months": plan["affected_invoice_months"],
        "rollback_manifest": plan["rollback_manifest"],
        "authorized_write_scope": ["app.import_batch_rows", "app.invoices"],
    }


def _bank_row_plan(
    files: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    transactions_by_key: dict[str, dict[str, Any]] = {}
    for transaction in transactions:
        key = _text(transaction.get("source_unique_key"))
        if key in transactions_by_key:
            raise ValueError(f"Duplicate canonical bank transaction identity: {key}")
        transactions_by_key[key] = transaction
    existing_by_id = {_text(row.get("row_id")): row for row in existing_rows}
    if len(existing_by_id) != len(existing_rows):
        raise ValueError("Duplicate strict bank import row ids prevent deterministic repair.")
    desired_row_ids: set[str] = set()
    planned: list[dict[str, Any]] = []
    for file in files:
        batch_id = _text(file.get("batch_id"))
        payload = _payload(file.get("raw_payload"))
        row_results = [dict(row) for row in list(payload.get("row_results") or []) if isinstance(row, dict)]
        normalized_rows = [dict(row) for row in list(payload.get("normalized_rows") or []) if isinstance(row, dict)]
        if len(row_results) != len(normalized_rows) or len(row_results) != int(file.get("row_count") or 0):
            raise ValueError(f"Bank import file {file.get('file_id')} row evidence is incomplete.")
        desired_batch_rows: list[dict[str, Any]] = []
        new_batch_rows: list[dict[str, Any]] = []
        for row_no, (row_result, normalized) in enumerate(zip(row_results, normalized_rows, strict=True), start=1):
            source_key = _text(row_result.get("source_unique_key") or normalized.get("source_unique_key"))
            decision = _text(row_result.get("decision"))
            if decision not in {"created", "status_updated", "duplicate_skipped", "suspected_duplicate", "error"}:
                raise ValueError(f"Bank import {batch_id} row {row_no} has an unknown registered decision.")
            transaction = transactions_by_key.get(source_key)
            if decision in {"created", "status_updated", "duplicate_skipped"} and transaction is None:
                raise ValueError(f"Canonical bank transaction is missing for {batch_id} row {row_no}.")
            if decision in {"created", "status_updated"} and _text(transaction.get("source_batch_id")) != batch_id:
                raise ValueError(f"Canonical bank transaction owner mismatch for {batch_id} row {row_no}.")
            linked_object_id = (
                transaction["transaction_id"]
                if transaction is not None and decision in {"created", "status_updated", "duplicate_skipped"}
                else None
            )
            row_id = f"batch_row:{batch_id}:{row_no:05d}"
            desired_row_ids.add(row_id)
            repaired_result = {
                **row_result,
                "id": row_id,
                "batch_id": batch_id,
                "row_no": row_no,
                "source_record_type": "bank_transaction",
                "source_unique_key": source_key,
                "decision": decision,
                "decision_reason": (
                    _text(row_result.get("decision_reason"))
                    or "Recovered from registered import evidence."
                ),
                "linked_object_type": "bank_transaction" if linked_object_id else None,
                "linked_object_id": linked_object_id,
            }
            repaired = {
                "row_id": row_id,
                "batch_id": batch_id,
                "row_no": row_no,
                "source_unique_key": source_key,
                "data_fingerprint": repaired_result.get("data_fingerprint"),
                "decision": decision,
                "decision_reason": repaired_result["decision_reason"],
                "linked_object_id": linked_object_id,
                "identity_kind": repaired_result.get("identity_kind"),
                "account_no": repaired_result.get("account_no") or normalized.get("account_no"),
                "trade_time": (
                    repaired_result.get("trade_time")
                    or normalized.get("trade_time")
                    or normalized.get("pay_receive_time")
                    or normalized.get("txn_date")
                ),
                "direction": (
                    repaired_result.get("direction")
                    or normalized.get("txn_direction")
                    or normalized.get("direction")
                ),
                "amount": repaired_result.get("amount") or normalized.get("amount"),
                "counterparty_name": (
                    repaired_result.get("counterparty_name")
                    or normalized.get("counterparty_name_raw")
                    or normalized.get("counterparty_name")
                ),
                "raw_payload": {**repaired_result, "normalized_row": normalized},
            }
            desired_batch_rows.append(repaired)
            existing = existing_by_id.get(row_id)
            if existing is not None:
                _assert_existing_bank_row_matches(existing, repaired)
            else:
                new_batch_rows.append(repaired)
        counts = Counter(row["decision"] for row in desired_batch_rows)
        actual = {
            "row_count": len(desired_batch_rows),
            "success_count": counts["created"] + counts["status_updated"],
            "error_count": counts["error"],
            "duplicate_count": counts["duplicate_skipped"],
            "suspected_duplicate_count": counts["suspected_duplicate"],
            "updated_count": counts["status_updated"],
        }
        expected = {key: int(file.get(key) or 0) for key in actual}
        if actual != expected:
            raise ValueError(f"Bank import batch {batch_id} decision counts do not match registered evidence.")
        planned.extend(new_batch_rows)
    unexpected_existing_ids = set(existing_by_id) - desired_row_ids
    if unexpected_existing_ids:
        raise ValueError("Existing strict bank import rows use non-deterministic ids; automatic repair refused.")
    return planned


def _assert_existing_bank_row_matches(existing: dict[str, Any], desired: dict[str, Any]) -> None:
    for field_name in (
        "batch_id",
        "row_no",
        "source_unique_key",
        "data_fingerprint",
        "decision",
        "linked_object_id",
        "identity_kind",
    ):
        if _text(existing.get(field_name)) != _text(desired.get(field_name)):
            raise ValueError(f"Existing bank import row {desired['row_id']} conflicts on {field_name}.")


def _invoice_update_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        batch_id = _text(row.get("batch_id"))
        invoice_id = _text(row.get("invoice_id"))
        if invoice_id and _text(row.get("invoice_source_batch_id")) == batch_id:
            grouped[(batch_id, invoice_id)].append(row)
    updates: list[dict[str, Any]] = []
    for (batch_id, invoice_id), component_rows in grouped.items():
        if len(component_rows) < 2:
            continue
        normalized_rows = [_normalized_row(row.get("row_raw_payload")) for row in component_rows]
        _assert_invoice_headers_match(invoice_id, normalized_rows)
        aggregated_rows = aggregate_invoice_line_rows(normalized_rows)
        if len(aggregated_rows) != 1:
            continue
        aggregate = aggregated_rows[0]
        amount = Decimal(_text(aggregate.get("amount")) or "0")
        signed_amount = _sum_decimal(normalized_rows, "signed_amount")
        tax_amount = Decimal(_text(aggregate.get("tax_amount")) or "0")
        total_with_tax = Decimal(_text(aggregate.get("total_with_tax")) or "0")
        tax_rate = _text(aggregate.get("tax_rate"))
        current = component_rows[0]
        before = {
            "invoice_id": invoice_id,
            "source_batch_id": batch_id,
            "amount": _decimal_text(current.get("amount")),
            "signed_amount": _decimal_text(current.get("signed_amount")),
            "tax_amount": _decimal_text(current.get("tax_amount")),
            "total_with_tax": _decimal_text(current.get("total_with_tax")),
            "tax_rate": current.get("tax_rate"),
        }
        after = {
            "amount": _decimal_text(amount),
            "signed_amount": _decimal_text(signed_amount),
            "tax_amount": _decimal_text(tax_amount),
            "total_with_tax": _decimal_text(total_with_tax),
            "tax_rate": tax_rate,
        }
        if all(before[key] == after[key] for key in after):
            continue
        raw_payload = dict(current.get("invoice_raw_payload") or {})
        normalized_payload = dict(raw_payload.get("normalized_payload") or raw_payload)
        normalized_payload.update(after)
        raw_payload["normalized_payload"] = normalized_payload
        invoice_month = _text(current.get("invoice_month") or normalized_rows[0].get("invoice_date"))[:7]
        updates.append(
            {
                "invoice_id": invoice_id,
                "invoice_month": invoice_month,
                "source_batch_id": batch_id,
                **after,
                "raw_payload": raw_payload,
                "before": before,
            }
        )
    return updates


def _assert_invoice_headers_match(invoice_id: str, rows: list[dict[str, Any]]) -> None:
    for field_name in (
        "digital_invoice_no",
        "invoice_code",
        "invoice_no",
        "invoice_date",
        "seller_tax_no",
        "buyer_tax_no",
    ):
        values = {_text(row.get(field_name)) for row in rows if _text(row.get(field_name))}
        if len(values) > 1:
            raise ValueError(f"Invoice {invoice_id} has conflicting {field_name} component evidence.")


def _sum_decimal(rows: list[dict[str, Any]], field_name: str) -> Decimal:
    try:
        return sum((Decimal(_text(row.get(field_name)) or "0") for row in rows), Decimal("0"))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid invoice component decimal field: {field_name}") from exc


def _normalized_row(raw_payload: Any) -> dict[str, Any]:
    return dict(_payload(raw_payload).get("normalized_row") or {})


def _payload(value: Any) -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return dict(payload.get("normalized_payload") or payload)


def _decimal_text(value: Any) -> str:
    return format(Decimal(str(value or "0")).normalize(), "f")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fingerprint(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
