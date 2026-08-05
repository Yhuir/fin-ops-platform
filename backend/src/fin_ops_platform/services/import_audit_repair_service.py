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
    lifecycle_repairs = _lifecycle_repair_plan(snapshot)
    etc_session_retirements = _etc_session_retirement_plan(snapshot)
    return {
        "source_fingerprint": source_fingerprint,
        "bank_rows": bank_rows,
        "invoice_updates": invoice_updates,
        "lifecycle_repairs": lifecycle_repairs,
        "etc_session_retirements": etc_session_retirements,
        "etc_session_retirement_mode": bool(snapshot.get("etc_session_retirement_requested")),
        "affected_invoice_months": sorted(
            {_text(update.get("invoice_month")) for update in invoice_updates if _text(update.get("invoice_month"))}
        ),
        "rollback_manifest": {
            "delete_bank_row_ids": [row["row_id"] for row in bank_rows],
            "restore_invoices": [update["before"] for update in invoice_updates],
            "restore_import_lifecycle": [repair["before"] for repair in lifecycle_repairs],
            "restore_etc_import_sessions": [repair["before"] for repair in etc_session_retirements],
            "restore_import_row_links": [
                row_link["before"]
                for repair in lifecycle_repairs
                for row_link in list(repair.get("row_links") or [])
            ],
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
        "lifecycle_repair_count": len(plan["lifecycle_repairs"]),
        "etc_session_retirement_count": len(plan["etc_session_retirements"]),
        "lifecycle_row_link_repair_count": sum(
            len(list(repair.get("row_links") or [])) for repair in plan["lifecycle_repairs"]
        ),
        "affected_invoice_months": plan["affected_invoice_months"],
        "rollback_manifest": plan["rollback_manifest"],
        "authorized_write_scope": (
            ["app.etc_import_sessions"]
            if plan["etc_session_retirement_mode"]
            else [
                "app.import_batch_rows",
                "app.invoices",
                "app.import_batches",
                "app.import_files",
            ]
        ),
    }


def _etc_session_retirement_plan(snapshot: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    requested = sorted({_text(row.get("session_id")) for row in snapshot.get("etc_session_retirement_requested") or []})
    requested = [session_id for session_id in requested if session_id]
    if not requested:
        return []
    targets = list(snapshot.get("etc_session_retirement_targets") or [])
    targets_by_id = {_text(row.get("session_id")): row for row in targets}
    if len(targets_by_id) != len(targets) or set(targets_by_id) != set(requested):
        raise ValueError("ETC import session retirement targets must resolve exactly once.")

    repairs: list[dict[str, Any]] = []
    retired_revision = "etc-import-page-audit.v1.deleted-task-retired"
    for session_id in requested:
        target = targets_by_id[session_id]
        revision = _text(target.get("audit_contract_revision"))
        if revision == retired_revision:
            continue
        if revision != "etc-import-page-audit.v1":
            raise ValueError(f"ETC import session {session_id} is not registered under the strict audit contract.")
        if _text(target.get("session_status")) not in {"preview_ready", "failed", "succeeded"}:
            raise ValueError(f"ETC import session {session_id} is not in a retireable state.")
        task_payload = _payload(target.get("task_raw_payload"))
        if _text(target.get("task_status")) != "deleted" or _text(task_payload.get("status")) != "deleted":
            raise ValueError(f"ETC import session {session_id} task is not formally deleted.")
        if int(target.get("active_job_count") or 0) or int(target.get("active_outbox_count") or 0):
            raise ValueError(f"ETC import session {session_id} still has active runtime work.")
        repairs.append(
            {
                "session_id": session_id,
                "task_id": _text(target.get("task_id")),
                "session_status": _text(target.get("session_status")),
                "before": {
                    "session_id": session_id,
                    "audit_contract_revision": revision,
                },
                "after_revision": retired_revision,
            }
        )
    return repairs


def _lifecycle_repair_plan(snapshot: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    requested = list(snapshot.get("lifecycle_requested") or [])
    if not requested:
        return []
    if len(requested) != 1:
        raise ValueError("Import lifecycle repair requires exactly one batch/file target.")
    request = requested[0]
    batch_id = _text(request.get("batch_id"))
    file_id = _text(request.get("file_id"))
    targets = list(snapshot.get("lifecycle_targets") or [])
    if len(targets) != 1:
        raise ValueError(f"Import lifecycle target must resolve exactly once: {batch_id}/{file_id}")
    target = targets[0]
    if _text(target.get("batch_id")) != batch_id or _text(target.get("file_id")) != file_id:
        raise ValueError("Import lifecycle target identity changed during repair planning.")
    if _text(target.get("batch_type")) not in {"input_invoice", "output_invoice"}:
        raise ValueError("Import lifecycle repair only supports invoice file imports.")

    jobs = list(snapshot.get("lifecycle_jobs") or [])
    succeeded_jobs = [row for row in jobs if _text(row.get("status")) == "succeeded"]
    active_jobs = [row for row in jobs if _text(row.get("status")) in {"pending", "processing"}]
    if active_jobs:
        raise ValueError("Import lifecycle repair refused while a matching import job is active.")
    if len(succeeded_jobs) != 1:
        raise ValueError("Import lifecycle repair requires exactly one succeeded import job.")
    job = succeeded_jobs[0]
    job_payload = dict(job.get("payload") or {})
    result_payload = dict(job.get("result_payload") or {})
    selected_file_ids = {_text(value) for value in list(job_payload.get("selected_file_ids") or []) if _text(value)}
    if (
        _text(job.get("stage")) != "succeeded"
        or _text(job.get("import_session_id") or job_payload.get("session_id")) != _text(target.get("session_id"))
        or file_id not in selected_file_ids
        or int(result_payload.get("selected") or 0) != len(selected_file_ids)
        or int(result_payload.get("confirmed") or 0) != len(selected_file_ids)
    ):
        raise ValueError("Succeeded import job does not prove the selected file was fully confirmed.")

    evidence_rows = list(snapshot.get("lifecycle_row_evidence") or [])
    if len(evidence_rows) != 1:
        raise ValueError("Import lifecycle row evidence must resolve exactly once.")
    evidence = evidence_rows[0]
    expected_counts = {
        "row_count": int(target.get("row_count") or 0),
        "success_count": int(target.get("success_count") or 0),
        "error_count": int(target.get("error_count") or 0),
        "duplicate_count": int(target.get("duplicate_count") or 0),
        "suspected_duplicate_count": int(target.get("suspected_duplicate_count") or 0),
        "updated_count": int(target.get("updated_count") or 0),
    }
    actual_counts = {
        "row_count": int(evidence.get("row_count") or 0),
        "success_count": int(evidence.get("created_count") or 0) + int(evidence.get("status_updated_count") or 0),
        "error_count": int(evidence.get("error_count") or 0),
        "duplicate_count": int(evidence.get("duplicate_count") or 0),
        "suspected_duplicate_count": int(evidence.get("suspected_duplicate_count") or 0),
        "updated_count": int(evidence.get("status_updated_count") or 0),
    }
    if actual_counts != expected_counts:
        raise ValueError("Import lifecycle batch counters do not match durable row evidence.")
    row_links = list(snapshot.get("lifecycle_row_links") or [])
    if len(row_links) != expected_counts["row_count"]:
        raise ValueError("Import lifecycle row-link evidence does not cover the registered batch.")
    row_link_repairs: list[dict[str, Any]] = []
    linked_decision_count = 0
    for row in row_links:
        decision = _text(row.get("decision"))
        current_type = _text(row.get("linked_object_type"))
        current_id = _text(row.get("linked_object_id"))
        if decision not in {"created", "status_updated", "duplicate_skipped"}:
            if current_type or current_id:
                raise ValueError("Non-linked import decision unexpectedly owns a canonical invoice link.")
            continue
        linked_decision_count += 1
        if int(row.get("candidate_count") or 0) != 1 or not _text(row.get("candidate_invoice_id")):
            raise ValueError("Import lifecycle canonical source-link evidence is not one-to-one.")
        if decision == "created" and not bool(row.get("candidate_is_batch_owner")):
            raise ValueError("Created import row canonical invoice owner does not match the target batch.")
        candidate_invoice_id = _text(row.get("candidate_invoice_id"))
        if current_type or current_id:
            if current_type != "invoice" or current_id != candidate_invoice_id:
                raise ValueError("Existing import row canonical link conflicts with source-link evidence.")
            continue
        row_link_repairs.append(
            {
                "row_id": _text(row.get("row_id")),
                "decision": decision,
                "source_id": _text(row.get("source_id")),
                "linked_object_id": candidate_invoice_id,
                "before": {
                    "row_id": _text(row.get("row_id")),
                    "linked_object_type": None,
                    "linked_object_id": None,
                },
            }
        )
    if linked_decision_count != expected_counts["success_count"] + expected_counts["duplicate_count"]:
        raise ValueError("Import lifecycle linked decision count does not match registered batch counters.")

    batch_payload = _payload(target.get("batch_raw_payload"))
    file_payload = _payload(target.get("file_raw_payload"))
    terminal = (
        _text(target.get("batch_status")) == "completed"
        and _text(batch_payload.get("status")) == "completed"
        and _text(target.get("file_status")) == "confirmed"
        and _text(file_payload.get("status")) == "confirmed"
        and _text(file_payload.get("batch_id")) == batch_id
        and _text(file_payload.get("session_status")) == "confirmed"
        and not row_link_repairs
    )
    if terminal:
        return []
    downgraded = (
        _text(target.get("batch_status")) == "pending"
        and _text(batch_payload.get("status")) == "pending"
        and _text(target.get("file_status")) == "preview_ready"
        and _text(file_payload.get("status")) == "preview_ready"
        and not _text(file_payload.get("batch_id"))
        and _text(file_payload.get("preview_batch_id")) == batch_id
        and _text(file_payload.get("session_status")) == "preview_ready"
    )
    if not downgraded:
        raise ValueError("Import lifecycle state is neither the exact downgraded state nor the terminal state.")
    return [
        {
            "batch_id": batch_id,
            "file_id": file_id,
            "row_links": row_link_repairs,
            "before": {
                "batch_id": batch_id,
                "batch_status": _text(target.get("batch_status")),
                "batch_payload_status": _text(batch_payload.get("status")),
                "file_id": file_id,
                "file_status": _text(target.get("file_status")),
                "file_payload_status": _text(file_payload.get("status")),
                "file_payload_batch_id": _text(file_payload.get("batch_id")) or None,
                "file_payload_session_status": _text(file_payload.get("session_status")),
            },
        }
    ]


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
    planned_batch_ids: set[str] = set()
    planned: list[dict[str, Any]] = []
    for file in files:
        batch_id = _text(file.get("batch_id"))
        if not batch_id or batch_id in planned_batch_ids:
            raise ValueError(f"Strict bank import batch ownership is not one-file-to-one-batch: {batch_id}")
        planned_batch_ids.add(batch_id)
        payload = _payload(file.get("raw_payload"))
        row_results = [dict(row) for row in list(payload.get("row_results") or []) if isinstance(row, dict)]
        normalized_rows = [dict(row) for row in list(payload.get("normalized_rows") or []) if isinstance(row, dict)]
        if len(row_results) != len(normalized_rows) or len(row_results) != int(file.get("row_count") or 0):
            raise ValueError(f"Bank import file {file.get('file_id')} row evidence is incomplete.")
        desired_batch_rows: list[dict[str, Any]] = []
        new_batch_rows: list[dict[str, Any]] = []
        owned_source_keys: set[str] = set()
        for row_no, (row_result, normalized) in enumerate(zip(row_results, normalized_rows, strict=True), start=1):
            source_key = _text(row_result.get("source_unique_key") or normalized.get("source_unique_key"))
            preview_decision = _text(row_result.get("decision"))
            if preview_decision not in {"created", "status_updated", "duplicate_skipped", "suspected_duplicate", "error"}:
                raise ValueError(f"Bank import {batch_id} row {row_no} has an unknown registered decision.")
            transaction = transactions_by_key.get(source_key)
            if preview_decision in {"created", "status_updated", "duplicate_skipped"} and transaction is None:
                raise ValueError(f"Canonical bank transaction is missing for {batch_id} row {row_no}.")
            decision = preview_decision
            if transaction is not None and preview_decision in {"created", "status_updated", "duplicate_skipped"}:
                canonical_owner = _text(transaction.get("source_batch_id"))
                if canonical_owner != batch_id or source_key in owned_source_keys:
                    decision = "duplicate_skipped"
                else:
                    owned_source_keys.add(source_key)
                    decision = "status_updated" if preview_decision == "status_updated" else "created"
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
                    _text(row_result.get("decision_reason")) if decision == preview_decision else ""
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
