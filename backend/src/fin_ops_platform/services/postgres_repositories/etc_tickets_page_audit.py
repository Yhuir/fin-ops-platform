from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)


ACTIVE_BATCH_STATUSES = frozenset(
    {
        "draft",
        "reviewing",
        "ready_for_import",
        "importing",
        "imported",
        "import_failed",
        "import_partial_failed",
        "oa_draft_creating",
        "oa_draft_failed",
        "oa_confirmation_pending",
        "not_submitted",
        "manually_marked_not_submitted",
        "migration_conflict",
        "business_batch_invariant_broken",
    }
)
SUBMITTED_BATCH_STATUSES = frozenset({"oa_submitted", "manually_marked_submitted", "closed"})
VISIBLE_BATCH_STATUSES = ACTIVE_BATCH_STATUSES | SUBMITTED_BATCH_STATUSES
ACTIVE_IMPORT_JOB_STATUSES = frozenset({"pending", "processing"})
COVERED_IMPORT_TASK_STATUSES = frozenset({"imported", "closed"})
TERMINAL_IMPORT_JOB_STATUSES = frozenset({"failed", "dead_lettered"})


def audit_etc_tickets_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_etc_tickets_snapshot(
            snapshot.connection,
            tenant_id=str(tenant_id or "default").strip() or "default",
            limit=max(int(example_limit or 50), 1),
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_etc_tickets_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    facts, issues = collect_etc_tickets_integrity(connection, tenant_id=tenant_id)
    batches = facts["batches"]
    tasks = facts["tasks"]
    files = facts["files"]
    invoices = facts["invoices"]
    import_batches = facts["import_batches"]
    submission_batches = facts["submission_batches"]
    invoice_links = facts["invoice_links"]
    import_jobs = facts["import_jobs"]

    evaluation = evaluate_audit_issues(issues, sample_limit=limit)

    visible_batches = [row for row in batches if _text(row.get("status")) in VISIBLE_BATCH_STATUSES]
    active_tasks = [row for row in tasks if _text(row.get("status")) != "deleted"]
    active_files = [row for row in files if _text(row.get("status")) != "deleted"]
    active_invoices = [row for row in invoices if _text(row.get("status")) != "deleted"]
    return {
        "mode": "etc-tickets-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            "visible_business_batch_count": len(visible_batches),
            "active_business_batch_count": sum(
                1 for row in visible_batches if _text(row.get("status")) in ACTIVE_BATCH_STATUSES
            ),
            "submitted_business_batch_count": sum(
                1 for row in visible_batches if _text(row.get("status")) in SUBMITTED_BATCH_STATUSES
            ),
            "active_reconciliation_task_count": len(active_tasks),
            "active_reconciliation_file_count": len(active_files),
            "active_etc_invoice_count": len(active_invoices),
            "active_invoice_link_count": sum(
                1 for row in invoice_links if _text(row.get("link_status")) == "active"
            ),
            "etc_import_job_count": len(import_jobs),
            "covered_failed_import_job_count": sum(
                1
                for row in import_jobs
                if _text(row.get("status")) in TERMINAL_IMPORT_JOB_STATUSES
                and _text(row.get("task_status")) in COVERED_IMPORT_TASK_STATUSES
            ),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": _etc_tickets_audit_contract(
            snapshot_consistency=snapshot_consistency,
            database_snapshot=database_snapshot,
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def collect_etc_tickets_integrity(
    connection: Any,
    *,
    tenant_id: str,
    include_import_job_issues: bool = True,
) -> tuple[dict[str, list[dict[str, Any]]], list[AuditIssue]]:
    batches = connection.fetch_all(_BUSINESS_BATCH_SQL)
    tasks = connection.fetch_all(_TASK_SQL)
    files = connection.fetch_all(_FILE_SQL)
    invoices = connection.fetch_all(_ETC_INVOICE_SQL)
    import_batches = connection.fetch_all(_IMPORT_BATCH_SQL)
    submission_batches = connection.fetch_all(_SUBMISSION_BATCH_SQL)
    invoice_links = connection.fetch_all(_INVOICE_LINK_SQL, (tenant_id,))
    import_jobs = connection.fetch_all(_IMPORT_JOB_SQL, (tenant_id,))

    issues: list[AuditIssue] = []
    issues.extend(_row_contract_issues(batches, tasks, files, invoices, import_batches, submission_batches))
    issues.extend(
        _batch_relation_issues(
            batches=batches,
            tasks=tasks,
            invoices=invoices,
            import_batches=import_batches,
            submission_batches=submission_batches,
            invoice_links=invoice_links,
        )
    )
    issues.extend(_task_relation_issues(tasks=tasks, files=files, import_batches=import_batches))
    if include_import_job_issues:
        issues.extend(_import_job_issues(import_jobs))
    return (
        {
            "batches": batches,
            "tasks": tasks,
            "files": files,
            "invoices": invoices,
            "import_batches": import_batches,
            "submission_batches": submission_batches,
            "invoice_links": invoice_links,
            "import_jobs": import_jobs,
        },
        issues,
    )


def _etc_tickets_audit_contract(*, snapshot_consistency: str, database_snapshot: bool) -> dict[str, Any]:
    return {
            "source_tables": [
                "app.etc_business_batches",
                "app.etc_reconciliation_tasks",
                "app.etc_reconciliation_files",
                "app.etc_invoices",
                "app.etc_import_batches",
                "app.etc_submission_batches",
                "app.etc_batch_invoice_links",
                "app.invoices",
                "job.import_jobs",
            ],
            "read_model_tables": [],
            "canonical_expected_set": (
                "all non-deleted business batches, reconciliation tasks/files, ETC invoice metadata, import and "
                "submission batches reconstructed from normalized columns and registered payload members"
            ),
            "key_display_fields": [
                "business batch title/status/version/owner/month/OA identifiers",
                "business batch invoice count/amount and invoice detail fields",
                "task title/status/version/date/amount/count/plate fields",
                "source file identity/kind/name/size/hash/object reference",
                "credit-card, ticket-root, supplement and reconciliation item fields",
            ],
            "relation_edge_equality": (
                "bidirectional equality for business-batch/task, business-batch/ETC-invoice, "
                "business/import/submission-batch/invoice and task/file duplicated representations; "
                "referential and unique-owner closure for card/ticket/reconciled/supplement single-source edges; "
                "shared Workbench relation is outside this page consumer contract"
            ),
            "proof_checks": [
                "formal_column_to_registered_payload_equality",
                "visible_batch_bucket_and_control_total_recalculation",
                "business_batch_task_invoice_import_submission_bidirectional_edges",
                "canonical_invoice_bridge_referential_integrity",
                "task_file_bidirectional_membership",
                "card_ticket_reconciled_supplement_reference_and_owner_closure",
                "ETC_import_job_queue_and_terminal_failure_gate",
            ],
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": (
                "ETC source archive bytes/object readability and real OA draft state before App registration "
                "are not proven by this PostgreSQL snapshot"
            ),
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Every registered App ETC page fact and internal typed relation agrees in one database snapshot; "
                "external ETC archive/OA completeness and downstream Workbench relation completeness are not inferred."
            ),
            "write_policy": "read_only",
    }


def _row_contract_issues(
    batches: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    files: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    import_batches: list[dict[str, Any]],
    submission_batches: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    issues.extend(
        _duplicate_key_issues(batches, "business_batch_id", "etc_business_batch_duplicate")
    )
    issues.extend(_duplicate_key_issues(tasks, "task_id", "etc_reconciliation_task_duplicate"))
    issues.extend(_duplicate_key_issues(files, "file_id", "etc_reconciliation_file_duplicate"))
    issues.extend(_duplicate_key_issues(invoices, "etc_invoice_id", "etc_invoice_duplicate"))
    issues.extend(_duplicate_key_issues(import_batches, "batch_id", "etc_import_batch_duplicate"))
    issues.extend(
        _duplicate_key_issues(submission_batches, "submission_batch_id", "etc_submission_batch_duplicate")
    )

    for row in batches:
        payload = _payload(row)
        subject = _text(row.get("business_batch_id"))
        issues.extend(
            _compare_fields(
                subject,
                "etc_business_batch_display_field_mismatch",
                row,
                payload,
                {
                    "business_batch_id": "business_batch_id",
                    "task_id": "task_id",
                    "status": "status",
                    "version": "version",
                },
                aliases={
                    "business_batch_id": ("businessBatchId",),
                    "task_id": ("taskId",),
                },
            )
        )
        status = _text(row.get("status"))
        if status not in VISIBLE_BATCH_STATUSES | {"deleted", "superseded", "withdrawn"}:
            issues.append(_issue("etc_business_batch_unknown_status", subject, {"status": status}))
        if status in VISIBLE_BATCH_STATUSES and not _text(_first(payload, "title")):
            issues.append(_issue("etc_business_batch_title_missing", subject, None))

    for row in tasks:
        payload = _payload(row)
        subject = _text(row.get("task_id"))
        issues.extend(
            _compare_fields(
                subject,
                "etc_reconciliation_task_display_field_mismatch",
                row,
                payload,
                {"task_id": "task_id", "status": "status", "version": "version"},
                aliases={"task_id": ("taskId",)},
            )
        )
        if _text(row.get("status")) != "deleted" and not _text(_first(payload, "title")):
            issues.append(_issue("etc_reconciliation_task_title_missing", subject, None))
        result_summary = _dict(row.get("result_summary"))
        for field in (
            "approved_delta",
            "approved_delta_note",
            "oa_total_amount",
            "etc_invoice_amount",
            "supplement_amount",
            "etc_invoice_count",
            "supplement_count",
            "vehicle_plates",
            "confirmed_item_set_hash",
        ):
            if field not in payload and field not in result_summary:
                continue
            if not _value_equal(result_summary.get(field), payload.get(field), money=field.endswith("amount") or field == "approved_delta"):
                issues.append(
                    _issue(
                        "etc_reconciliation_task_summary_mismatch",
                        subject,
                        {"field": field, "formal": result_summary.get(field), "expected": payload.get(field)},
                    )
                )

    for row in files:
        payload = _payload(row)
        subject = _text(row.get("file_id"))
        issues.extend(
            _compare_fields(
                subject,
                "etc_reconciliation_file_display_field_mismatch",
                row,
                payload,
                {
                    "task_id": "task_id",
                    "file_id": "file_id",
                    "file_kind": "source_kind",
                    "file_path": "stored_path",
                    "file_sha256": "sha256",
                },
                aliases={
                    "task_id": ("taskId",),
                    "file_id": ("fileId",),
                    "file_kind": ("sourceKind",),
                    "file_path": ("filePath", "storedPath"),
                    "file_sha256": ("fileSha256",),
                },
            )
        )
        if _text(row.get("status")) != "deleted":
            for field in ("original_name", "size_bytes", "sha256", "stored_path"):
                if _first(payload, field, _camel(field)) in (None, ""):
                    issues.append(
                        _issue("etc_reconciliation_file_metadata_missing", subject, {"field": field})
                    )
            if row.get("file_object_id") and not bool(row.get("file_object_registered")):
                issues.append(
                    _issue(
                        "etc_reconciliation_file_object_unavailable",
                        subject,
                        {"file_object_id": row.get("file_object_id")},
                    )
                )

    for row in invoices:
        payload = _payload(row)
        subject = _text(row.get("etc_invoice_id"))
        issues.extend(
            _compare_fields(
                subject,
                "etc_invoice_display_field_mismatch",
                row,
                payload,
                {
                    "etc_invoice_id": "id",
                    "invoice_no": "invoice_number",
                    "invoice_date": "issue_date",
                    "seller_name": "seller_name",
                    "buyer_name": "buyer_name",
                    "amount": "amount_without_tax",
                    "tax_amount": "tax_amount",
                    "total_with_tax": "total_amount",
                    "status": "status",
                    "batch_id": "current_batch_id",
                    "task_id": "task_id",
                    "business_batch_id": "business_batch_id",
                    "file_path": "xml_file_path",
                    "file_sha256": "xml_file_hash",
                },
                aliases={
                    "invoice_no": ("invoiceNo",),
                    "invoice_date": ("invoiceDate",),
                    "batch_id": ("last_batch_id",),
                    "task_id": ("reconciliation_task_id",),
                    "file_path": ("pdf_file_path",),
                    "file_sha256": ("pdf_file_hash",),
                },
                money_fields={"amount", "tax_amount", "total_with_tax"},
            )
        )
        amount = _decimal(row.get("amount")) or Decimal("0")
        tax = _decimal(row.get("tax_amount")) or Decimal("0")
        total = _decimal(row.get("total_with_tax"))
        if total is not None and total != amount + tax:
            issues.append(
                _issue(
                    "etc_invoice_arithmetic_mismatch",
                    subject,
                    {"amount": str(amount), "tax_amount": str(tax), "total_with_tax": str(total)},
                )
            )
        if row.get("file_object_id") and not bool(row.get("file_object_registered")):
            issues.append(
                _issue(
                    "etc_invoice_file_object_unavailable",
                    subject,
                    {"file_object_id": row.get("file_object_id")},
                )
            )

    for row in import_batches:
        payload = _payload(row)
        subject = _text(row.get("batch_id"))
        invoice_ids = _text_set(payload.get("invoice_ids"))
        if invoice_ids and _integer(row.get("invoice_count")) != len(invoice_ids):
            issues.append(
                _issue(
                    "etc_import_batch_invoice_count_mismatch",
                    subject,
                    {"formal": row.get("invoice_count"), "expected": len(invoice_ids)},
                )
            )

    for row in submission_batches:
        payload = _payload(row)
        subject = _text(row.get("submission_batch_id"))
        formal_ids = _text_set(row.get("invoice_ids"))
        payload_ids = _text_set(payload.get("invoice_ids"))
        if formal_ids != payload_ids:
            issues.append(
                _issue(
                    "etc_submission_batch_invoice_set_mismatch",
                    subject,
                    {"formal": sorted(formal_ids), "expected": sorted(payload_ids)},
                )
            )
    return issues


def _batch_relation_issues(
    *,
    batches: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    import_batches: list[dict[str, Any]],
    submission_batches: list[dict[str, Any]],
    invoice_links: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    active_task_by_id = {
        _text(row.get("task_id")): row
        for row in tasks
        if _text(row.get("status")) != "deleted"
    }
    task_ids = set(active_task_by_id)
    invoice_by_id = {
        _text(row.get("etc_invoice_id")): row
        for row in invoices
        if _text(row.get("status")) != "deleted"
    }
    import_by_id = {_text(row.get("batch_id")): row for row in import_batches}
    submission_by_id = {_text(row.get("submission_batch_id")): row for row in submission_batches}
    linked_task_owners: Counter[str] = Counter()
    linked_invoice_owners: defaultdict[str, set[str]] = defaultdict(set)

    for row in batches:
        status = _text(row.get("status"))
        if status not in VISIBLE_BATCH_STATUSES:
            continue
        subject = _text(row.get("business_batch_id"))
        payload = _payload(row)
        task_id = _text(row.get("task_id"))
        if not task_id or task_id not in task_ids:
            issues.append(_issue("etc_business_batch_task_missing", subject, {"task_id": task_id}))
        else:
            linked_task_owners[task_id] += 1
            task_title = _text(_payload(active_task_by_id[task_id]).get("title"))
            batch_title = _text(payload.get("title"))
            if task_title != batch_title:
                issues.append(
                    _issue(
                        "etc_business_batch_task_title_mismatch",
                        subject,
                        {"batch_title": batch_title, "task_title": task_title},
                    )
                )

        expected_invoice_ids = _text_set(payload.get("invoice_ids"))
        actual_invoice_ids = {
            invoice_id
            for invoice_id, invoice in invoice_by_id.items()
            if _text(invoice.get("business_batch_id")) == subject
        }
        if expected_invoice_ids != actual_invoice_ids:
            issues.append(
                _issue(
                    "etc_business_batch_invoice_edge_mismatch",
                    subject,
                    {
                        "missing_from_invoice_owner": sorted(expected_invoice_ids - actual_invoice_ids),
                        "unexpected_invoice_owner": sorted(actual_invoice_ids - expected_invoice_ids),
                    },
                )
            )
        for invoice_id in expected_invoice_ids:
            linked_invoice_owners[invoice_id].add(subject)
            if invoice_id not in invoice_by_id:
                issues.append(
                    _issue("etc_business_batch_invoice_missing", subject, {"invoice_id": invoice_id})
                )

        expected_import_ids = _text_set(payload.get("import_batch_ids"))
        invoice_import_ids = {
            _text(_payload(invoice).get("import_batch_id"))
            for invoice_id, invoice in invoice_by_id.items()
            if invoice_id in expected_invoice_ids and _text(_payload(invoice).get("import_batch_id"))
        }
        if expected_import_ids != invoice_import_ids:
            issues.append(
                _issue(
                    "etc_business_batch_import_edge_mismatch",
                    subject,
                    {"declared": sorted(expected_import_ids), "derived": sorted(invoice_import_ids)},
                )
            )
        for import_id in expected_import_ids:
            if import_id not in import_by_id:
                issues.append(_issue("etc_business_batch_import_missing", subject, {"import_batch_id": import_id}))

        submission_id = _text(payload.get("submission_batch_id"))
        submission = submission_by_id.get(submission_id) if submission_id else None
        expected_count, expected_total = _batch_controls(
            payload,
            _payload(submission) if submission is not None else {},
        )
        if _integer(row.get("invoice_count")) != expected_count:
            issues.append(
                _issue(
                    "etc_business_batch_invoice_count_mismatch",
                    subject,
                    {"formal": row.get("invoice_count"), "expected": expected_count},
                )
            )
        if _decimal(row.get("total_amount")) != expected_total:
            issues.append(
                _issue(
                    "etc_business_batch_total_amount_mismatch",
                    subject,
                    {"formal": row.get("total_amount"), "expected": str(expected_total)},
                )
            )
        if submission_id:
            if submission is None:
                issues.append(
                    _issue("etc_business_batch_submission_missing", subject, {"submission_batch_id": submission_id})
                )
            else:
                submission_ids = _text_set(submission.get("invoice_ids"))
                if submission_ids != expected_invoice_ids:
                    issues.append(
                        _issue(
                            "etc_business_batch_submission_invoice_edge_mismatch",
                            subject,
                            {"business": sorted(expected_invoice_ids), "submission": sorted(submission_ids)},
                        )
                    )

    for task_id, count in linked_task_owners.items():
        if count > 1:
            issues.append(_issue("etc_reconciliation_task_multiple_business_batches", task_id, {"count": count}))
    for invoice_id, owners in linked_invoice_owners.items():
        if len(owners) > 1:
            issues.append(
                _issue("etc_invoice_multiple_business_batches", invoice_id, {"owners": sorted(owners)})
            )
    visible_batch_ids = {
        _text(row.get("business_batch_id"))
        for row in batches
        if _text(row.get("status")) in VISIBLE_BATCH_STATUSES
    }
    for invoice_id, invoice in invoice_by_id.items():
        business_id = _text(invoice.get("business_batch_id"))
        if business_id and business_id not in visible_batch_ids:
            issues.append(
                _issue(
                    "etc_invoice_business_batch_missing",
                    invoice_id,
                    {"business_batch_id": business_id},
                )
            )

    declared_import_members = {
        import_id: _text_set(_payload(import_row).get("invoice_ids"))
        for import_id, import_row in import_by_id.items()
    }
    for import_id, declared_ids in declared_import_members.items():
        missing_invoice_ids = sorted(declared_ids - set(invoice_by_id))
        if missing_invoice_ids:
            issues.append(
                _issue(
                    "etc_import_batch_invoice_missing",
                    import_id,
                    {"missing_invoice_ids": missing_invoice_ids},
                )
            )

    # An import batch is an immutable import-attempt membership event. Re-importing an
    # existing invoice can therefore register the same invoice in several batch events,
    # while the invoice's import_batch_id remains its first/current provenance owner.
    # Prove both representations without incorrectly requiring every historical event to
    # be the invoice's single current owner.
    for invoice_id, invoice in invoice_by_id.items():
        import_id = _text(_payload(invoice).get("import_batch_id"))
        if not import_id or import_id not in import_by_id:
            continue
        if invoice_id not in declared_import_members.get(import_id, set()):
            issues.append(
                _issue(
                    "etc_invoice_import_owner_membership_mismatch",
                    invoice_id,
                    {"import_batch_id": import_id},
                )
            )

    active_links = [row for row in invoice_links if _text(row.get("link_status")) == "active"]
    link_keys: Counter[tuple[str, str]] = Counter()
    for link in active_links:
        business_id = _text(link.get("business_batch_id"))
        etc_invoice_id = _text(link.get("etc_invoice_id"))
        invoice_id = _text(link.get("invoice_id"))
        identity_key = _text(link.get("identity_key"))
        subject = f"{business_id}:{identity_key or invoice_id}"
        link_keys[(business_id, identity_key or invoice_id)] += 1
        if business_id not in {
            _text(row.get("business_batch_id")) for row in batches if _text(row.get("status")) in VISIBLE_BATCH_STATUSES
        }:
            issues.append(_issue("etc_invoice_link_business_batch_missing", subject, None))
        if etc_invoice_id and etc_invoice_id not in invoice_by_id:
            issues.append(_issue("etc_invoice_link_etc_invoice_missing", subject, {"etc_invoice_id": etc_invoice_id}))
        if not invoice_id or not bool(link.get("canonical_invoice_exists")):
            issues.append(_issue("etc_invoice_link_canonical_invoice_missing", subject, {"invoice_id": invoice_id}))
        if etc_invoice_id and _text(invoice_by_id.get(etc_invoice_id, {}).get("business_batch_id")) != business_id:
            issues.append(
                _issue(
                    "etc_invoice_link_owner_mismatch",
                    subject,
                    {"etc_invoice_id": etc_invoice_id, "business_batch_id": business_id},
                )
            )
    for (business_id, identity), count in link_keys.items():
        if count > 1:
            issues.append(
                _issue("etc_invoice_link_duplicate", f"{business_id}:{identity}", {"count": count})
            )
    return issues


def _task_relation_issues(
    *,
    tasks: list[dict[str, Any]],
    files: list[dict[str, Any]],
    import_batches: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    formal_files_by_task: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    import_batch_ids = {_text(row.get("batch_id")) for row in import_batches}
    for row in files:
        if _text(row.get("status")) == "deleted":
            continue
        formal_files_by_task[_text(row.get("task_id"))][_text(row.get("file_id"))] = row

    for row in tasks:
        if _text(row.get("status")) == "deleted":
            continue
        task_id = _text(row.get("task_id"))
        payload = _payload(row)
        import_batch_id = _text(payload.get("import_batch_id"))
        if import_batch_id and import_batch_id not in import_batch_ids:
            issues.append(
                _issue(
                    "etc_reconciliation_task_import_batch_missing",
                    task_id,
                    {"import_batch_id": import_batch_id},
                )
            )
        source_files = _dict_list(payload.get("source_files"))
        declared_files = {_text(_first(item, "file_id", "fileId")) for item in source_files}
        declared_files.discard("")
        formal_files = set(formal_files_by_task.get(task_id, {}))
        if declared_files != formal_files:
            issues.append(
                _issue(
                    "etc_reconciliation_task_file_edge_mismatch",
                    task_id,
                    {
                        "missing_formal": sorted(declared_files - formal_files),
                        "unexpected_formal": sorted(formal_files - declared_files),
                    },
                )
            )

        cards = _unique_items(payload, "credit_card_items", "item_id", task_id, issues)
        tickets = _unique_items(payload, "ticket_root_items", "item_id", task_id, issues)
        evidences = _unique_items(payload, "supplement_evidences", "evidence_id", task_id, issues)
        reconciled = _unique_items(payload, "reconciled_items", "item_id", task_id, issues)
        for item_type, items in (
            ("credit_card", cards),
            ("ticket_root", tickets),
            ("supplement", evidences),
            ("reconciled", reconciled),
        ):
            for item_id, item in items.items():
                owner = _text(item.get("task_id"))
                if owner and owner != task_id:
                    issues.append(
                        _issue(
                            "etc_reconciliation_item_owner_mismatch",
                            item_id,
                            {"item_type": item_type, "task_id": owner, "expected": task_id},
                        )
                    )

        for card_id, card in cards.items():
            statement_file_id = _text(card.get("statement_file_id"))
            if statement_file_id and statement_file_id not in formal_files:
                issues.append(
                    _issue(
                        "etc_credit_card_source_file_missing", card_id, {"file_id": statement_file_id}
                    )
                )
        ticket_owners: defaultdict[str, set[str]] = defaultdict(set)
        for ticket_id, ticket in tickets.items():
            source_file_id = _text(ticket.get("ticket_file_id"))
            if source_file_id and source_file_id not in formal_files:
                issues.append(
                    _issue("etc_ticket_root_source_file_missing", ticket_id, {"file_id": source_file_id})
                )
            for card_id in _text_set(ticket.get("linked_credit_card_item_ids")):
                ticket_owners[ticket_id].add(card_id)
                if card_id not in cards:
                    issues.append(
                        _issue("etc_ticket_root_card_missing", ticket_id, {"card_id": card_id})
                    )
        for evidence_id, evidence in evidences.items():
            source_file_id = _text(evidence.get("source_file_id"))
            if source_file_id and source_file_id not in formal_files:
                issues.append(
                    _issue("etc_supplement_source_file_missing", evidence_id, {"file_id": source_file_id})
                )

        evidence_owners: defaultdict[str, set[str]] = defaultdict(set)
        for reconciled_id, item in reconciled.items():
            card_id = _text(item.get("credit_card_item_id"))
            if card_id not in cards:
                issues.append(_issue("etc_reconciled_card_missing", reconciled_id, {"card_id": card_id}))
            for ticket_id in _text_set(item.get("ticket_root_item_ids")):
                if ticket_id not in tickets:
                    issues.append(
                        _issue("etc_reconciled_ticket_missing", reconciled_id, {"ticket_id": ticket_id})
                    )
            for evidence_id in _text_set(item.get("supplement_evidence_ids")):
                evidence_owners[evidence_id].add(card_id)
                if evidence_id not in evidences:
                    issues.append(
                        _issue(
                            "etc_reconciled_supplement_missing",
                            reconciled_id,
                            {"evidence_id": evidence_id},
                        )
                    )
        for ticket_id, owners in ticket_owners.items():
            if len(owners) > 1:
                issues.append(
                    _issue("etc_ticket_multiple_card_owners", ticket_id, {"owners": sorted(owners)})
                )
        for evidence_id, owners in evidence_owners.items():
            if len(owners) > 1:
                issues.append(
                    _issue("etc_supplement_multiple_card_owners", evidence_id, {"owners": sorted(owners)})
                )
    for task_id, formal_files in formal_files_by_task.items():
        if task_id not in {_text(row.get("task_id")) for row in tasks if _text(row.get("status")) != "deleted"}:
            for file_id in formal_files:
                issues.append(_issue("etc_reconciliation_file_orphan_task", file_id, {"task_id": task_id}))
    return issues


def _import_job_issues(rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in rows:
        status = _text(row.get("status"))
        subject = _text(row.get("job_id"))
        attempt_count = _integer(row.get("attempt_count"))
        max_attempts = max(_integer(row.get("max_attempts")), 1)
        task_status = _text(row.get("task_status"))
        if status in ACTIVE_IMPORT_JOB_STATUSES:
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "ETC import durable queue 尚未排空。",
                    subject,
                    "etc_invoice_import.confirm",
                    {
                        "status": status,
                        "attempt_count": attempt_count,
                        "max_attempts": max_attempts,
                        "import_session_id": row.get("import_session_id"),
                        "task_id": row.get("task_id"),
                        "task_status": task_status,
                    },
                )
            )
        elif status in TERMINAL_IMPORT_JOB_STATUSES and task_status not in COVERED_IMPORT_TASK_STATUSES:
            issues.append(
                _issue(
                    "etc_import_job_terminal_failure",
                    subject,
                    {
                        "status": status,
                        "attempt_count": attempt_count,
                        "max_attempts": max_attempts,
                        "last_error": row.get("last_error"),
                        "import_session_id": row.get("import_session_id"),
                        "session_status": row.get("session_status"),
                        "task_id": row.get("task_id"),
                        "task_status": task_status,
                    },
                )
            )
    return issues


def _duplicate_key_issues(
    rows: Iterable[dict[str, Any]], key: str, code: str
) -> list[AuditIssue]:
    counts = Counter(_text(row.get(key)) for row in rows)
    return [_issue(code, value, {"count": count}) for value, count in counts.items() if not value or count > 1]


def _compare_fields(
    subject: str,
    code: str,
    formal: dict[str, Any],
    payload: dict[str, Any],
    fields: dict[str, str],
    *,
    aliases: dict[str, tuple[str, ...]] | None = None,
    money_fields: set[str] | None = None,
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    aliases = aliases or {}
    money_fields = money_fields or set()
    for formal_field, payload_field in fields.items():
        candidates = (payload_field, *aliases.get(formal_field, ()))
        expected = _first(payload, *candidates)
        if not _value_equal(formal.get(formal_field), expected, money=formal_field in money_fields):
            issues.append(
                _issue(
                    code,
                    subject,
                    {"field": formal_field, "formal": formal.get(formal_field), "expected": expected},
                )
            )
    return issues


def _unique_items(
    payload: dict[str, Any],
    collection: str,
    key: str,
    task_id: str,
    issues: list[AuditIssue],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _dict_list(payload.get(collection)):
        item_id = _text(_first(item, key, _camel(key)))
        if not item_id or item_id in result:
            issues.append(
                _issue(
                    "etc_reconciliation_item_duplicate_or_missing_id",
                    item_id or task_id,
                    {"collection": collection},
                )
            )
            continue
        result[item_id] = item
    return result


def _batch_controls(
    payload: dict[str, Any], submission_payload: dict[str, Any]
) -> tuple[int, Decimal]:
    invoice_ids = _text_set(payload.get("invoice_ids"))
    summary = _dict(payload.get("invoice_summary"))
    count_value = _first(payload, "etc_invoice_count")
    if count_value is None and summary.get("count") is not None:
        count_value = summary.get("count")
    if count_value is None:
        count_value = _first(submission_payload, "etc_invoice_count", "invoice_count")
    count = _integer(count_value) if count_value is not None else len(invoice_ids)
    amount_candidates = (
        _first(payload, "oa_total_amount", "total_amount"),
        summary.get("amount"),
        _first(submission_payload, "oa_total_amount", "total_amount", "etc_invoice_amount"),
        payload.get("total_with_tax"),
    )
    amount = next(
        (
            candidate
            for candidate in (_decimal(value) for value in amount_candidates)
            if candidate is not None and candidate != Decimal("0")
        ),
        Decimal("0"),
    )
    return count, amount


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("raw_payload")
    if not isinstance(payload, dict):
        return {}
    normalized = payload.get("normalized_payload")
    return dict(normalized) if isinstance(normalized, dict) else dict(payload)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value] if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def _text_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {_text(item) for item in value if _text(item)}


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        current: Any = payload
        found = True
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current is not None:
            return current
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        return None


def _value_equal(left: Any, right: Any, *, money: bool = False) -> bool:
    if money:
        return _decimal(left) == _decimal(right)
    if isinstance(left, datetime):
        left = left.isoformat()
    if hasattr(left, "isoformat") and not isinstance(left, str):
        left = left.isoformat()
    return left == right or _text(left) == _text(right)


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _issue(code: str, subject_id: str, details: dict[str, Any] | None) -> AuditIssue:
    return AuditIssue(
        "error",
        code,
        "ETC 票据 canonical facts、展示字段或内部关系不一致。",
        subject_id,
        "etc-tickets",
        details,
    )


_BUSINESS_BATCH_SQL = """select business_batch_id, task_id, status, to_char(scope_month, 'YYYY-MM') as scope_month, invoice_count, total_amount, import_attempts, audit_events, version, raw_payload from app.etc_business_batches where coalesce(legacy_mongo_id, '') !~ '^current_state:' order by business_batch_id"""
_TASK_SQL = """select task_id, status, to_char(scope_month, 'YYYY-MM') as scope_month, source_file_id, result_summary, version, raw_payload from app.etc_reconciliation_tasks where coalesce(legacy_mongo_id, '') !~ '^current_state:' order by task_id"""
_FILE_SQL = """select file.task_id, file.file_id, file.file_object_id::text as file_object_id, file.file_kind, file.status, file.file_path, file.file_sha256, file.raw_payload, (file.file_object_id is null or (object.id is not null and object.tombstoned_at is null and coalesce(object.object_key, object.storage_uri, '') <> '')) as file_object_registered from app.etc_reconciliation_files file left join app.file_objects object on object.id = file.file_object_id where coalesce(file.legacy_mongo_id, '') !~ '^current_state:' order by file.task_id, file.file_id"""
_ETC_INVOICE_SQL = """select etc.etc_invoice_id, etc.invoice_no, etc.invoice_code, etc.invoice_date::text as invoice_date, to_char(etc.scope_month, 'YYYY-MM') as scope_month, etc.seller_name, etc.buyer_name, etc.amount, etc.tax_amount, etc.total_with_tax, etc.status, etc.batch_id, etc.task_id, etc.business_batch_id, etc.file_object_id::text as file_object_id, etc.file_path, etc.file_sha256, etc.version, etc.raw_payload, (etc.file_object_id is null or (object.id is not null and object.tombstoned_at is null and coalesce(object.object_key, object.storage_uri, '') <> '')) as file_object_registered from app.etc_invoices etc left join app.file_objects object on object.id = etc.file_object_id where coalesce(etc.legacy_mongo_id, '') !~ '^current_state:' order by etc.etc_invoice_id"""
_IMPORT_BATCH_SQL = """select batch_id, status, to_char(scope_month, 'YYYY-MM') as scope_month, invoice_count, raw_payload from app.etc_import_batches where coalesce(legacy_mongo_id, '') !~ '^current_state:' order by batch_id"""
_SUBMISSION_BATCH_SQL = """select submission_batch_id, status, to_char(scope_month, 'YYYY-MM') as scope_month, invoice_ids, submitted_by, submitted_at, version, raw_payload from app.etc_submission_batches where coalesce(legacy_mongo_id, '') !~ '^current_state:' order by submission_batch_id"""
_INVOICE_LINK_SQL = """select link.business_batch_id, link.etc_invoice_id, link.invoice_id::text as invoice_id, link.identity_key, link.invoice_no, link.invoice_code, link.digital_invoice_no, link.invoice_date::text as invoice_date, link.link_status, link.link_source, link.confidence, (invoice.id is not null and invoice.status <> 'deleted') as canonical_invoice_exists from app.etc_batch_invoice_links link left join app.invoices invoice on invoice.id = link.invoice_id where link.tenant_id = %s order by link.business_batch_id, link.identity_key"""
_IMPORT_JOB_SQL = """
select job.id::text as job_id, job.import_type, job.import_session_id, job.source_file_id,
       job.status, job.stage, job.attempt_count, job.max_attempts, job.last_error,
       job.available_at, job.updated_at,
       session.status as session_status, session.task_id, task.status as task_status
from job.import_jobs job
left join app.etc_import_sessions session on session.session_id = job.import_session_id
left join app.etc_reconciliation_tasks task on task.task_id = session.task_id
where job.tenant_id = %s
  and job.import_type = 'etc_invoice_import.confirm'
order by job.created_at, job.id
"""
