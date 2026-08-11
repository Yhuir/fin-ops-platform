from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
import unicodedata
from zoneinfo import ZoneInfo

from fin_ops_platform.services.bank_transaction_identity_service import (
    BankTransactionIdentityService,
)
from fin_ops_platform.services.import_preview_audit import (
    CONTROLLED_DUPLICATE_PROVENANCE_REASONS,
    ImportPreviewAuditRow,
    build_import_preview_session_audit,
)
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)


ACTIVE_JOB_STATUSES = frozenset({"pending", "processing"})
ACTIVE_OUTBOX_STATUSES = frozenset({"pending", "processing", "failed", "dead_lettered"})
KNOWN_BATCH_STATUSES = frozenset({"pending", "completed", "completed_with_errors", "failed"})
KNOWN_DECISIONS = frozenset({"created", "status_updated", "duplicate_skipped", "suspected_duplicate", "error"})
TERMINAL_BATCH_STATUSES = frozenset({"completed", "completed_with_errors"})
IMPORT_AUDIT_CONTRACT_REVISION = "import-page-audit.v1"
BANK_IMPORT_LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


def audit_bank_transaction_import_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    normalized_tenant = str(tenant_id or "default").strip() or "default"
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        files = snapshot.connection.fetch_all(BANK_IMPORT_FILE_SQL)
        batches = snapshot.connection.fetch_all(BANK_IMPORT_BATCH_SQL)
        rows = snapshot.connection.fetch_all(BANK_IMPORT_ROW_SQL)
        transactions = snapshot.connection.fetch_all(_TRANSACTION_SQL)
        jobs = snapshot.connection.fetch_all(_JOB_SQL, (normalized_tenant,))
        outbox = snapshot.connection.fetch_all(_OUTBOX_SQL, (normalized_tenant,))
        return _audit_snapshot(
            files=files,
            batches=batches,
            rows=rows,
            transactions=transactions,
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
    transactions: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    outbox: list[dict[str, Any]],
    tenant_id: str,
    sample_limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    bank_files = bank_import_files(files, batches=batches)
    formal_files = formal_bank_import_files(files, batches=batches)
    legacy_files = [row for row in bank_files if row not in formal_files]
    formal_batch_ids = {
        batch_id
        for row in formal_files
        for batch_id in (_text(_payload(row).get("preview_batch_id")), _text(_payload(row).get("batch_id")))
        if batch_id
    }
    formal_batches = [row for row in batches if _text(row.get("batch_id")) in formal_batch_ids]
    formal_rows = [row for row in rows if _text(row.get("batch_id")) in formal_batch_ids]
    referenced_transaction_ids = {
        _text(row.get("linked_object_id"))
        for row in formal_rows
        if _text(row.get("linked_object_type")) == "bank_transaction"
        and _text(row.get("linked_object_id"))
    }
    formal_transactions = [
        row
        for row in transactions
        if _text(row.get("batch_id")) in formal_batch_ids
        or _text(row.get("transaction_id")) in referenced_transaction_ids
    ]
    owned_transactions = [row for row in formal_transactions if _text(row.get("batch_id")) in formal_batch_ids]
    bank_file_ids = {_text(row.get("file_id")) for row in formal_files if _text(row.get("file_id"))}
    bank_session_ids = {_text(row.get("session_id")) for row in formal_files if _text(row.get("session_id"))}
    bank_jobs = [
        row
        for row in jobs
        if _job_session_id(row) in bank_session_ids or bool(_job_selected_file_ids(row) & bank_file_ids)
    ]
    bank_job_ids = {_text(row.get("job_id")) for row in bank_jobs}
    bank_outbox = [row for row in outbox if _text(row.get("aggregate_id")) in bank_job_ids]

    issues: list[AuditIssue] = []
    issues.extend(_duplicate_issues(formal_files, "file_id", "bank_import_file_duplicate"))
    issues.extend(_duplicate_issues(formal_batches, "batch_id", "bank_import_batch_duplicate"))
    issues.extend(_duplicate_issues(formal_rows, "row_id", "bank_import_row_duplicate"))
    issues.extend(_duplicate_issues(formal_transactions, "transaction_id", "bank_import_transaction_duplicate"))
    issues.extend(_file_issues(formal_files, formal_files, formal_batches))
    issues.extend(_batch_row_issues(formal_batches, formal_rows))
    issues.extend(_session_audit_issues(formal_files, formal_rows))
    issues.extend(_canonical_transaction_issues(formal_batches, formal_rows, formal_transactions))
    issues.extend(_job_issues(bank_jobs, formal_files, formal_batches))
    issues.extend(_outbox_issues(bank_outbox))
    if legacy_files:
        issues.append(
            AuditIssue(
                "warning",
                "bank_import_legacy_provenance_unproven",
                "Pre-contract bank import history remains readable canonical App data, but missing historical file provenance is not fabricated.",
                "legacy-bank-import-history",
                "bank_transaction_import",
                {"file_count": len(legacy_files)},
            )
        )
    evaluation = evaluate_audit_issues(issues, sample_limit=sample_limit)

    return {
        "mode": "bank-transaction-import-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            "bank_import_session_count": len(bank_session_ids),
            "bank_import_file_count": len(bank_files),
            "strict_contract_file_count": len(formal_files),
            "legacy_file_count": len(legacy_files),
            "bank_import_batch_count": len(formal_batches),
            "bank_import_row_count": len(formal_rows),
            "bank_import_owned_transaction_count": len(owned_transactions),
            "bank_import_referenced_transaction_count": len(formal_transactions),
            "bank_import_job_count": len(bank_jobs),
            "bank_import_outbox_attention_count": len(bank_outbox),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": [
                "app.import_files",
                "app.file_objects",
                "app.import_batches",
                "app.import_batch_rows",
                "app.bank_transactions",
                "job.import_jobs",
                "job.outbox_events",
            ],
            "read_model_tables": [],
            "canonical_expected_set": (
                "all version-registered bank-transaction file sessions and their preview/confirmed batches and rows, "
                "plus every canonical bank transaction owned or referenced by those decisions"
            ),
            "key_display_fields": [
                "session/file identity, filename, template, status and bank mapping selection",
                "preview audit original/unique/duplicate/existing/importable/error/skipped counts",
                "batch type/status/counts/source/operator",
                "row decision, identity/fingerprint, account/time/direction/amount/counterparty",
                "canonical bank transaction ownership and matching identity fields",
                "import job stage/status/attempt/result references",
            ],
            "relation_edge_equality": (
                "bidirectional file-session to preview/confirmed batch, batch to row, and completed row decision "
                "to canonical bank-transaction ownership/reference equality; pairing relation is not consumed by this page"
            ),
            "proof_checks": [
                "file_object_hash_registration_and_formal_payload_equality",
                "session_file_and_file_batch_bidirectional_membership",
                "preview_audit_count_recalculation_from_registered_rows",
                "batch_structured_payload_and_decision_count_recalculation",
                "created_and_duplicate_decision_to_canonical_transaction_equality",
                "canonical_transaction_identity_field_and_source_batch_equality",
                "file_import_job_result_and_outbox_queue_gate",
            ],
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": (
                "The App-registered original file hash and size are proven. Bank statement control totals, "
                "page/row completeness before upload, and object bytes readability require separate external evidence."
            ),
            "downstream_impact_targets": [
                "workbench",
                "workbench_relation",
                "pending_invoice",
                "oa_pending_payment",
                "cost_statistics",
                "search",
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Every version-registered App bank-import session/file/batch/row/transaction/job edge agrees in one snapshot. "
                "Pre-contract provenance remains explicitly unproven instead of being fabricated; downstream page projections "
                "and external bank statement completeness are not inferred."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def bank_import_files(
    files: list[dict[str, Any]],
    *,
    batches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    batch_ids = {
        _text(row.get("batch_id")) for row in batches if _text(row.get("batch_id"))
    }
    return [row for row in files if _is_bank_file(row, batch_ids=batch_ids)]


def formal_bank_import_files(
    files: list[dict[str, Any]],
    *,
    batches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in bank_import_files(files, batches=batches)
        if _text(row.get("audit_contract_revision"))
        == IMPORT_AUDIT_CONTRACT_REVISION
    ]


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
                code="bank_import_file_formal_payload_mismatch",
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
            issues.append(_issue("bank_import_file_session_missing", file_id, None))
        if _text(row.get("status")) != "deleted":
            if not _text(row.get("file_object_id")):
                issues.append(_issue("bank_import_file_object_missing", file_id, None))
            if not _text(row.get("storage_uri")) or not _text(row.get("sha256")) or row.get("size_bytes") is None:
                issues.append(_issue("bank_import_file_hash_registration_incomplete", file_id, None))
            elif len(_text(row.get("sha256"))) != 64 or _int(row.get("size_bytes"), -1) < 0:
                issues.append(
                    _issue(
                        "bank_import_file_hash_registration_invalid",
                        file_id,
                        {"sha256_length": len(_text(row.get("sha256"))), "size_bytes": row.get("size_bytes")},
                    )
                )
        for key in ("preview_batch_id", "batch_id"):
            batch_id = _text(payload.get(key))
            if not batch_id:
                continue
            referenced_batches[batch_id].add(file_id)
            if batch_id not in batch_by_id:
                issues.append(_issue("bank_import_file_batch_orphan", file_id, {"edge": key, "batch_id": batch_id}))
        if _text(row.get("status")) == "confirmed" and not _text(payload.get("batch_id")):
            issues.append(_issue("bank_import_confirmed_file_batch_missing", file_id, None))

    for session_id, session_files in sessions.items():
        expected_count = len(session_files)
        registered_counts = {_int(_payload(row).get("file_count"), expected_count) for row in session_files}
        if registered_counts != {expected_count}:
            issues.append(
                _issue(
                    "bank_import_session_file_count_mismatch",
                    session_id,
                    {"expected": expected_count, "registered": sorted(registered_counts)},
                )
            )
    for batch_id in batch_by_id:
        if len(referenced_batches[batch_id]) != 1:
            issues.append(
                _issue(
                    "bank_import_batch_file_owner_mismatch",
                    batch_id,
                    {"file_reference_count": len(referenced_batches[batch_id])},
                )
            )
    bank_session_ids = {session_id for session_id in sessions if session_id}
    for row in all_files:
        session_id = _text(row.get("session_id"))
        if session_id not in bank_session_ids or row in files:
            continue
        payload = _payload(row)
        issues.append(
            _issue(
                "bank_import_mixed_session_batch_type",
                session_id,
                {
                    "file_id": _text(row.get("file_id")),
                    "batch_type": _text(payload.get("batch_type") or payload.get("override_batch_type")),
                },
            )
        )
    return issues


def _batch_row_issues(batches: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    rows_by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_batch[_text(row.get("batch_id"))].append(row)
        payload = _payload(row)
        row_id = _text(row.get("row_id"))
        issues.extend(
            _compare_fields(
                subject=row_id,
                code="bank_import_row_formal_payload_mismatch",
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
                    "account_no": "account_no",
                    "trade_time": "trade_time",
                    "direction": "direction",
                    "amount": "amount",
                    "counterparty_name": "counterparty_name",
                },
            )
        )
        if _text(row.get("decision")) not in KNOWN_DECISIONS:
            issues.append(_issue("bank_import_row_decision_invalid", row_id, {"decision": row.get("decision")}))
        if not _text(row.get("batch_id")):
            issues.append(_issue("bank_import_row_batch_orphan", row_id, None))

    for batch in batches:
        batch_id = _text(batch.get("batch_id"))
        payload = _batch_payload(batch)
        batch_rows = rows_by_batch.get(batch_id, [])
        issues.extend(
            _compare_fields(
                subject=batch_id,
                code="bank_import_batch_formal_payload_mismatch",
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
        status = _text(batch.get("status"))
        if status not in KNOWN_BATCH_STATUSES:
            issues.append(_issue("bank_import_batch_status_invalid", batch_id, {"status": status}))
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
            issues.append(_issue("bank_import_batch_decision_count_mismatch", batch_id, {"expected": expected, "actual": actual}))
    known_batch_ids = {_text(row.get("batch_id")) for row in batches}
    for orphan_batch_id in sorted(set(rows_by_batch) - known_batch_ids):
        issues.append(_issue("bank_import_row_batch_orphan", orphan_batch_id, {"row_count": len(rows_by_batch[orphan_batch_id])}))
    return issues


def _session_audit_issues(files: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[AuditIssue]:
    expectations = bank_import_audit_count_expectations(files, rows)
    issues: list[AuditIssue] = []
    for file_row in files:
        if _text(_payload(file_row).get("batch_type")) not in {
            "",
            "bank_transaction",
        }:
            issues.append(
                _issue(
                    "bank_import_mixed_session_batch_type",
                    _text(file_row.get("session_id")),
                    None,
                )
            )
    for session_id, session_files in expectations["session_files"].items():
        expected_session_audit = expectations["sessions"][session_id]
        registered_session_audits = [
            _dict(_payload(row).get("session_audit")) for row in session_files
        ]
        if any(audit != expected_session_audit for audit in registered_session_audits):
            issues.append(
                _issue(
                    "bank_import_session_audit_count_mismatch",
                    session_id,
                    {"expected": expected_session_audit},
                )
            )
        for file_row in session_files:
            file_id = _text(file_row.get("file_id"))
            registered = _dict(_payload(file_row).get("audit"))
            expected = expectations["files"][file_id]
            if registered != expected:
                issues.append(
                    _issue(
                        "bank_import_file_audit_count_mismatch",
                        file_id,
                        {"expected": expected},
                    )
                )
    return issues


def bank_import_audit_count_expectations(
    files: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
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
                record_type=_text(row.get("source_record_type")) or "bank_transaction",
                identity_key=_text(row.get("source_unique_key")) or _text(row.get("data_fingerprint")) or None,
                identity_kind=_text(row.get("identity_kind")) or None,
                decision=_text(row.get("decision")) or None,
                decision_reason=_text(row.get("decision_reason")) or None,
                linked_object_type=_text(row.get("linked_object_type")) or None,
                linked_object_id=_text(row.get("linked_object_id")) or None,
                account_no=_text(row.get("account_no")) or None,
                trade_time=_text(row.get("trade_time")) or None,
                direction=_text(row.get("direction")) or None,
                amount=_decimal_text(row.get("amount")) or None,
                counterparty_name=_text(row.get("counterparty_name")) or None,
            )
        )
    session_expectations: dict[str, dict[str, int]] = {}
    file_expectations: dict[str, dict[str, int]] = {}
    for session_id, session_files in files_by_session.items():
        recalculated = build_import_preview_session_audit(rows_by_session.get(session_id, []))
        recalculated_by_file = {item.file_id: asdict(item.audit) for item in recalculated.files}
        session_expectations[session_id] = asdict(recalculated.audit)
        for file_row in session_files:
            file_id = _text(file_row.get("file_id"))
            file_expectations[file_id] = recalculated_by_file.get(
                file_id,
                _zero_audit_counts(),
            )
    return {
        "sessions": session_expectations,
        "files": file_expectations,
        "session_files": files_by_session,
    }


def _canonical_transaction_issues(
    batches: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    batch_status = {_text(row.get("batch_id")): _text(row.get("status")) for row in batches}
    batch_ids = set(batch_status)
    transaction_by_id = {_text(row.get("transaction_id")): row for row in transactions}
    created_owner_counts: Counter[str] = Counter()
    for row in rows:
        batch_id = _text(row.get("batch_id"))
        if batch_status.get(batch_id) not in TERMINAL_BATCH_STATUSES:
            continue
        decision = _text(row.get("decision"))
        linked_id = _text(row.get("linked_object_id"))
        row_id = _text(row.get("row_id"))
        if decision in {"created", "duplicate_skipped"}:
            transaction = transaction_by_id.get(linked_id)
            if _text(row.get("linked_object_type")) != "bank_transaction" or transaction is None:
                issues.append(_issue("bank_import_row_transaction_orphan", row_id, {"linked_object_id": linked_id}))
                continue
            if decision == "created":
                created_owner_counts[linked_id] += 1
                if _text(transaction.get("batch_id")) != batch_id:
                    issues.append(
                        _issue(
                            "bank_import_created_transaction_batch_mismatch",
                            row_id,
                            {"row_batch_id": batch_id, "transaction_batch_id": transaction.get("batch_id")},
                        )
                    )
            issues.extend(_transaction_field_issues(row, transaction))
        elif linked_id:
            issues.append(_issue("bank_import_nonlinked_decision_has_transaction", row_id, {"decision": decision, "linked_object_id": linked_id}))

    for transaction in transactions:
        if _text(transaction.get("batch_id")) not in batch_ids:
            continue
        transaction_id = _text(transaction.get("transaction_id"))
        if created_owner_counts[transaction_id] != 1:
            issues.append(
                _issue(
                    "bank_import_transaction_created_owner_mismatch",
                    transaction_id,
                    {"created_row_count": created_owner_counts[transaction_id]},
                )
            )
    return issues


def _transaction_field_issues(row: dict[str, Any], transaction: dict[str, Any]) -> list[AuditIssue]:
    row_id = _text(row.get("row_id"))
    comparisons = {
        "account_no": (_text(row.get("account_no")), _text(transaction.get("account_no"))),
        "trade_time": (_time_text(row.get("trade_time")), _time_text(transaction.get("trade_time"))),
        "direction": (_text(row.get("direction")), _text(transaction.get("txn_direction"))),
        "amount": (_decimal_text(row.get("amount")), _decimal_text(transaction.get("amount"))),
        "counterparty_name": (
            _text(row.get("counterparty_name")),
            _text(transaction.get("counterparty_name_raw")),
        ),
    }
    identity_matches = _identity_matches(row, transaction)
    controlled_replay_matches = _controlled_replay_statement_position_matches(
        row,
        transaction,
    )
    if not identity_matches and not controlled_replay_matches:
        comparisons.update(
            {
                "source_unique_key": (
                    _text(row.get("source_unique_key")),
                    _text(transaction.get("source_unique_key")),
                ),
                "data_fingerprint": (
                    _text(row.get("data_fingerprint")),
                    _text(transaction.get("data_fingerprint")),
                ),
            }
        )
    mismatches = {key: {"row": left, "transaction": right} for key, (left, right) in comparisons.items() if left != right}
    if not mismatches:
        return []
    details: dict[str, Any] = {"fields": mismatches}
    controlled_replay_diagnostics = _controlled_replay_statement_position_diagnostics(
        row,
        transaction,
    )
    if controlled_replay_diagnostics is not None:
        details["controlled_replay_statement_position"] = controlled_replay_diagnostics
    return [_issue("bank_import_transaction_field_mismatch", row_id, details)]


def _controlled_replay_statement_position_matches(
    row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    diagnostics = _controlled_replay_statement_position_diagnostics(row, transaction)
    return diagnostics is not None and not diagnostics["mismatch_fields"]


def _controlled_replay_statement_position_diagnostics(
    row: dict[str, Any],
    transaction: dict[str, Any],
) -> dict[str, Any] | None:
    decision = _text(row.get("decision"))
    if decision != "duplicate_skipped":
        return None
    decision_reason = _text(row.get("decision_reason"))
    if decision_reason not in CONTROLLED_DUPLICATE_PROVENANCE_REASONS:
        return {
            "eligible": False,
            "decision": decision,
            "decision_reason": decision_reason or "missing",
            "row_position_complete": False,
            "transaction_position_complete": False,
            "mismatch_fields": ["unregistered_decision_reason"],
        }
    identity_service = BankTransactionIdentityService()
    row_position = identity_service.statement_position_for_mapping(
        _bank_statement_mapping(row, direction_key="direction"),
        allow_missing_currency=True,
    )
    transaction_position = identity_service.statement_position_for_mapping(
        _bank_statement_mapping(transaction, direction_key="txn_direction"),
        allow_missing_currency=True,
    )
    if row_position is None or transaction_position is None:
        return {
            "eligible": True,
            "row_position_complete": row_position is not None,
            "transaction_position_complete": transaction_position is not None,
            "mismatch_fields": ["incomplete_statement_position"],
        }
    field_names = ("account_no", "trade_time", "direction", "amount", "balance")
    mismatch_fields = [
        field_name
        for field_name, row_value, transaction_value in zip(
            field_names,
            row_position[:5],
            transaction_position[:5],
            strict=True,
        )
        if row_value != transaction_value
    ]
    row_currency = row_position[5]
    transaction_currency = transaction_position[5]
    if not (
        row_currency == transaction_currency
        or (row_currency == "CNY" and transaction_currency == "")
    ):
        mismatch_fields.append("currency")
    return {
        "eligible": True,
        "row_position_complete": True,
        "transaction_position_complete": True,
        "mismatch_fields": mismatch_fields,
        "row_currency": row_currency or "missing",
        "transaction_currency": transaction_currency or "missing",
    }


def _bank_statement_mapping(row: dict[str, Any], *, direction_key: str) -> dict[str, Any]:
    payload = _payload(row)
    normalized_row = _dict(payload.get("normalized_row"))
    merged = {**payload, **normalized_row}
    return {
        **merged,
        "account_no": row.get("account_no") or merged.get("account_no"),
        "trade_time": _statement_position_time(
            row.get("trade_time") or merged.get("trade_time")
        ),
        "txn_direction": row.get(direction_key) or merged.get("txn_direction") or merged.get("direction"),
        "amount": row.get("amount") if row.get("amount") is not None else merged.get("amount"),
        "counterparty_name": (
            row.get("counterparty_name")
            or row.get("counterparty_name_raw")
            or merged.get("counterparty_name")
            or merged.get("counterparty_name_raw")
        ),
        "balance": row.get("balance") if row.get("balance") is not None else merged.get("balance"),
        "currency": row.get("currency") or merged.get("currency"),
    }


def _statement_position_time(value: Any) -> Any:
    if value in (None, ""):
        return value
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BANK_IMPORT_LOCAL_TIMEZONE)
    return parsed.astimezone(BANK_IMPORT_LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _identity_matches(row: dict[str, Any], transaction: dict[str, Any]) -> bool:
    row_source_key = _text(row.get("source_unique_key"))
    row_fingerprint = _text(row.get("data_fingerprint"))
    transaction_source_key = _text(transaction.get("source_unique_key"))
    transaction_fingerprint = _text(transaction.get("data_fingerprint"))
    if (row_source_key, row_fingerprint) == (transaction_source_key, transaction_fingerprint):
        return True
    if row_fingerprint and row_fingerprint == transaction_fingerprint:
        row_references = _official_reference_values(row)
        transaction_references = _official_reference_values(transaction)
        if row_references and transaction_references and row_references.intersection(transaction_references):
            return True
    return (
        not row_fingerprint
        and row_source_key.startswith("bank:")
        and row_source_key == transaction_fingerprint
        and (not transaction_source_key or transaction_source_key.startswith("bank-v2:"))
    )


def _official_reference_values(row: dict[str, Any]) -> set[str]:
    payload = _payload(row)
    normalized_row = _dict(payload.get("normalized_row"))
    values = {
        row.get(field_name) or normalized_row.get(field_name) or payload.get(field_name)
        for field_name in ("account_detail_no", "bank_serial_no", "enterprise_serial_no")
    }
    return {
        "".join(unicodedata.normalize("NFKC", str(value)).split()).upper()
        for value in values
        if _text(value)
    }


def _job_issues(
    jobs: list[dict[str, Any]],
    files: list[dict[str, Any]],
    batches: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    sessions = {_text(row.get("session_id")) for row in files}
    file_ids = {_text(row.get("file_id")) for row in files}
    batch_ids = {_text(row.get("batch_id")) for row in batches}
    for row in jobs:
        job_id = _text(row.get("job_id"))
        status = _text(row.get("status"))
        payload = _dict(row.get("payload"))
        result = _dict(row.get("result_payload"))
        session_id = _job_session_id(row)
        if session_id not in sessions:
            issues.append(_issue("bank_import_job_session_orphan", job_id, {"session_id": session_id}))
        selected_file_ids = _job_selected_file_ids(row)
        if selected_file_ids - file_ids:
            issues.append(_issue("bank_import_job_file_orphan", job_id, {"file_ids": sorted(selected_file_ids - file_ids)}))
        if status in ACTIVE_JOB_STATUSES or (status == "failed" and _int(row.get("attempt_count"), 0) < _int(row.get("max_attempts"), 1)):
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "银行流水导入任务尚未排空。",
                    job_id,
                    "file_import.confirm",
                    {
                        "status": status,
                        "stage": row.get("stage"),
                        "attempt_count": _int(row.get("attempt_count"), 0),
                        "max_attempts": _int(row.get("max_attempts"), 0),
                        "last_error": _text(row.get("last_error")) or None,
                        "session_id": session_id or None,
                        "selected_file_ids": sorted(selected_file_ids),
                    },
                )
            )
        elif status == "failed":
            issues.append(_issue("bank_import_job_terminal_failure", job_id, {"last_error": row.get("last_error")}))
        if status == "succeeded":
            result_batch_ids = _result_batch_ids(result)
            if result_batch_ids and not result_batch_ids.issubset(batch_ids):
                issues.append(
                    _issue(
                        "bank_import_job_result_batch_orphan",
                        job_id,
                        {"batch_ids": sorted(result_batch_ids - batch_ids)},
                    )
                )
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
                "银行流水导入 outbox 尚未排空。",
                event_id,
                "import.process.requested",
                {"status": status, "last_error": row.get("last_error")},
            )
        )
        if status in {"failed", "dead_lettered"}:
            issues.append(_issue("bank_import_outbox_terminal_failure", event_id, {"status": status}))
    return issues


def _is_bank_file(row: dict[str, Any], *, batch_ids: set[str]) -> bool:
    payload = _payload(row)
    batch_type = _text(payload.get("batch_type") or payload.get("override_batch_type"))
    referenced = {_text(payload.get("preview_batch_id")), _text(payload.get("batch_id"))}
    return batch_type == "bank_transaction" or bool((referenced - {""}) & batch_ids)


def _job_session_id(row: dict[str, Any]) -> str:
    return _text(row.get("import_session_id")) or _text(_dict(row.get("payload")).get("session_id"))


def _job_selected_file_ids(row: dict[str, Any]) -> set[str]:
    return {_text(value) for value in _list(_dict(row.get("payload")).get("selected_file_ids")) if _text(value)}


def _result_batch_ids(result: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    batch = _dict(result.get("batch"))
    if _text(batch.get("id")):
        ids.add(_text(batch.get("id")))
    session = _dict(result.get("session")) or result
    for file_payload in _list(session.get("files")):
        item = _dict(file_payload)
        if _text(item.get("batch_id")):
            ids.add(_text(item.get("batch_id")))
    return ids


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
        if structured_key == "amount":
            left = _decimal_text(structured.get(structured_key))
            right = _decimal_text(payload.get(payload_key))
        elif structured_key.endswith("_time"):
            left = _time_text(structured.get(structured_key))
            right = _time_text(payload.get(payload_key))
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
        "银行流水导入 canonical facts、集合、字段、引用或任务状态不一致。",
        subject_id,
        "bank_transaction_import",
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


def _time_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    parsed: datetime | None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text.replace("+00:00", "Z")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BANK_IMPORT_LOCAL_TIMEZONE)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _comparable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if hasattr(value, "isoformat"):
        return _time_text(value)
    return value


BANK_IMPORT_FILE_SQL = """
select f.id::text as file_pk, coalesce(f.legacy_mongo_id, f.id::text) as file_id,
       f.session_id, f.audit_contract_revision, f.file_object_id::text, f.stored_file_path, f.original_filename, f.template_kind,
       f.status, f.uploaded_by, f.uploaded_at, f.raw_payload,
       o.storage_backend, o.storage_uri, o.bucket_name, o.object_key, o.filename as object_filename,
       o.sha256, o.size_bytes, o.content_type
from app.import_files f
left join app.file_objects o on o.id = f.file_object_id
order by f.session_id, f.uploaded_at, file_id
"""
BANK_IMPORT_BATCH_SQL = """
select coalesce(id::text, legacy_mongo_id) as formal_id,
       coalesce(legacy_mongo_id, id::text) as batch_id,
       batch_type, source_name, imported_by, row_count, success_count, error_count,
       duplicate_count, suspected_duplicate_count, updated_count, status, imported_at, raw_payload
from app.import_batches
where batch_type = 'bank_transaction'
order by imported_at, batch_id
"""
BANK_IMPORT_ROW_SQL = """
select coalesce(r.legacy_mongo_id, r.id::text) as row_id,
       coalesce(b.legacy_mongo_id, b.id::text, r.legacy_batch_id) as batch_id,
       r.row_no, r.source_record_type, r.source_unique_key, r.data_fingerprint,
       r.decision, r.decision_reason, r.linked_object_type, r.linked_object_id,
       r.identity_kind, r.account_no, r.trade_time, r.direction, r.amount,
       r.counterparty_name, r.raw_payload
from app.import_batch_rows r
join app.import_batches b on b.id = r.import_batch_id
where b.batch_type = 'bank_transaction'
order by batch_id, r.row_no, row_id
"""
_TRANSACTION_SQL = """
select coalesce(t.legacy_mongo_id, t.id::text) as transaction_id,
       coalesce(b.legacy_mongo_id, b.id::text, t.legacy_source_batch_id) as batch_id,
       t.account_no, t.account_name, t.txn_direction, t.counterparty_name_raw,
       t.amount, t.signed_amount, t.balance, t.currency, t.txn_date, t.trade_time, t.bank_serial_no,
       t.source_unique_key, t.data_fingerprint, t.status, t.raw_payload
from app.bank_transactions t
left join app.import_batches b
  on b.id = t.source_batch_id
  or (t.source_batch_id is null and b.legacy_mongo_id = t.legacy_source_batch_id)
order by batch_id, transaction_id
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
