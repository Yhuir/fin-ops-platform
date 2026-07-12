from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.etc_tickets_page_audit import (
    collect_etc_tickets_integrity,
)


ACTIVE_JOB_STATUSES = frozenset({"pending", "processing"})
TERMINAL_SESSION_STATUSES = frozenset({"succeeded", "partial_success"})
KNOWN_SESSION_STATUSES = frozenset({"preview_ready", "queued", "processing", "failed"}) | TERMINAL_SESSION_STATUSES
ETC_IMPORT_AUDIT_CONTRACT_REVISION = "etc-import-page-audit.v1"


def audit_etc_import_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_etc_import_snapshot(
            snapshot.connection,
            tenant_id=str(tenant_id or "default").strip() or "default",
            limit=max(int(example_limit or 50), 1),
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_etc_import_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    facts, issues = collect_etc_tickets_integrity(
        connection,
        tenant_id=tenant_id,
        include_import_job_issues=False,
    )
    sessions = connection.fetch_all(_SESSION_SQL)
    files = connection.fetch_all(_SESSION_FILE_SQL)
    strict_sessions = [
        row
        for row in sessions
        if _text(row.get("audit_contract_revision")) == ETC_IMPORT_AUDIT_CONTRACT_REVISION
    ]
    strict_session_ids = {_text(row.get("session_id")) for row in strict_sessions}
    strict_files = [row for row in files if _text(row.get("session_id")) in strict_session_ids]
    legacy_sessions = [row for row in sessions if row not in strict_sessions]
    jobs = [row for row in facts["import_jobs"] if _text(row.get("import_session_id")) in strict_session_ids]
    job_ids = [str(row.get("job_id") or "") for row in jobs if row.get("job_id")]
    outbox = connection.fetch_all(_OUTBOX_SQL, (job_ids,)) if job_ids else []

    issues.extend(_session_contract_issues(sessions=strict_sessions, files=strict_files))
    issues.extend(_session_task_edge_issues(sessions=strict_sessions, facts=facts))
    issues.extend(_session_job_issues(sessions=strict_sessions, jobs=jobs, outbox=outbox))
    if legacy_sessions:
        issues.append(
            AuditIssue(
                "warning",
                "etc_import_legacy_session_provenance_unproven",
                "Pre-contract ETC import session history remains readable App data, but missing historical ZIP/session evidence is not fabricated.",
                "legacy-etc-import-history",
                "imports.etc-invoices",
                {"session_count": len(legacy_sessions)},
            )
        )
    evaluation = evaluate_audit_issues(issues, sample_limit=limit)

    return {
        "mode": "etc-import-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            "session_count": len(sessions),
            "strict_contract_session_count": len(strict_sessions),
            "legacy_session_count": len(legacy_sessions),
            "session_file_count": len(strict_files),
            "preview_ready_count": sum(1 for row in strict_sessions if _text(row.get("status")) == "preview_ready"),
            "terminal_session_count": sum(
                1 for row in strict_sessions if _text(row.get("status")) in TERMINAL_SESSION_STATUSES
            ),
            "import_job_count": len(jobs),
            "outbox_event_count": len(outbox),
            "reconciliation_task_count": len(facts["tasks"]),
            "business_batch_count": len(facts["batches"]),
            "etc_invoice_count": len(facts["invoices"]),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": [
                "app.etc_import_sessions",
                "app.etc_import_session_files",
                "app.file_objects",
                "app.etc_reconciliation_tasks",
                "app.etc_business_batches",
                "app.etc_import_batches",
                "app.etc_invoices",
                "app.etc_batch_invoice_links",
                "app.invoices",
                "job.import_jobs",
                "job.outbox_events",
            ],
            "read_model_tables": [],
            "canonical_expected_set": (
                "every version-registered ETC import preview session and original ZIP file, all task-bound preview match edges, "
                "all terminal session business/import-batch/ETC-invoice edges, and the complete ETC tickets canonical closure"
            ),
            "key_display_fields": [
                "task id/version/confirmed item set hash/zip preview generation",
                "ZIP filename/hash/size/file object registration",
                "preview summary/audit/file counts/filter statuses/requirement ids/fingerprint",
                "session/job/task/business batch/import batch/ETC invoice statuses and identifiers",
            ],
            "relation_edge_equality": (
                "bidirectional session/file, session/task, preview invoice/requirement, terminal session/business/import-batch/"
                "ETC-invoice and ETC/canonical-invoice bridge equality; downstream Workbench pairing is outside this page contract"
            ),
            "proof_checks": [
                "formal_session_to_registered_payload_equality",
                "session_file_to_file_object_hash_size_equality",
                "preview_per_file_and_session_count_recalculation",
                "preview_filter_requirement_edge_equality_and_fingerprint",
                "session_task_version_hash_and_status_contract",
                "terminal_session_business_import_batch_invoice_bidirectional_edges",
                "ETC_tickets_canonical_closure_reused_in_same_snapshot",
                "page_owned_import_job_and_outbox_gate",
            ],
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": (
                "The PostgreSQL snapshot proves registered ZIP hash/size/object locator only; it does not read object bytes, "
                "prove the external ETC export omitted nothing, establish external control totals, or verify real OA state."
            ),
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Every version-registered App-internal ETC import fact and internal relation agrees in one database snapshot. "
                "Pre-contract ZIP/session provenance remains explicitly unproven rather than fabricated; external archive "
                "completeness and downstream page projections require their own evidence and Audits."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _session_contract_issues(
    *,
    sessions: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    files_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in files:
        files_by_session[_text(row.get("session_id"))].append(row)
    session_ids = {_text(row.get("session_id")) for row in sessions}
    for row in files:
        subject = _text(row.get("file_id")) or "unknown-file"
        if _text(row.get("session_id")) not in session_ids:
            issues.append(_issue("etc_import_file_orphan", subject, row))
        if not _text(row.get("file_object_id")) or not bool(row.get("file_object_registered")):
            issues.append(_issue("etc_import_file_object_missing", subject, row))
        if (
            _text(row.get("sha256")) != _text(row.get("object_sha256"))
            or _integer(row.get("size_bytes")) != _integer(row.get("object_size_bytes"))
        ):
            issues.append(_issue("etc_import_file_object_field_mismatch", subject, row))
        payload = _payload(row.get("raw_payload"))
        for formal_key, payload_key in (
            ("file_id", "file_id"),
            ("original_filename", "file_name"),
            ("sha256", "sha256"),
            ("size_bytes", "size_bytes"),
        ):
            if not _equal(row.get(formal_key), payload.get(payload_key)):
                issues.append(
                    _issue(
                        "etc_import_file_payload_mismatch",
                        subject,
                        {"field": formal_key, "formal": row.get(formal_key), "payload": payload.get(payload_key)},
                    )
                )

    for row in sessions:
        session_id = _text(row.get("session_id"))
        payload = _payload(row.get("raw_payload"))
        if _text(row.get("status")) not in KNOWN_SESSION_STATUSES:
            issues.append(_issue("etc_import_session_status_invalid", session_id, {"status": row.get("status")}))
        if _text(row.get("status")) == "failed":
            issues.append(
                _issue(
                    "etc_import_session_terminal_failure",
                    session_id,
                    {"last_error": row.get("last_error")},
                )
            )
        required = (
            "task_id",
            "task_version",
            "confirmed_item_set_hash",
            "preview_fingerprint",
        )
        for field_name in required:
            if row.get(field_name) in (None, "", 0):
                issues.append(_issue("etc_import_session_required_field_missing", session_id, {"field": field_name}))
        for formal_key in (
            "session_id",
            "status",
            "task_id",
            "task_version",
            "zip_preview_generation",
            "confirmed_item_set_hash",
            "preview_fingerprint",
        ):
            if not _equal(row.get(formal_key), payload.get(formal_key)):
                issues.append(
                    _issue(
                        "etc_import_session_payload_mismatch",
                        session_id,
                        {"field": formal_key, "formal": row.get(formal_key), "payload": payload.get(formal_key)},
                    )
                )
        preview_result = payload.get("preview_result") if isinstance(payload.get("preview_result"), dict) else {}
        preview_audit = payload.get("preview_audit") if isinstance(payload.get("preview_audit"), dict) else {}
        preview_files = [item for item in list(payload.get("preview_files") or []) if isinstance(item, dict)]
        reconciliation_filter = (
            payload.get("reconciliation_filter") if isinstance(payload.get("reconciliation_filter"), dict) else {}
        )
        if preview_audit != (row.get("preview_summary") if isinstance(row.get("preview_summary"), dict) else {}):
            issues.append(_issue("etc_import_session_preview_summary_mismatch", session_id, None))
        if preview_audit != (preview_result.get("audit") if isinstance(preview_result.get("audit"), dict) else {}):
            issues.append(_issue("etc_import_session_preview_audit_mismatch", session_id, None))
        session_files = sorted(files_by_session.get(session_id, []), key=lambda item: _integer(item.get("ordinal")))
        if len(session_files) != len(preview_files):
            issues.append(
                _issue(
                    "etc_import_session_file_set_mismatch",
                    session_id,
                    {"registered": len(session_files), "preview": len(preview_files)},
                )
            )
        else:
            for stored_file, preview_file in zip(session_files, preview_files, strict=True):
                if _text(stored_file.get("original_filename")) != _text(
                    preview_file.get("fileName") or preview_file.get("file_name")
                ):
                    issues.append(_issue("etc_import_session_file_name_mismatch", session_id, None))
        summed_audit = _sum_file_audits(preview_files)
        if summed_audit and summed_audit != {key: _integer(preview_audit.get(key)) for key in summed_audit}:
            issues.append(
                _issue(
                    "etc_import_session_file_audit_total_mismatch",
                    session_id,
                    {"expected": summed_audit, "actual": preview_audit},
                )
            )
        preview_items = [item for item in list(preview_result.get("items") or []) if isinstance(item, dict)]
        if _integer(preview_audit.get("original_count")) != len(preview_items):
            issues.append(
                _issue(
                    "etc_import_session_item_count_mismatch",
                    session_id,
                    {"audit": preview_audit.get("original_count"), "items": len(preview_items)},
                )
            )
        issues.extend(
            _preview_relation_issues(
                session_id=session_id,
                preview_items=preview_items,
                reconciliation_filter=reconciliation_filter,
            )
        )
        expected_fingerprint = _stored_preview_fingerprint(
            row=row,
            files=session_files,
            preview_result=preview_result,
            reconciliation_filter=reconciliation_filter,
        )
        if expected_fingerprint != _text(row.get("preview_fingerprint")):
            issues.append(
                _issue(
                    "etc_import_session_fingerprint_mismatch",
                    session_id,
                    {"expected": expected_fingerprint, "actual": row.get("preview_fingerprint")},
                )
            )
    return issues


def _preview_relation_issues(
    *,
    session_id: str,
    preview_items: list[dict[str, Any]],
    reconciliation_filter: dict[str, Any],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    filter_items = [item for item in list(reconciliation_filter.get("items") or []) if isinstance(item, dict)]
    expected = Counter(
        (
            _text(item.get("invoiceNumber")),
            _text(item.get("filterStatus")),
            _text(item.get("requirementId")),
        )
        for item in filter_items
        if _text(item.get("invoiceNumber"))
    )
    actual = Counter(
        (
            _text(item.get("invoiceNumber")),
            _text(item.get("filterStatus")),
            _text(item.get("requirementId")),
        )
        for item in preview_items
        if _text(item.get("invoiceNumber"))
    )
    if expected != actual:
        issues.append(
            _issue(
                "etc_import_preview_requirement_edge_mismatch",
                session_id,
                {"missing": list((expected - actual).elements()), "extra": list((actual - expected).elements())},
            )
        )
    included = sorted({_text(item.get("invoiceNumber")) for item in filter_items if item.get("filterStatus") == "included"})
    allowed = sorted({_text(value) for value in list(reconciliation_filter.get("allowedInvoiceNumbers") or []) if _text(value)})
    if included != allowed:
        issues.append(
            _issue(
                "etc_import_preview_allowed_set_mismatch",
                session_id,
                {"included": included, "allowed": allowed},
            )
        )
    return issues


def _session_task_edge_issues(
    *,
    sessions: list[dict[str, Any]],
    facts: dict[str, list[dict[str, Any]]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_by_id = {_text(row.get("task_id")): row for row in facts["tasks"]}
    session_by_id = {_text(row.get("session_id")): row for row in sessions}
    attempt_edges: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for batch in facts["batches"]:
        payload = _payload(batch.get("raw_payload"))
        for attempt in list(payload.get("import_attempts") or []):
            if isinstance(attempt, dict) and _text(attempt.get("session_id")):
                attempt_edges[_text(attempt.get("session_id"))].append((_text(batch.get("business_batch_id")), attempt))
    import_batch_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for batch in facts["import_batches"]:
        payload = _payload(batch.get("raw_payload"))
        if _text(payload.get("source_session_id")):
            import_batch_edges[_text(payload.get("source_session_id"))].append(batch)
    invoice_edges: dict[str, set[str]] = defaultdict(set)
    for invoice in facts["invoices"]:
        payload = _payload(invoice.get("raw_payload"))
        if _text(payload.get("import_session_id")):
            invoice_edges[_text(payload.get("import_session_id"))].add(_text(invoice.get("etc_invoice_id")))

    for session in sessions:
        session_id = _text(session.get("session_id"))
        task = task_by_id.get(_text(session.get("task_id")))
        if task is None:
            issues.append(_issue("etc_import_session_task_missing", session_id, {"task_id": session.get("task_id")}))
            continue
        status = _text(session.get("status"))
        task_payload = _payload(task.get("raw_payload"))
        if status in {"preview_ready", "failed"}:
            if (
                _text(task.get("status")) != "ready_for_import"
                or _integer(task.get("version")) != _integer(session.get("task_version"))
                or _text(task_payload.get("confirmed_item_set_hash")) != _text(session.get("confirmed_item_set_hash"))
            ):
                issues.append(_issue("etc_import_session_ready_task_mismatch", session_id, None))
        if status == "processing" and (
            _text(task.get("status")) != "importing"
            or _text(task_payload.get("import_batch_id")) != session_id
        ):
            issues.append(_issue("etc_import_session_processing_task_mismatch", session_id, None))
        if status in TERMINAL_SESSION_STATUSES:
            expected_task_status = "imported" if status == "succeeded" else "ready_for_import"
            if _text(task.get("status")) != expected_task_status:
                issues.append(
                    _issue(
                        "etc_import_terminal_task_status_mismatch",
                        session_id,
                        {"expected": expected_task_status, "actual": task.get("status")},
                    )
                )
            if not attempt_edges.get(session_id) or not import_batch_edges.get(session_id):
                issues.append(
                    _issue(
                        "etc_import_terminal_output_edge_missing",
                        session_id,
                        {
                            "business_attempts": len(attempt_edges.get(session_id, [])),
                            "import_batches": len(import_batch_edges.get(session_id, [])),
                        },
                    )
                )
            batch_invoice_ids = {
                _text(invoice_id)
                for batch in import_batch_edges.get(session_id, [])
                for invoice_id in list(_payload(batch.get("raw_payload")).get("invoice_ids") or [])
                if _text(invoice_id)
            }
            if batch_invoice_ids != invoice_edges.get(session_id, set()):
                issues.append(
                    _issue(
                        "etc_import_session_invoice_edge_mismatch",
                        session_id,
                        {
                            "missing": sorted(batch_invoice_ids - invoice_edges.get(session_id, set())),
                            "extra": sorted(invoice_edges.get(session_id, set()) - batch_invoice_ids),
                        },
                    )
                )

    for session_id in sorted(set(attempt_edges) | set(import_batch_edges) | set(invoice_edges)):
        if session_id not in session_by_id:
            issues.append(
                AuditIssue(
                    "warning",
                    "etc_import_historical_session_evidence_unproven",
                    "Historical ETC output references a pre-contract session; the missing archive evidence is not fabricated.",
                    session_id,
                    "imports.etc-invoices",
                    {
                        "business_attempts": len(attempt_edges.get(session_id, [])),
                        "import_batches": len(import_batch_edges.get(session_id, [])),
                        "invoices": len(invoice_edges.get(session_id, set())),
                    },
                )
            )
    return issues


def _session_job_issues(
    *,
    sessions: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    outbox: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    session_ids = {_text(row.get("session_id")) for row in sessions}
    jobs_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        session_id = _text(job.get("import_session_id"))
        jobs_by_session[session_id].append(job)
        if session_id not in session_ids:
            issues.append(_issue("etc_import_job_session_missing", _text(job.get("job_id")), {"session_id": session_id}))
        if _text(job.get("status")) in ACTIVE_JOB_STATUSES:
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "ETC 发票导入 job 尚未完成。",
                    _text(job.get("job_id")),
                    "imports.etc-invoices",
                    {"status": job.get("status"), "session_id": session_id},
                )
            )
        if _text(job.get("status")) in {"failed", "dead_lettered"}:
            issues.append(_issue("etc_import_job_terminal_failure", _text(job.get("job_id")), job))
    job_ids = {_text(row.get("job_id")) for row in jobs}
    for event in outbox:
        job_id = _text(event.get("aggregate_id"))
        if job_id not in job_ids:
            issues.append(_issue("etc_import_outbox_job_missing", _text(event.get("event_id")), event))
        if _text(event.get("status")) in {"pending", "processing", "failed", "dead_lettered"}:
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "ETC 发票导入 outbox 尚未收敛。",
                    _text(event.get("event_id")),
                    "imports.etc-invoices",
                    {"status": event.get("status"), "job_id": job_id},
                )
            )
    for session in sessions:
        status = _text(session.get("status"))
        related = jobs_by_session.get(_text(session.get("session_id")), [])
        if status in {"processing"} and not any(_text(job.get("status")) in ACTIVE_JOB_STATUSES for job in related):
            issues.append(_issue("etc_import_processing_job_missing", _text(session.get("session_id")), None))
        if status in TERMINAL_SESSION_STATUSES and not any(_text(job.get("status")) == "succeeded" for job in related):
            issues.append(_issue("etc_import_terminal_job_missing", _text(session.get("session_id")), None))
    return issues


def _stored_preview_fingerprint(
    *,
    row: dict[str, Any],
    files: list[dict[str, Any]],
    preview_result: dict[str, Any],
    reconciliation_filter: dict[str, Any],
) -> str:
    canonical = {
        "task_id": _text(row.get("task_id")),
        "task_version": _integer(row.get("task_version")),
        "confirmed_item_set_hash": _text(row.get("confirmed_item_set_hash")),
        "zip_preview_generation": _integer(row.get("zip_preview_generation")),
        "uploads": [
            {
                "file_name": _text(file.get("original_filename")),
                "sha256": _text(file.get("sha256")),
                "size_bytes": _integer(file.get("size_bytes")),
            }
            for file in sorted(files, key=lambda item: _integer(item.get("ordinal")))
        ],
        "summary": preview_result.get("summary"),
        "audit": preview_result.get("audit"),
        "items": [
            {
                "fileName": item.get("fileName"),
                "invoiceNumber": item.get("invoiceNumber"),
                "status": item.get("status"),
                "filterStatus": item.get("filterStatus"),
                "requirementId": item.get("requirementId"),
            }
            for item in list(preview_result.get("items") or [])
            if isinstance(item, dict)
        ],
        "reconciliation_filter": reconciliation_filter,
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sum_file_audits(preview_files: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "original_count",
        "unique_count",
        "duplicate_count",
        "duplicate_in_file_count",
        "duplicate_across_files_count",
        "existing_duplicate_count",
        "importable_count",
        "update_count",
        "merge_count",
        "suspected_duplicate_count",
        "error_count",
        "confirmable_count",
        "skipped_count",
    )
    if not preview_files:
        return {}
    totals = {key: 0 for key in keys}
    for file_payload in preview_files:
        audit = file_payload.get("audit") if isinstance(file_payload.get("audit"), dict) else {}
        for key in keys:
            totals[key] += _integer(audit.get(key))
    return totals


def _payload(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    normalized = payload.get("normalized_payload")
    return dict(normalized) if isinstance(normalized, dict) else dict(payload)


def _issue(code: str, subject_id: str, details: Any) -> AuditIssue:
    return AuditIssue(
        "error",
        code,
        "ETC 发票导入 session、字段或内部关系不一致。",
        subject_id,
        "imports.etc-invoices",
        details if isinstance(details, dict) or details is None else {"value": details},
    )


def _equal(left: Any, right: Any) -> bool:
    return left == right or _text(left) == _text(right)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


_SESSION_SQL = """
select session.session_id, session.audit_contract_revision, session.status, session.imported_by, session.imported_at,
       session.task_id, session.task_version, session.zip_preview_generation,
       session.confirmed_item_set_hash, session.preview_fingerprint,
       session.preview_summary, session.last_error, session.raw_payload,
       session.created_at, session.updated_at
from app.etc_import_sessions session
order by session.created_at, session.session_id
"""

_SESSION_FILE_SQL = """
select session.session_id, file.file_id, file.ordinal, file.file_object_id::text as file_object_id,
       file.original_filename, file.sha256, file.size_bytes, file.raw_payload,
       object.sha256 as object_sha256, object.size_bytes as object_size_bytes,
       (
         object.id is not null
         and object.tombstoned_at is null
         and coalesce(object.storage_uri, '') <> ''
         and coalesce(object.migration_status, 'verified') not in ('failed', 'tombstoned')
       ) as file_object_registered
from app.etc_import_session_files file
join app.etc_import_sessions session on session.id = file.session_id
left join app.file_objects object on object.id = file.file_object_id
order by session.created_at, session.session_id, file.ordinal, file.file_id
"""

_OUTBOX_SQL = """
select id::text as event_id, aggregate_id, status, attempt_count, max_attempts,
       last_error, payload, created_at, updated_at
from job.outbox_events
where event_type = 'import.process.requested'
  and aggregate_type = 'import_job'
  and aggregate_id = any(%s)
order by created_at, id
"""
