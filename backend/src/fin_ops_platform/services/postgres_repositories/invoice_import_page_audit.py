from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.import_preview_audit import (
    ImportPreviewAuditRow,
    build_import_preview_session_audit,
)
from fin_ops_platform.services.import_file_service import aggregate_invoice_line_rows
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)


INVOICE_BATCH_TYPES = frozenset({"input_invoice", "output_invoice"})
ACTIVE_JOB_STATUSES = frozenset({"pending", "processing"})
ACTIVE_OUTBOX_STATUSES = frozenset({"pending", "processing", "failed", "dead_lettered"})
KNOWN_BATCH_STATUSES = frozenset({"pending", "completed", "completed_with_errors", "failed", "reverted"})
KNOWN_DECISIONS = frozenset({"created", "status_updated", "duplicate_skipped", "suspected_duplicate", "error"})
TERMINAL_BATCH_STATUSES = frozenset({"completed", "completed_with_errors"})
LINKED_TERMINAL_DECISIONS = frozenset({"created", "status_updated", "duplicate_skipped"})
IMPORT_AUDIT_CONTRACT_REVISION = "import-page-audit.v1"


def audit_invoice_import_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    normalized_tenant = str(tenant_id or "default").strip() or "default"
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        files = snapshot.connection.fetch_all(_FILE_SQL)
        batches = snapshot.connection.fetch_all(_BATCH_SQL)
        rows = snapshot.connection.fetch_all(_ROW_SQL)
        invoices = snapshot.connection.fetch_all(_INVOICE_SQL)
        jobs = snapshot.connection.fetch_all(_JOB_SQL, (normalized_tenant,))
        outbox = snapshot.connection.fetch_all(_OUTBOX_SQL, (normalized_tenant,))
        return _audit_snapshot(
            files=files,
            batches=batches,
            rows=rows,
            invoices=invoices,
            jobs=jobs,
            outbox=outbox,
            tenant_id=normalized_tenant,
            sample_limit=max(int(example_limit or 50), 1),
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_snapshot(
    *,
    files: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    outbox: list[dict[str, Any]],
    tenant_id: str,
    sample_limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    batch_ids = {_text(row.get("batch_id")) for row in batches if _text(row.get("batch_id"))}
    invoice_files = [row for row in files if _is_invoice_file(row, batch_ids=batch_ids)]
    formal_files = [
        row for row in invoice_files if _text(row.get("audit_contract_revision")) == IMPORT_AUDIT_CONTRACT_REVISION
    ]
    legacy_files = [row for row in invoice_files if row not in formal_files]
    formal_batch_ids = {
        batch_id
        for row in formal_files
        for batch_id in (_text(_payload(row).get("preview_batch_id")), _text(_payload(row).get("batch_id")))
        if batch_id
    }
    known_invoice_batch_ids = {
        _text(row.get("batch_id"))
        for row in batches
        if _text(row.get("batch_type")) in INVOICE_BATCH_TYPES and _text(row.get("batch_id"))
    }
    formal_batches = [row for row in batches if _text(row.get("batch_id")) in formal_batch_ids]
    formal_rows = [row for row in rows if _text(row.get("batch_id")) in formal_batch_ids]
    formal_invoices = [
        row
        for row in invoices
        if _text(row.get("source_batch_id")) in formal_batch_ids
        or any(
            _text(_dict(link).get("source_type")) == "manual_invoice_import"
            and _text(_dict(link).get("batch_id")) in formal_batch_ids
            for link in _list(row.get("source_links"))
        )
    ]
    invoice_file_ids = {_text(row.get("file_id")) for row in formal_files if _text(row.get("file_id"))}
    invoice_session_ids = {_text(row.get("session_id")) for row in formal_files if _text(row.get("session_id"))}
    invoice_jobs = [
        row
        for row in jobs
        if _job_session_id(row) in invoice_session_ids or bool(_job_selected_file_ids(row) & invoice_file_ids)
    ]
    invoice_job_ids = {_text(row.get("job_id")) for row in invoice_jobs if _text(row.get("job_id"))}
    invoice_outbox = [row for row in outbox if _text(row.get("aggregate_id")) in invoice_job_ids]

    issues: list[AuditIssue] = []
    issues.extend(_duplicate_issues(formal_files, "file_id", "invoice_import_file_duplicate"))
    issues.extend(_duplicate_issues(formal_batches, "batch_id", "invoice_import_batch_duplicate"))
    issues.extend(_duplicate_issues(formal_rows, "row_id", "invoice_import_row_duplicate"))
    issues.extend(_duplicate_issues(formal_invoices, "invoice_id", "invoice_import_invoice_duplicate"))
    issues.extend(_file_issues(formal_files, formal_files, formal_batches))
    issues.extend(_batch_row_issues(formal_batches, formal_rows))
    issues.extend(_session_audit_issues(formal_files, formal_rows))
    issues.extend(
        _canonical_invoice_issues(
            formal_batches,
            formal_rows,
            formal_invoices,
            known_batch_ids=known_invoice_batch_ids,
        )
    )
    issues.extend(_job_issues(invoice_jobs, formal_files, formal_files, formal_batches))
    issues.extend(_outbox_issues(invoice_outbox))
    if legacy_files:
        issues.append(
            AuditIssue(
                "warning",
                "invoice_import_legacy_provenance_unproven",
                "Pre-contract invoice import history remains readable canonical App data, but missing historical file provenance is not fabricated.",
                "legacy-invoice-import-history",
                "invoice_import",
                {"file_count": len(legacy_files)},
            )
        )
    evaluation = evaluate_audit_issues(issues, sample_limit=sample_limit)

    return {
        "mode": "invoice-import-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            "invoice_import_session_count": len(invoice_session_ids),
            "invoice_import_file_count": len(invoice_files),
            "strict_contract_file_count": len(formal_files),
            "legacy_file_count": len(legacy_files),
            "invoice_import_batch_count": len(formal_batches),
            "invoice_import_row_count": len(formal_rows),
            "invoice_import_canonical_invoice_count": len(formal_invoices),
            "invoice_import_job_count": len(invoice_jobs),
            "invoice_import_outbox_attention_count": len(invoice_outbox),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": [
                "app.import_files",
                "app.file_objects",
                "app.import_batches",
                "app.import_batch_rows",
                "app.invoices",
                "job.import_jobs",
                "job.outbox_events",
            ],
            "derived_tables": [],
            "canonical_expected_set": (
                "all version-registered input/output invoice file sessions, their preview/confirmed batches and rows, "
                "and the exact canonical invoice/manual_invoice_import source-link closure of terminal row decisions"
            ),
            "key_display_fields": [
                "session/file identity, filename, template, direction, status and registered object hash",
                "preview audit original/unique/duplicate/existing/importable/update/error/skipped counts",
                "batch type/status/counts/source/operator and every row decision/identity/reference",
                "invoice type/number/code/digital number/date/counterparty/seller/buyer/tax identity",
                "amount/tax/total/tax rate/source status and canonical identity/fingerprint",
                "manual invoice-import source-link batch/source identity and import job state",
            ],
            "relation_edge_equality": (
                "bidirectional file-session to batch, batch to row, and terminal row to canonical invoice/manual source-link "
                "edge equality; business pairing relations are downstream impacts and are not consumed by this page"
            ),
            "proof_checks": [
                "file_object_hash_registration_and_formal_payload_equality",
                "session_file_and_file_batch_bidirectional_membership",
                "preview_audit_and_batch_decision_count_recalculation",
                "terminal_row_invoice_manual_source_link_set_equality",
                "canonical_invoice_identity_and_critical_field_equality",
                "page_owned_file_import_job_and_outbox_queue_gate",
            ],
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": (
                "The App-registered file hash, size and internal import closure are proven. Tax-platform export completeness, "
                "missing invoices before upload, control totals and object-byte readability require separate external evidence."
            ),
            "downstream_impact_targets": [
                "workbench",
                "workbench_relation",
                "invoice_lifecycle",
                "pending_invoice",
                "input_invoice_usage",
                "output_invoice_collection",
                "oa_pending_payment",
                "tax_offset",
                "cost_statistics",
                "search",
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Every version-registered App invoice-import file/batch/row/invoice/source-link/job edge agrees in one snapshot. "
                "Pre-contract provenance remains explicitly unproven instead of being fabricated; downstream page projections, "
                "business pairing edges and external invoice-source completeness are not inferred."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _file_issues(
    files: list[dict[str, Any]],
    all_files: list[dict[str, Any]],
    batches: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    batch_by_id = {_text(row.get("batch_id")): row for row in batches}
    referenced_batches: dict[str, set[str]] = defaultdict(set)
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in files:
        payload = _payload(row)
        file_id = _text(row.get("file_id"))
        session_id = _text(row.get("session_id"))
        sessions[session_id].append(row)
        issues.extend(
            _compare_fields(
                subject=file_id,
                code="invoice_import_file_formal_payload_mismatch",
                structured=row,
                payload=payload,
                fields={
                    "file_id": "id",
                    "session_id": "session_id",
                    "original_filename": "file_name",
                    "stored_file_path": "stored_file_path",
                    "template_kind": "template_code",
                    "status": "status",
                },
            )
        )
        if not session_id:
            issues.append(_issue("invoice_import_file_session_missing", file_id, None))
        batch_type = _text(payload.get("batch_type") or payload.get("override_batch_type"))
        if batch_type not in INVOICE_BATCH_TYPES:
            issues.append(_issue("invoice_import_file_batch_type_invalid", file_id, {"batch_type": batch_type}))
        is_logical_manual_entry = _text(row.get("template_kind")) == "manual_invoice_entry"
        if _text(row.get("status")) != "deleted" and not is_logical_manual_entry:
            if not _text(row.get("file_object_id")):
                issues.append(_issue("invoice_import_file_object_missing", file_id, None))
            if not _text(row.get("storage_uri")) or not _text(row.get("sha256")) or row.get("size_bytes") is None:
                issues.append(_issue("invoice_import_file_hash_registration_incomplete", file_id, None))
            elif len(_text(row.get("sha256"))) != 64 or _int(row.get("size_bytes"), -1) < 0:
                issues.append(
                    _issue(
                        "invoice_import_file_hash_registration_invalid",
                        file_id,
                        {"sha256_length": len(_text(row.get("sha256"))), "size_bytes": row.get("size_bytes")},
                    )
                )
        for key in ("preview_batch_id", "batch_id"):
            batch_id = _text(payload.get(key))
            if not batch_id:
                continue
            referenced_batches[batch_id].add(file_id)
            batch = batch_by_id.get(batch_id)
            if batch is None:
                issues.append(_issue("invoice_import_file_batch_orphan", file_id, {"edge": key, "batch_id": batch_id}))
            elif _text(batch.get("batch_type")) != batch_type:
                issues.append(
                    _issue(
                        "invoice_import_file_batch_type_mismatch",
                        file_id,
                        {"file_batch_type": batch_type, "batch_type": batch.get("batch_type")},
                    )
                )
        if _text(row.get("status")) == "confirmed" and not _text(payload.get("batch_id")):
            issues.append(_issue("invoice_import_confirmed_file_batch_missing", file_id, None))

    for batch_id in sorted(batch_by_id):
        owners = referenced_batches.get(batch_id, set())
        if len(owners) != 1:
            issues.append(_issue("invoice_import_batch_file_owner_mismatch", batch_id, {"file_ids": sorted(owners)}))

    invoice_session_ids = {session_id for session_id in sessions if session_id}
    for row in all_files:
        session_id = _text(row.get("session_id"))
        if session_id not in invoice_session_ids or row in files:
            continue
        payload = _payload(row)
        other_type = _text(payload.get("batch_type") or payload.get("override_batch_type"))
        issues.append(
            _issue(
                "invoice_import_mixed_session_batch_type",
                session_id,
                {"file_id": _text(row.get("file_id")), "batch_type": other_type},
            )
        )
    return issues


def _batch_row_issues(batches: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    rows_by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        batch_id = _text(row.get("batch_id"))
        row_id = _text(row.get("row_id"))
        rows_by_batch[batch_id].append(row)
        payload = _payload(row)
        issues.extend(
            _compare_fields(
                subject=row_id,
                code="invoice_import_row_formal_payload_mismatch",
                structured=row,
                payload=payload,
                fields={
                    "row_no": "row_no",
                    "source_record_type": "source_record_type",
                    "source_unique_key": "source_unique_key",
                    "data_fingerprint": "data_fingerprint",
                    "decision": "decision",
                    "linked_object_type": "linked_object_type",
                    "linked_object_id": "linked_object_id",
                    "identity_kind": "identity_kind",
                },
            )
        )
        normalized = _normalized_row(row)
        if _text(row.get("source_unique_key")) != _text(normalized.get("source_unique_key")):
            issues.append(_issue("invoice_import_row_identity_payload_mismatch", row_id, {"field": "source_unique_key"}))
        if _text(row.get("data_fingerprint")) != _text(normalized.get("data_fingerprint")):
            issues.append(_issue("invoice_import_row_identity_payload_mismatch", row_id, {"field": "data_fingerprint"}))
        if _text(row.get("source_record_type")) != "invoice":
            issues.append(_issue("invoice_import_row_record_type_invalid", row_id, {"record_type": row.get("source_record_type")}))
        if _text(row.get("decision")) not in KNOWN_DECISIONS:
            issues.append(_issue("invoice_import_row_decision_invalid", row_id, {"decision": row.get("decision")}))
        if not batch_id:
            issues.append(_issue("invoice_import_row_batch_orphan", row_id, None))

    for batch in batches:
        batch_id = _text(batch.get("batch_id"))
        payload = _batch_payload(batch)
        batch_rows = rows_by_batch.get(batch_id, [])
        issues.extend(
            _compare_fields(
                subject=batch_id,
                code="invoice_import_batch_formal_payload_mismatch",
                structured=batch,
                payload=payload,
                fields={
                    "batch_type": "batch_type",
                    "source_name": "source_name",
                    "imported_by": "imported_by",
                    "row_count": "row_count",
                    "success_count": "success_count",
                    "error_count": "error_count",
                    "duplicate_count": "duplicate_count",
                    "suspected_duplicate_count": "suspected_duplicate_count",
                    "updated_count": "updated_count",
                    "status": "status",
                },
            )
        )
        if _text(batch.get("batch_type")) not in INVOICE_BATCH_TYPES:
            issues.append(_issue("invoice_import_batch_type_invalid", batch_id, {"batch_type": batch.get("batch_type")}))
        if _text(batch.get("status")) not in KNOWN_BATCH_STATUSES:
            issues.append(_issue("invoice_import_batch_status_invalid", batch_id, {"status": batch.get("status")}))
        counts = Counter(_text(row.get("decision")) for row in batch_rows)
        expected = {
            "row_count": len(batch_rows),
            "success_count": counts["created"] + counts["status_updated"],
            "error_count": counts["error"],
            "duplicate_count": counts["duplicate_skipped"],
            "suspected_duplicate_count": counts["suspected_duplicate"],
            "updated_count": counts["status_updated"],
        }
        actual = {key: _int(batch.get(key), -1) for key in expected}
        if actual != expected:
            issues.append(_issue("invoice_import_batch_decision_count_mismatch", batch_id, {"expected": expected, "actual": actual}))
    known_batch_ids = {_text(row.get("batch_id")) for row in batches}
    for orphan_batch_id in sorted(set(rows_by_batch) - known_batch_ids):
        issues.append(_issue("invoice_import_row_batch_orphan", orphan_batch_id, {"row_count": len(rows_by_batch[orphan_batch_id])}))
    return issues


def _session_audit_issues(files: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    files_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_by_batch: dict[str, dict[str, Any]] = {}
    for file_row in files:
        files_by_session[_text(file_row.get("session_id"))].append(file_row)
        payload = _payload(file_row)
        for key in ("preview_batch_id", "batch_id"):
            batch_id = _text(payload.get(key))
            if batch_id:
                file_by_batch[batch_id] = file_row
    rows_by_session: dict[str, list[ImportPreviewAuditRow]] = defaultdict(list)
    for row in rows:
        file_row = file_by_batch.get(_text(row.get("batch_id")))
        if file_row is None:
            continue
        rows_by_session[_text(file_row.get("session_id"))].append(
            ImportPreviewAuditRow(
                file_id=_text(file_row.get("file_id")),
                file_name=_text(file_row.get("original_filename")),
                row_no=_int(row.get("row_no"), 0),
                record_type="invoice",
                identity_key=_text(row.get("source_unique_key")) or _text(row.get("data_fingerprint")) or None,
                identity_kind=_text(row.get("identity_kind")) or None,
                decision=_text(row.get("decision")) or None,
                decision_reason=_text(row.get("decision_reason")) or None,
                linked_object_type=_text(row.get("linked_object_type")) or None,
                linked_object_id=_text(row.get("linked_object_id")) or None,
            )
        )

    for session_id, session_files in files_by_session.items():
        recalculated = build_import_preview_session_audit(rows_by_session.get(session_id, []))
        recalculated_by_file = {item.file_id: asdict(item.audit) for item in recalculated.files}
        expected_session_audit = asdict(recalculated.audit)
        registered_session_audits = [_dict(_payload(row).get("session_audit")) for row in session_files]
        if any(audit != expected_session_audit for audit in registered_session_audits):
            issues.append(_issue("invoice_import_session_audit_count_mismatch", session_id, {"expected": expected_session_audit}))
        for file_row in session_files:
            file_id = _text(file_row.get("file_id"))
            expected = recalculated_by_file.get(file_id, _zero_audit_counts())
            if _dict(_payload(file_row).get("audit")) != expected:
                issues.append(_issue("invoice_import_file_audit_count_mismatch", file_id, {"expected": expected}))
    return issues


def _canonical_invoice_issues(
    batches: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    *,
    known_batch_ids: set[str],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    batch_status = {_text(row.get("batch_id")): _text(row.get("status")) for row in batches}
    formal_batch_ids = set(batch_status)
    invoice_by_id = {_text(row.get("invoice_id")): row for row in invoices}
    expected_edges: set[tuple[str, str, str]] = set()
    expected_invoice_ids: set[str] = set()
    linked_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        batch_id = _text(row.get("batch_id"))
        if batch_status.get(batch_id) not in TERMINAL_BATCH_STATUSES:
            continue
        decision = _text(row.get("decision"))
        linked_id = _text(row.get("linked_object_id"))
        row_id = _text(row.get("row_id"))
        if decision in LINKED_TERMINAL_DECISIONS:
            invoice = invoice_by_id.get(linked_id)
            if _text(row.get("linked_object_type")) != "invoice" or invoice is None:
                issues.append(_issue("invoice_import_row_invoice_orphan", row_id, {"linked_object_id": linked_id}))
                continue
            source_id = _text(row.get("source_unique_key")) or _text(row.get("data_fingerprint"))
            if not source_id:
                issues.append(_issue("invoice_import_row_identity_missing", row_id, None))
            expected_edges.add((linked_id, batch_id, source_id))
            expected_invoice_ids.add(linked_id)
            linked_rows[(batch_id, linked_id)].append(row)
        elif linked_id or _text(row.get("linked_object_type")):
            issues.append(_issue("invoice_import_nonlinked_decision_has_invoice", row_id, {"decision": decision, "linked_object_id": linked_id}))

    for (batch_id, invoice_id), component_rows in linked_rows.items():
        issues.extend(
            _invoice_component_field_issues(
                component_rows,
                invoice_by_id[invoice_id],
                batch_type=_batch_type(batches, batch_id),
            )
        )

    actual_edges: set[tuple[str, str, str]] = set()
    for invoice in invoices:
        invoice_id = _text(invoice.get("invoice_id"))
        issues.extend(_invoice_formal_payload_issues(invoice))
        manual_batch_ids: set[str] = set()
        etc_batch_ids: set[str] = set()
        for link in _list(invoice.get("source_links")):
            source_link = _dict(link)
            source_type = _text(source_link.get("source_type"))
            if source_type == "etc_invoice_import":
                etc_batch_id = _text(source_link.get("batch_id"))
                if etc_batch_id:
                    etc_batch_ids.add(etc_batch_id)
                continue
            if source_type != "manual_invoice_import":
                continue
            batch_id = _text(source_link.get("batch_id"))
            source_id = _text(source_link.get("source_id"))
            edge = (invoice_id, batch_id, source_id)
            if not invoice_id or not batch_id or not source_id:
                issues.append(_issue("invoice_import_source_link_malformed", invoice_id, {"link": source_link}))
                continue
            if batch_id not in known_batch_ids:
                issues.append(_issue("invoice_import_source_link_batch_orphan", invoice_id, {"batch_id": batch_id}))
                continue
            if batch_id not in formal_batch_ids:
                # Pre-contract invoice provenance remains explicitly unproven, but
                # a known legacy invoice batch is not part of the strict edge set.
                manual_batch_ids.add(batch_id)
                continue
            if edge in actual_edges:
                issues.append(_issue("invoice_import_source_link_duplicate", invoice_id, {"batch_id": batch_id, "source_id": source_id}))
            actual_edges.add(edge)
            manual_batch_ids.add(batch_id)
        source_batch_id = _text(invoice.get("source_batch_id"))
        if manual_batch_ids and source_batch_id not in manual_batch_ids | etc_batch_ids:
            issues.append(
                _issue(
                    "invoice_import_source_batch_not_in_manual_links",
                    invoice_id,
                    {
                        "source_batch_id": source_batch_id,
                        "manual_batch_ids": sorted(manual_batch_ids),
                        "etc_batch_ids": sorted(etc_batch_ids),
                    },
                )
            )

    missing = expected_edges - actual_edges
    extra = actual_edges - expected_edges
    for invoice_id, batch_id, source_id in sorted(missing):
        issues.append(_issue("invoice_import_manual_source_link_missing", invoice_id, {"batch_id": batch_id, "source_id": source_id}))
    for invoice_id, batch_id, source_id in sorted(extra):
        issues.append(_issue("invoice_import_manual_source_link_orphan", invoice_id, {"batch_id": batch_id, "source_id": source_id}))
    actual_invoice_ids = {
        _text(row.get("invoice_id"))
        for row in invoices
        if _text(row.get("invoice_id"))
    }
    for invoice_id in sorted(expected_invoice_ids - actual_invoice_ids):
        issues.append(_issue("invoice_import_expected_invoice_missing", invoice_id, None))
    for invoice_id in sorted(actual_invoice_ids - expected_invoice_ids):
        issues.append(_issue("invoice_import_canonical_invoice_orphan", invoice_id, None))
    return issues


def _invoice_field_issues(row: dict[str, Any], invoice: dict[str, Any], *, batch_type: str) -> list[AuditIssue]:
    normalized = _normalized_row(row)
    invoice_payload = _payload(invoice)
    expected_type = "output" if batch_type == "output_invoice" else "input"
    expected_invoice_no = _text(normalized.get("digital_invoice_no") or normalized.get("invoice_no"))
    comparisons: dict[str, tuple[str, str]] = {
        "invoice_type": (expected_type, _text(invoice.get("invoice_type"))),
        "invoice_no": (expected_invoice_no, _text(invoice.get("invoice_no"))),
        "invoice_code": (_text(normalized.get("invoice_code")), _text(invoice.get("invoice_code"))),
        "digital_invoice_no": (_text(normalized.get("digital_invoice_no")), _text(invoice.get("digital_invoice_no"))),
        "invoice_date": (_date_text(normalized.get("invoice_date")), _date_text(invoice.get("invoice_date"))),
        "counterparty_name": (_text(normalized.get("counterparty_name")), _text(invoice.get("counterparty_name"))),
        "seller_name": (_text(normalized.get("seller_name")), _text(invoice.get("seller_name"))),
        "seller_tax_no": (_text(normalized.get("seller_tax_no")), _text(invoice.get("seller_tax_no"))),
        "buyer_name": (_text(normalized.get("buyer_name")), _text(invoice.get("buyer_name"))),
        "buyer_tax_no": (_text(normalized.get("buyer_tax_no")), _text(invoice.get("buyer_tax_no"))),
        "amount": (_decimal_text(normalized.get("amount")), _decimal_text(invoice.get("amount"))),
        "tax_amount": (_decimal_text(normalized.get("tax_amount")), _decimal_text(invoice.get("tax_amount"))),
        "total_with_tax": (_decimal_text(normalized.get("total_with_tax")), _decimal_text(invoice.get("total_with_tax"))),
        "tax_rate": (_tax_rate_text(normalized.get("tax_rate")), _tax_rate_text(invoice.get("tax_rate"))),
        "invoice_status_from_source": (
            _text(normalized.get("invoice_status_from_source")),
            _text(invoice_payload.get("invoice_status_from_source")),
        ),
        "source_unique_key": (_text(row.get("source_unique_key")), _text(invoice.get("source_unique_key"))),
    }
    if not _text(row.get("source_unique_key")):
        comparisons["data_fingerprint"] = (_text(row.get("data_fingerprint")), _text(invoice.get("data_fingerprint")))
    mismatches = {
        key: {"row": left, "invoice": right}
        for key, (left, right) in comparisons.items()
        if left and left != right
    }
    if _text(row.get("source_unique_key")) and _text(invoice.get("data_fingerprint")):
        mismatches["data_fingerprint"] = {"row": "canonical_identity_present", "invoice": invoice.get("data_fingerprint")}
    return [_issue("invoice_import_invoice_field_mismatch", _text(row.get("row_id")), {"fields": mismatches})] if mismatches else []


def _invoice_component_field_issues(
    rows: list[dict[str, Any]],
    invoice: dict[str, Any],
    *,
    batch_type: str,
) -> list[AuditIssue]:
    if len(rows) == 1:
        return _invoice_field_issues(rows[0], invoice, batch_type=batch_type)
    normalized_rows = [_normalized_row(row) for row in rows]
    try:
        aggregated_rows = aggregate_invoice_line_rows(normalized_rows)
    except ValueError as exc:
        return [
            _issue(
                "invoice_import_component_field_conflict",
                _text(invoice.get("invoice_id")),
                {"reason": str(exc)},
            )
        ]
    if len(aggregated_rows) != 1:
        return _invoice_field_issues(rows[0], invoice, batch_type=batch_type)
    aggregate = dict(aggregated_rows[0])
    aggregate["signed_amount"] = str(
        sum((Decimal(_decimal_text(row.get("signed_amount")) or "0") for row in normalized_rows), Decimal("0"))
    )
    synthetic = dict(rows[0])
    synthetic["row_id"] = f"{_text(rows[0].get('batch_id'))}:{_text(invoice.get('invoice_id'))}"
    synthetic["raw_payload"] = {"normalized_payload": {"normalized_row": aggregate}}
    return _invoice_field_issues(synthetic, invoice, batch_type=batch_type)


def _invoice_formal_payload_issues(invoice: dict[str, Any]) -> list[AuditIssue]:
    payload = dict(_payload(invoice))
    if not _text(payload.get("counterparty_name")):
        payload["counterparty_name"] = _text(_dict(payload.get("counterparty")).get("name"))
    issues = _compare_fields(
        subject=_text(invoice.get("invoice_id")),
        code="invoice_import_invoice_formal_payload_mismatch",
        structured=invoice,
        payload=payload,
        fields={
            "invoice_type": "invoice_type",
            "invoice_no": "invoice_no",
            "invoice_code": "invoice_code",
            "digital_invoice_no": "digital_invoice_no",
            "invoice_date": "invoice_date",
            "counterparty_name": "counterparty_name",
            "seller_name": "seller_name",
            "seller_tax_no": "seller_tax_no",
            "buyer_name": "buyer_name",
            "buyer_tax_no": "buyer_tax_no",
            "amount": "amount",
            "tax_rate": "tax_rate",
            "tax_amount": "tax_amount",
            "total_with_tax": "total_with_tax",
            "source_unique_key": "source_unique_key",
            "data_fingerprint": "data_fingerprint",
        },
    )
    if _list(invoice.get("source_links")) != _list(payload.get("source_links")):
        issues.append(
            _issue(
                "invoice_import_invoice_formal_payload_mismatch",
                _text(invoice.get("invoice_id")),
                {"fields": {"source_links": {"structured": invoice.get("source_links"), "payload": payload.get("source_links")}}},
            )
        )
    return issues


def _job_issues(
    jobs: list[dict[str, Any]],
    invoice_files: list[dict[str, Any]],
    all_files: list[dict[str, Any]],
    batches: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    invoice_file_ids = {_text(row.get("file_id")) for row in invoice_files}
    all_file_ids = {_text(row.get("file_id")) for row in all_files}
    invoice_sessions = {_text(row.get("session_id")) for row in invoice_files}
    batch_ids = {_text(row.get("batch_id")) for row in batches}
    file_by_id = {_text(row.get("file_id")): row for row in invoice_files}
    for row in jobs:
        job_id = _text(row.get("job_id"))
        status = _text(row.get("status"))
        session_id = _job_session_id(row)
        selected_file_ids = _job_selected_file_ids(row)
        if session_id not in invoice_sessions:
            issues.append(_issue("invoice_import_job_session_orphan", job_id, {"session_id": session_id}))
        if selected_file_ids - all_file_ids:
            issues.append(_issue("invoice_import_job_file_orphan", job_id, {"file_ids": sorted(selected_file_ids - all_file_ids)}))
        if selected_file_ids - invoice_file_ids:
            issues.append(_issue("invoice_import_job_mixed_file_types", job_id, {"file_ids": sorted(selected_file_ids - invoice_file_ids)}))
        if not selected_file_ids:
            issues.append(_issue("invoice_import_job_selected_files_missing", job_id, None))
        if status in ACTIVE_JOB_STATUSES or (status == "failed" and _int(row.get("attempt_count"), 0) < _int(row.get("max_attempts"), 1)):
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "发票导入任务尚未排空。",
                    job_id,
                    "file_import.confirm",
                    {"status": status, "stage": row.get("stage")},
                )
            )
        elif status == "failed":
            issues.append(_issue("invoice_import_job_terminal_failure", job_id, {"last_error": row.get("last_error")}))
        if status == "succeeded":
            expected_batch_ids = {
                _text(_payload(file_by_id[file_id]).get("batch_id"))
                for file_id in selected_file_ids & invoice_file_ids
                if _text(_payload(file_by_id[file_id]).get("batch_id"))
            }
            if expected_batch_ids - batch_ids:
                issues.append(_issue("invoice_import_job_confirmed_batch_orphan", job_id, {"batch_ids": sorted(expected_batch_ids - batch_ids)}))
            for file_id in selected_file_ids & invoice_file_ids:
                file_payload = _payload(file_by_id[file_id])
                if _text(file_by_id[file_id].get("status")) != "confirmed" or not _text(file_payload.get("batch_id")):
                    issues.append(_issue("invoice_import_job_succeeded_file_not_confirmed", job_id, {"file_id": file_id}))
    return issues


def _outbox_issues(rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in rows:
        status = _text(row.get("status"))
        if status not in ACTIVE_OUTBOX_STATUSES:
            continue
        event_id = _text(row.get("event_id"))
        issues.append(
            AuditIssue(
                "error",
                "page_runtime_queue_not_drained",
                "发票导入 outbox 尚未排空。",
                event_id,
                "import.process.requested",
                {"status": status, "last_error": row.get("last_error")},
            )
        )
        if status in {"failed", "dead_lettered"}:
            issues.append(_issue("invoice_import_outbox_terminal_failure", event_id, {"status": status}))
    return issues


def _job_session_id(row: dict[str, Any]) -> str:
    return _text(row.get("import_session_id")) or _text(_dict(row.get("payload")).get("session_id"))


def _job_selected_file_ids(row: dict[str, Any]) -> set[str]:
    return {_text(value) for value in _list(_dict(row.get("payload")).get("selected_file_ids")) if _text(value)}


def _is_invoice_file(row: dict[str, Any], *, batch_ids: set[str]) -> bool:
    payload = _payload(row)
    batch_type = _text(payload.get("batch_type") or payload.get("override_batch_type"))
    referenced = {_text(payload.get("preview_batch_id")), _text(payload.get("batch_id"))}
    return batch_type in INVOICE_BATCH_TYPES or bool((referenced - {""}) & batch_ids)


def _batch_type(batches: list[dict[str, Any]], batch_id: str) -> str:
    return next((_text(row.get("batch_type")) for row in batches if _text(row.get("batch_id")) == batch_id), "")


def _compare_fields(
    *,
    subject: str,
    code: str,
    structured: dict[str, Any],
    payload: dict[str, Any],
    fields: dict[str, str],
) -> list[AuditIssue]:
    mismatches: dict[str, dict[str, Any]] = {}
    for structured_key, payload_key in fields.items():
        if structured_key in {"amount", "tax_amount", "total_with_tax"}:
            left = _decimal_text(structured.get(structured_key))
            right = _decimal_text(payload.get(payload_key))
        elif structured_key.endswith("_date"):
            left = _date_text(structured.get(structured_key))
            right = _date_text(payload.get(payload_key))
        else:
            left = _comparable(structured.get(structured_key))
            right = _comparable(payload.get(payload_key))
        if left != right:
            mismatches[structured_key] = {"structured": left, "payload": right}
    return [_issue(code, subject, {"fields": mismatches})] if mismatches else []


def _duplicate_issues(rows: list[dict[str, Any]], key: str, code: str) -> list[AuditIssue]:
    counts = Counter(_text(row.get(key)) for row in rows)
    return [_issue(code, subject or key, {"count": count}) for subject, count in counts.items() if not subject or count != 1]


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = _dict(row.get("raw_payload"))
    return _dict(raw.get("normalized_payload")) or raw


def _batch_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(row)
    return _dict(payload.get("batch")) or payload


def _normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(_payload(row).get("normalized_row"))


def _zero_audit_counts() -> dict[str, int]:
    return {
        "original_count": 0,
        "unique_count": 0,
        "duplicate_count": 0,
        "duplicate_in_file_count": 0,
        "duplicate_across_files_count": 0,
        "existing_duplicate_count": 0,
        "importable_count": 0,
        "update_count": 0,
        "merge_count": 0,
        "suspected_duplicate_count": 0,
        "error_count": 0,
        "confirmable_count": 0,
        "skipped_count": 0,
    }


def _issue(code: str, subject_id: str, details: dict[str, Any] | None) -> AuditIssue:
    return AuditIssue(
        "error",
        code,
        "发票导入 canonical facts、集合、字段、source link、引用或任务状态不一致。",
        subject_id,
        "invoice_import",
        details,
    )


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decimal_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return _text(value)


def _tax_rate_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = Decimal(text[:-1]) / Decimal("100") if text.endswith("%") else Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return text
    return format(number.normalize(), "f")


def _date_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return _text(value)[:10]


def _comparable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, (datetime, date)):
        return _date_text(value)
    return value


_FILE_SQL = """
select coalesce(f.legacy_mongo_id, f.id::text) as file_id,
       f.session_id, f.audit_contract_revision, f.file_object_id::text, f.stored_file_path, f.original_filename,
       f.template_kind, f.status, f.uploaded_by, f.uploaded_at, f.raw_payload,
       o.storage_backend, o.storage_uri, o.bucket_name, o.object_key, o.filename as object_filename,
       o.sha256, o.size_bytes, o.content_type
from app.import_files f
left join app.file_objects o on o.id = f.file_object_id
order by f.session_id, f.uploaded_at, file_id
"""
_BATCH_SQL = """
select coalesce(legacy_mongo_id, id::text) as batch_id,
       batch_type, source_name, imported_by, row_count, success_count, error_count,
       duplicate_count, suspected_duplicate_count, updated_count, status, imported_at, raw_payload
from app.import_batches
where batch_type in ('input_invoice', 'output_invoice')
order by imported_at, batch_id
"""
_ROW_SQL = """
select coalesce(r.legacy_mongo_id, r.id::text) as row_id,
       coalesce(b.legacy_mongo_id, b.id::text, r.legacy_batch_id) as batch_id,
       r.row_no, r.source_record_type, r.source_unique_key, r.data_fingerprint,
       r.decision, r.decision_reason, r.linked_object_type, r.linked_object_id,
       r.identity_kind, r.raw_payload
from app.import_batch_rows r
join app.import_batches b on b.id = r.import_batch_id
where b.batch_type in ('input_invoice', 'output_invoice')
order by batch_id, r.row_no, row_id
"""
_INVOICE_SQL = """
select coalesce(i.legacy_mongo_id, i.id::text) as invoice_id,
       i.invoice_type, i.invoice_no, i.invoice_code, i.digital_invoice_no,
       i.source_unique_key, i.data_fingerprint, i.invoice_date,
       i.counterparty_name, i.seller_name, i.seller_tax_no, i.buyer_name, i.buyer_tax_no,
       i.amount, i.signed_amount, i.tax_rate, i.tax_amount, i.total_with_tax,
       coalesce(b.legacy_mongo_id, b.id::text, i.legacy_source_batch_id) as source_batch_id,
       i.status, i.tags, i.source_links, i.raw_payload
from app.invoices i
left join app.import_batches b on b.id = i.source_batch_id
where b.batch_type in ('input_invoice', 'output_invoice')
   or exists (
       select 1
       from jsonb_array_elements(coalesce(i.source_links, '[]'::jsonb)) link
       where link->>'source_type' = 'manual_invoice_import'
   )
order by invoice_id
"""
_JOB_SQL = """
select id::text as job_id, import_session_id, source_file_id, status, stage,
       attempt_count, max_attempts, last_error, payload, result_payload
from job.import_jobs
where tenant_id = %s and import_type = 'file_import.confirm'
order by created_at, id
"""
_OUTBOX_SQL = """
select id::text as event_id, aggregate_id, status, last_error, payload
from job.outbox_events
where tenant_id = %s
  and event_type = 'import.process.requested'
  and status in ('pending', 'processing', 'failed', 'dead_lettered')
order by created_at, id
"""
