from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.common import row_payload, text, text_list
from fin_ops_platform.services.postgres_repositories.workbench_relation_audit import (
    workbench_relation_edge_equality_issues,
)
from fin_ops_platform.services.postgres_repositories.workbench_projection_audit import (
    workbench_etc_relation_integrity_issues,
    workbench_projection_integrity_issues,
)
from fin_ops_platform.services.workbench_etc_batch_link import relation_external_etc_batch_id


@dataclass(frozen=True)
class RelationDisplayIssue:
    severity: str
    code: str
    message: str
    case_id: str
    scope_key: str = ""
    row_id: str = ""
    row_type: str = ""
    details: dict[str, Any] | None = None


def audit_workbench_relation_display(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_workbench_relation_display_snapshot(
            snapshot.connection,
            tenant_id=str(tenant_id or "default").strip() or "default",
            example_limit=max(int(example_limit or 50), 1),
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_workbench_relation_display_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    example_limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    audit_issues, proof_summary = collect_workbench_page_integrity_issues(
        connection,
        tenant_id=tenant_id,
        limit=example_limit + 1,
    )
    audit_issues.extend(
        workbench_etc_relation_integrity_issues(
            connection,
            tenant_id=tenant_id,
            limit=example_limit + 1,
        )
    )
    audit_issues.extend(_dirty_scope_issues(connection, tenant_id=tenant_id, limit=example_limit + 1))
    audit_issues.extend(_matching_dirty_scope_issues(connection, tenant_id=tenant_id, limit=example_limit + 1))
    audit_issues.extend(_outbox_issues(connection, tenant_id=tenant_id, limit=example_limit + 1))
    evaluation = evaluate_audit_issues(audit_issues, sample_limit=example_limit)
    error_count = sum(1 for issue in audit_issues if issue.severity == "error")
    warning_count = sum(1 for issue in audit_issues if issue.severity == "warning")
    return {
        "mode": "workbench-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            **proof_summary,
            "issue_count": len(audit_issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "blocking_issue_count": error_count,
            "issue_counts_by_code": _audit_issue_counts_by_code(audit_issues),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": [
                "app.oa_applications",
                "app.bank_transactions",
                "app.invoices",
                "app.etc_business_batches",
                "app.etc_invoices",
                "app.etc_batch_invoice_links",
                "app.workbench_pair_relations",
                "app.bank_transaction_relation_claims",
                "app.workbench_row_overrides",
                "app.workbench_exception_cases",
            ],
            "read_model_tables": [
                "read_model.workbench_generations",
                "read_model.workbench_rows",
                "read_model.workbench_groups",
                "read_model.workbench_group_rows",
                "read_model.workbench_summary",
                "read_model.workbench_relation_groups",
                "read_model.workbench_relation_rows",
            ],
            "canonical_expected_set": (
                "eligible canonical OA, bank, invoice, and ETC summary/detail objects in active month generations, "
                "plus every active relation member in the query-composed case owner"
            ),
            "key_display_fields": [
                "object identity",
                "scope and source kind",
                "OA applicant/project/amount",
                "bank direction/amount/counterparty",
                "invoice identity/type/date/amount",
                "ETC batch members/count/amount",
                "case/mode/group owner",
                "ignored and handled-exception ownership",
                "generation and summary counts",
                "source dependency versions",
            ],
            "relation_edge_equality": (
                "canonical == relation_groups == relation_rows == query-composed Workbench case ownership"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "proof_checks": [
                "canonical_object_expected_set_equality",
                "active_month_generation_expected_set_equality",
                "generation_row_group_summary_counts",
                "bidirectional_relation_edge_equality",
                "query_composed_relation_case_ownership",
                "relation_member_completeness",
                "durable_queue_and_freshness_gate",
                "exact_etc_batch_relation_owner",
                "unique_etc_batch_relation_owner",
            ],
            "external_source_boundary": "bank, OA, invoice, and ETC completeness before App registration",
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Registered App-internal canonical objects, active Workbench generations, shared relation distribution, "
                "critical display fields, summaries, dependency versions, and durable refresh state agree."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def collect_workbench_page_integrity_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    include_summary: bool = True,
) -> tuple[list[AuditIssue], dict[str, Any]]:
    """Collect Workbench integrity proof inside the caller-owned read-only snapshot."""
    relations = [_normalize_relation(row) for row in _fetch_active_relations(connection)]
    active_generations = (
        _fetch_active_generations(connection, tenant_id=tenant_id)
        if include_summary
        else []
    )
    relation_row_ids = sorted(
        {
            row_id
            for relation in relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id or "").strip()
        }
    )
    relation_case_group_ids = sorted(
        {
            group_id
            for relation in relations
            for group_id in (
                str(relation.get("case_id") or ""),
                f"case:{str(relation.get('case_id') or '')}",
            )
            if group_id and group_id != "case:"
        }
    )
    group_rows = _fetch_active_group_rows(
        connection,
        tenant_id=tenant_id,
        group_ids=relation_case_group_ids,
    )
    rows_by_scope_and_id = _rows_by_scope_and_row_id(group_rows)
    issues: list[RelationDisplayIssue] = []

    for relation in relations:
        issues.extend(
            _query_composed_relation_display_issues(
                relation,
                rows_by_scope_and_id=rows_by_scope_and_id,
                group_rows=group_rows,
            )
        )
    audit_issues = [_display_audit_issue(issue) for issue in issues]
    audit_issues.extend(
        workbench_relation_edge_equality_issues(
            connection,
            tenant_id=tenant_id,
            limit=limit,
            code_prefix="reconciliation_workbench",
            label="关联台",
        )
    )
    audit_issues.extend(
        workbench_projection_integrity_issues(
            connection,
            tenant_id=tenant_id,
            limit=limit,
        )
    )
    return audit_issues, {
        "active_relation_count": len(relations),
        "active_generation_scope_count": len(active_generations),
        "audited_relation_row_id_count": len(relation_row_ids),
        "active_group_row_count": len(group_rows),
        "query_composed_scope": "all",
        "materialized_all_required": False,
    }


def _display_audit_issue(issue: RelationDisplayIssue) -> AuditIssue:
    details = dict(issue.details or {})
    if issue.row_id:
        details["row_id"] = issue.row_id
    if issue.row_type:
        details["row_type"] = issue.row_type
    return AuditIssue(
        severity=issue.severity,
        code=issue.code,
        message=issue.message,
        subject_id=issue.case_id,
        scope_key=issue.scope_key,
        details=details or None,
    )


def _dirty_scope_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: dirty_scope */
        select scope_type, scope_key, status, last_error
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type in ('workbench', 'workbench_relation')
          and status in ('pending', 'processing', 'failed')
        order by scope_type, scope_key
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="read_model_scope_not_fresh",
            message="关联台证明依赖的 read model scope 尚未收敛。",
            subject_id=text(row.get("scope_type")) or "",
            scope_key=text(row.get("scope_key")) or "",
            details={"status": row.get("status"), "last_error": row.get("last_error")},
        )
        for row in rows
    ]


def _matching_dirty_scope_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: workbench_matching_dirty_scope */
        select to_char(scope_month, 'YYYY-MM') as scope_key, status, last_error
        from job.workbench_matching_dirty_scopes
        where tenant_id = %s
          and status in ('dirty', 'processing', 'retry', 'failed')
        order by scope_month
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="workbench_matching_scope_not_converged",
            message="关联台确定性配对 scope 尚未收敛。",
            subject_id="workbench_matching",
            scope_key=text(row.get("scope_key")) or "",
            details={"status": row.get("status"), "last_error": row.get("last_error")},
        )
        for row in rows
    ]


def _outbox_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: outbox_backlog */
        select event_type, scope_key, status, last_error
        from job.outbox_events
        where tenant_id = %s
          and event_type in ('workbench.read_model.refresh', 'workbench_relation.read_model.refresh')
          and status in ('pending', 'processing', 'failed', 'dead_lettered')
        order by event_type, scope_key
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="read_model_outbox_not_drained",
            message="关联台证明依赖的 durable outbox 尚未排空。",
            subject_id=text(row.get("event_type")) or "",
            scope_key=text(row.get("scope_key")) or "",
            details={"status": row.get("status"), "last_error": row.get("last_error")},
        )
        for row in rows
    ]


def _fetch_active_relations(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          case_id,
          relation_mode,
          status,
          row_ids,
          row_types,
          month_scope::text as month_scope,
          amount_check,
          special_metadata,
          updated_at::text as updated_at,
          raw_payload
        from app.workbench_pair_relations
        where status = 'active'
        order by case_id
        """
    )


def _fetch_active_generations(connection: Any, *, tenant_id: str) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          scope_key,
          generation_id,
          activated_at::text as activated_at,
          row_count,
          group_count,
          build_metadata
        from read_model.workbench_generations
        where tenant_id = %s
          and status = 'active'
          and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
        order by scope_key
        """,
        (tenant_id,),
    )


def _fetch_active_group_rows(connection: Any, *, tenant_id: str, group_ids: list[str]) -> list[dict[str, Any]]:
    if not group_ids:
        return []
    return connection.fetch_all(
        """
        select
          gen.scope_key,
          gen.generation_id,
          gen.activated_at::text as generation_activated_at,
          gr.group_id,
          gr.zone,
          gr.pane,
          gr.row_id,
          gr.row_role,
          gr.source_kind,
          gr.status,
          case
              when jsonb_typeof(row_detail.payload) = 'object' and row_detail.payload <> '{}'::jsonb
              then row_detail.payload
              else gr.payload
          end as payload
        from read_model.workbench_generations gen
        join read_model.workbench_group_rows gr
          on gr.generation_id = gen.generation_id
         and gr.scope_key = gen.scope_key
        left join read_model.workbench_rows row_detail
          on row_detail.generation_id = gr.generation_id
         and row_detail.scope_key = gr.scope_key
         and row_detail.row_id = gr.row_id
        where gen.tenant_id = %s
          and gen.status = 'active'
          and gen.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
          and gr.row_role <> 'summary'
          and gr.group_id = any(%s)
        order by gen.scope_key, gr.row_id, gr.group_id
        """,
        (tenant_id, group_ids),
    )


def _normalize_relation(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "raw_payload")
    relation_payload = payload if isinstance(payload, dict) else {}
    row_ids = text_list(row.get("row_ids")) or text_list(relation_payload.get("row_ids"))
    row_types = text_list(row.get("row_types")) or text_list(relation_payload.get("row_types"))
    normalized_payload = relation_payload.get("normalized_payload")
    normalized_payload = normalized_payload if isinstance(normalized_payload, dict) else relation_payload
    amount_check = row_payload(row, "amount_check")
    if not isinstance(amount_check, dict):
        amount_check = normalized_payload.get("amount_check")
    if not isinstance(amount_check, dict):
        amount_check = relation_payload.get("amount_check")
    special_metadata = row_payload(row, "special_metadata")
    if not isinstance(special_metadata, dict):
        special_metadata = normalized_payload.get("special_metadata")
    if not isinstance(special_metadata, dict):
        special_metadata = relation_payload.get("special_metadata")
    return {
        "case_id": text(row.get("case_id") or relation_payload.get("case_id")) or "",
        "relation_mode": text(row.get("relation_mode") or relation_payload.get("relation_mode")) or "",
        "status": text(row.get("status") or relation_payload.get("status")) or "active",
        "row_ids": row_ids,
        "row_types": row_types,
        "month_scope": text(row.get("month_scope") or relation_payload.get("month_scope")) or "",
        "updated_at": text(row.get("updated_at")) or "",
        "external_etc_batch_id": _external_etc_batch_id(
            amount_check if isinstance(amount_check, dict) else {},
            special_metadata if isinstance(special_metadata, dict) else {},
        ),
    }


def _external_etc_batch_id(amount_check: dict[str, Any], special_metadata: dict[str, Any]) -> str:
    return relation_external_etc_batch_id(
        {"amount_check": amount_check, "special_metadata": special_metadata}
    )


def _rows_by_scope_and_row_id(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        scope_key = text(row.get("scope_key")) or ""
        row_id = text(row.get("row_id")) or ""
        if scope_key and row_id:
            grouped[(scope_key, row_id)].append(row)
    return grouped


def _query_composed_relation_display_issues(
    relation: dict[str, Any],
    *,
    rows_by_scope_and_id: dict[tuple[str, str], list[dict[str, Any]]],
    group_rows: list[dict[str, Any]],
) -> list[RelationDisplayIssue]:
    case_id = str(relation.get("case_id") or "")
    row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or []) if str(row_id or "").strip()]
    row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
    relation_mode = str(relation.get("relation_mode") or "")
    issues: list[RelationDisplayIssue] = []
    if not case_id or not row_ids:
        return issues

    expected_group_ids = {case_id, f"case:{case_id}"}
    composed_rows_by_id = {
        row_id: [
            row
            for (scope_key, candidate_row_id), scoped_rows in rows_by_scope_and_id.items()
            if scope_key != "all" and candidate_row_id == row_id
            for row in scoped_rows
            if text(row.get("group_id")) in expected_group_ids
        ]
        for row_id in row_ids
    }
    actual_case_rows = [
        row
        for row in group_rows
        if text(row.get("scope_key")) != "all"
        and text(row.get("group_id")) in expected_group_ids
    ]
    expected_row_id_set = set(row_ids)
    actual_row_id_set = {
        row_id
        for row in actual_case_rows
        if (row_id := text(row.get("row_id")))
    }
    missing_row_ids = [row_id for row_id, rows in composed_rows_by_id.items() if not rows]
    if missing_row_ids:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="relation_rows_missing_from_query_composed_case",
                message="Active relation members are missing from the Workbench query-composed canonical case owner.",
                case_id=case_id,
                scope_key="all",
                details={"missing_row_ids": missing_row_ids, "relation_mode": relation_mode},
            )
        )
    derived_display_row_ids = {
        row_id
        for row in actual_case_rows
        if (row_id := text(row.get("row_id")))
        and _is_registered_etc_display_expansion(row, relation=relation)
    }
    extra_row_ids = sorted(actual_row_id_set - expected_row_id_set - derived_display_row_ids)
    if extra_row_ids:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="query_composed_case_rows_not_canonical",
                message="The Workbench query-composed case contains rows absent from the canonical relation.",
                case_id=case_id,
                scope_key="all",
                details={"extra_row_ids": extra_row_ids, "relation_mode": relation_mode},
            )
        )
    for row_index, row_id in enumerate(row_ids):
        rows_for_id = list(composed_rows_by_id.get(row_id) or [])
        row_type = _row_type_at(row_types, row_index)
        if rows_for_id and not any(
            _normalized_display_row_type(row.get("source_kind")) == _normalized_display_row_type(row_type)
            for row in rows_for_id
        ):
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="query_composed_case_row_type_mismatch",
                    message="A Workbench case member type differs from the canonical relation member type.",
                    case_id=case_id,
                    scope_key="all",
                    row_id=row_id,
                    row_type=row_type,
                    details={
                        "projected_source_kinds": sorted(
                            {
                                text(row.get("source_kind")) or ""
                                for row in rows_for_id
                            }
                        )
                    },
                )
            )
        for row in rows_for_id:
            payload = row_payload(row, "payload")
            row_payload_dict = payload if isinstance(payload, dict) else {}
            payload_case_id = text(row_payload_dict.get("case_id") or row_payload_dict.get("relation_id"))
            if payload_case_id and payload_case_id != case_id:
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_row_payload_case_mismatch",
                        message="A relation member row payload points at a different relation case.",
                        case_id=case_id,
                        scope_key=text(row.get("scope_key")) or "",
                        row_id=row_id,
                        row_type=row_type,
                        details={"payload_case_id": payload_case_id},
                    )
                )
            payload_mode = text(row_payload_dict.get("relation_mode"))
            if payload_mode and payload_mode != relation_mode:
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_row_payload_mode_mismatch",
                        message="A relation member row payload has a different relation mode.",
                        case_id=case_id,
                        scope_key=text(row.get("scope_key")) or "",
                        row_id=row_id,
                        row_type=row_type,
                        details={"payload_relation_mode": payload_mode, "relation_mode": relation_mode},
                    )
                )
    return issues


def _is_registered_etc_display_expansion(row: dict[str, Any], *, relation: dict[str, Any]) -> bool:
    external_batch_id = text(relation.get("external_etc_batch_id")) or ""
    if not external_batch_id:
        return False
    source_kind = text(row.get("source_kind")) or ""
    if source_kind not in {"etc_invoice_summary", "etc_invoice"}:
        return False
    payload = row_payload(row, "payload")
    if not isinstance(payload, dict):
        return False
    return text(payload.get("etc_batch_id")) == external_batch_id


def _row_type_at(row_types: list[str], index: int) -> str:
    if index < len(row_types):
        return row_types[index]
    return ""


def _normalized_display_row_type(value: Any) -> str:
    normalized = text(value).lower() if text(value) else ""
    if normalized in {"bank", "bank_transaction"}:
        return "bank"
    if normalized == "oa":
        return "oa"
    if normalized in {
        "input",
        "input_invoice",
        "output",
        "output_invoice",
        "invoice",
        "formal_invoice",
        "oa_attachment_invoice",
    }:
        return "invoice"
    if normalized in {"etc_summary", "etc_invoice_summary"}:
        return "etc_invoice_summary"
    return normalized


def _audit_issue_counts_by_code(issues: list[AuditIssue]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.code] += 1
    return dict(sorted(counts.items()))
