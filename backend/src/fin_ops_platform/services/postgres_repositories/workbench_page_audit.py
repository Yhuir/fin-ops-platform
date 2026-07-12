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
    workbench_projection_integrity_issues,
)


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
    audit_issues.extend(_dirty_scope_issues(connection, tenant_id=tenant_id, limit=example_limit + 1))
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
                "their all-scope union, and every active relation member"
            ),
            "key_display_fields": [
                "object identity",
                "scope and source kind",
                "OA applicant/project/amount",
                "bank direction/amount/counterparty",
                "invoice identity/type/date/amount",
                "ETC batch members/count/amount",
                "case/mode/group owner/row alignment",
                "ignored and handled-exception ownership",
                "generation and summary counts",
                "source dependency versions",
            ],
            "relation_edge_equality": (
                "canonical == relation_groups == relation_rows == active Workbench generation display ownership"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "proof_checks": [
                "canonical_object_expected_set_equality",
                "active_month_and_all_scope_union_equality",
                "generation_row_group_summary_counts",
                "bidirectional_relation_edge_equality",
                "active_generation_relation_display",
                "single_visible_group_owner",
                "case_mode_and_multi_oa_alignment",
                "all_scope_generation_order",
                "visible_automatic_decision_exclusion",
                "durable_queue_and_freshness_gate",
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
) -> tuple[list[AuditIssue], dict[str, Any]]:
    """Collect Workbench integrity proof inside the caller-owned read-only snapshot."""
    relations = [_normalize_relation(row) for row in _fetch_active_relations(connection)]
    active_generations = _fetch_active_generations(connection, tenant_id=tenant_id)
    relation_row_ids = sorted(
        {
            row_id
            for relation in relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id or "").strip()
        }
    )
    group_rows = _fetch_active_group_rows(connection, tenant_id=tenant_id, row_ids=relation_row_ids)
    automatic_decision_group_rows = _fetch_visible_automatic_decision_group_rows(
        connection,
        tenant_id=tenant_id,
        limit=limit,
    )
    generation_by_scope = {str(row.get("scope_key") or ""): row for row in active_generations}
    rows_by_scope_and_id = _rows_by_scope_and_row_id(group_rows)
    issues: list[RelationDisplayIssue] = []

    if relations and "all" not in generation_by_scope:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="missing_all_active_generation",
                message="Active relations exist but Workbench all scope has no active generation.",
                case_id="*",
                scope_key="all",
            )
        )

    for relation in relations:
        issues.extend(
            _relation_display_issues(
                relation,
                rows_by_scope_and_id=rows_by_scope_and_id,
                generation_by_scope=generation_by_scope,
            )
        )
    issues.extend(_visible_automatic_decision_issues(automatic_decision_group_rows))
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
    all_generation = generation_by_scope.get("all") or {}
    return audit_issues, {
        "active_relation_count": len(relations),
        "active_generation_scope_count": len(active_generations),
        "audited_relation_row_id_count": len(relation_row_ids),
        "active_group_row_count": len(group_rows),
        "visible_automatic_decision_row_count": len(automatic_decision_group_rows),
        "all_generation_id": all_generation.get("generation_id"),
        "all_generation_activated_at": all_generation.get("activated_at"),
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
        order by scope_key
        """,
        (tenant_id,),
    )


def _fetch_active_group_rows(connection: Any, *, tenant_id: str, row_ids: list[str]) -> list[dict[str, Any]]:
    if not row_ids:
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
          gr.payload
        from read_model.workbench_generations gen
        join read_model.workbench_group_rows gr
          on gr.generation_id = gen.generation_id
         and gr.scope_key = gen.scope_key
        where gen.tenant_id = %s
          and gen.status = 'active'
          and gr.row_role <> 'summary'
          and gr.row_id = any(%s)
        order by gen.scope_key, gr.row_id, gr.group_id
        """,
        (tenant_id, row_ids),
    )


def _fetch_visible_automatic_decision_group_rows(connection: Any, *, tenant_id: str, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
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
          gr.payload
        from read_model.workbench_generations gen
        join read_model.workbench_group_rows gr
          on gr.generation_id = gen.generation_id
         and gr.scope_key = gen.scope_key
        where gen.tenant_id = %s
          and gen.status = 'active'
          and gr.row_role <> 'summary'
          and (
            gr.group_id like 'case:decision:%%'
            or gr.payload->>'relation_mode' = 'automatic_decision'
            or gr.payload->>'case_id' like 'decision:%%'
            or gr.payload ? 'workbench_reconciliation_decision'
          )
        order by gen.scope_key, gr.group_id, gr.row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [row for row in rows if _row_is_visible_automatic_decision(row)]


def _normalize_relation(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "raw_payload")
    relation_payload = payload if isinstance(payload, dict) else {}
    row_ids = text_list(row.get("row_ids")) or text_list(relation_payload.get("row_ids"))
    row_types = text_list(row.get("row_types")) or text_list(relation_payload.get("row_types"))
    return {
        "case_id": text(row.get("case_id") or relation_payload.get("case_id")) or "",
        "relation_mode": text(row.get("relation_mode") or relation_payload.get("relation_mode")) or "",
        "status": text(row.get("status") or relation_payload.get("status")) or "active",
        "row_ids": row_ids,
        "row_types": row_types,
        "month_scope": text(row.get("month_scope") or relation_payload.get("month_scope")) or "",
        "updated_at": text(row.get("updated_at")) or "",
    }


def _rows_by_scope_and_row_id(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        scope_key = text(row.get("scope_key")) or ""
        row_id = text(row.get("row_id")) or ""
        if scope_key and row_id:
            grouped[(scope_key, row_id)].append(row)
    return grouped


def _visible_automatic_decision_issues(rows: list[dict[str, Any]]) -> list[RelationDisplayIssue]:
    issues: list[RelationDisplayIssue] = []
    for row in rows:
        payload = row_payload(row, "payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        group_id = text(row.get("group_id")) or ""
        row_id = text(row.get("row_id")) or text(payload_dict.get("id")) or ""
        pane = text(row.get("pane") or payload_dict.get("type") or payload_dict.get("source_kind")) or ""
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="visible_automatic_decision_group",
                message="Active Workbench generation contains visible automatic decision rows; same-row display must come from active linked relations only.",
                case_id=group_id,
                scope_key=text(row.get("scope_key")) or "",
                row_id=row_id,
                row_type=pane,
                details={
                    "group_id": group_id,
                    "payload_case_id": text(payload_dict.get("case_id")) or "",
                    "payload_relation_mode": text(payload_dict.get("relation_mode")) or "",
                },
            )
        )
    return issues


def _row_is_visible_automatic_decision(row: dict[str, Any]) -> bool:
    group_id = text(row.get("group_id")) or ""
    if group_id.startswith("case:decision:"):
        return True
    payload = row_payload(row, "payload")
    payload_dict = payload if isinstance(payload, dict) else {}
    if text(payload_dict.get("relation_mode")) == "automatic_decision":
        return True
    case_id = text(payload_dict.get("case_id"))
    if case_id and case_id.startswith("decision:"):
        return True
    return isinstance(payload_dict.get("workbench_reconciliation_decision"), dict)


def _relation_display_issues(
    relation: dict[str, Any],
    *,
    rows_by_scope_and_id: dict[tuple[str, str], list[dict[str, Any]]],
    generation_by_scope: dict[str, dict[str, Any]],
) -> list[RelationDisplayIssue]:
    case_id = str(relation.get("case_id") or "")
    row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or []) if str(row_id or "").strip()]
    row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
    relation_mode = str(relation.get("relation_mode") or "")
    issues: list[RelationDisplayIssue] = []
    if not case_id or not row_ids:
        return issues

    all_rows_by_id = {row_id: list(rows_by_scope_and_id.get(("all", row_id), [])) for row_id in row_ids}
    missing_all = [row_id for row_id, rows in all_rows_by_id.items() if not rows]
    if missing_all:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="relation_rows_missing_from_all_generation",
                message="Active relation members are missing from the active Workbench all generation.",
                case_id=case_id,
                scope_key="all",
                details={"missing_row_ids": missing_all, "relation_mode": relation_mode},
            )
        )

    issues.extend(
        _scope_group_issues(
            case_id=case_id,
            relation_mode=relation_mode,
            row_ids=row_ids,
            row_types=row_types,
            scope_key="all",
            rows_by_id=all_rows_by_id,
            require_complete=not missing_all,
        )
    )

    relation_scopes = sorted(
        {
            scope_key
            for (scope_key, row_id), rows in rows_by_scope_and_id.items()
            if scope_key != "all" and row_id in set(row_ids) and rows
        }
    )
    all_generation = generation_by_scope.get("all")
    all_activated_at = text((all_generation or {}).get("activated_at")) or ""
    for scope_key in relation_scopes:
        scope_rows_by_id = {row_id: list(rows_by_scope_and_id.get((scope_key, row_id), [])) for row_id in row_ids}
        missing_scope = [row_id for row_id, rows in scope_rows_by_id.items() if not rows]
        if missing_scope:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="relation_rows_missing_from_member_scope_generation",
                    message="Active relation members are not complete in a member Workbench month scope.",
                    case_id=case_id,
                    scope_key=scope_key,
                    details={"missing_row_ids": missing_scope, "relation_mode": relation_mode},
                )
            )
        issues.extend(
            _scope_group_issues(
                case_id=case_id,
                relation_mode=relation_mode,
                row_ids=row_ids,
                row_types=row_types,
                scope_key=scope_key,
                rows_by_id=scope_rows_by_id,
                require_complete=not missing_scope,
            )
        )
        scope_generation = generation_by_scope.get(scope_key) or {}
        scope_activated_at = text(scope_generation.get("activated_at")) or ""
        if all_activated_at and scope_activated_at and scope_activated_at > all_activated_at:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="all_generation_older_than_member_scope_generation",
                    message="Workbench all generation is older than a member month scope generation.",
                    case_id=case_id,
                    scope_key=scope_key,
                    details={
                        "all_activated_at": all_activated_at,
                        "member_scope_activated_at": scope_activated_at,
                        "all_generation_id": (all_generation or {}).get("generation_id"),
                        "member_generation_id": scope_generation.get("generation_id"),
                    },
                )
            )
    return issues


def _scope_group_issues(
    *,
    case_id: str,
    relation_mode: str,
    row_ids: list[str],
    row_types: list[str],
    scope_key: str,
    rows_by_id: dict[str, list[dict[str, Any]]],
    require_complete: bool,
) -> list[RelationDisplayIssue]:
    issues: list[RelationDisplayIssue] = []
    rows = [row for row_id in row_ids for row in rows_by_id.get(row_id, [])]
    group_ids = sorted({str(row.get("group_id") or "") for row in rows if str(row.get("group_id") or "").strip()})
    if require_complete and len(group_ids) > 1:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="relation_rows_split_across_groups",
                message="Active relation members are visible in more than one Workbench group.",
                case_id=case_id,
                scope_key=scope_key,
                details={"group_ids": group_ids, "relation_mode": relation_mode},
            )
        )
    expected_group_ids = {case_id, f"case:{case_id}"}
    if require_complete and len(group_ids) == 1 and group_ids[0] not in expected_group_ids:
        issues.append(
            RelationDisplayIssue(
                severity="warning",
                code="relation_group_id_not_case_based",
                message="Active relation members are grouped together but not under the canonical case group id.",
                case_id=case_id,
                scope_key=scope_key,
                details={"group_id": group_ids[0], "expected_group_ids": sorted(expected_group_ids)},
            )
        )
    for row_index, row_id in enumerate(row_ids):
        rows_for_id = list(rows_by_id.get(row_id) or [])
        row_type = _row_type_at(row_types, row_index)
        distinct_groups = sorted({str(row.get("group_id") or "") for row in rows_for_id if str(row.get("group_id") or "").strip()})
        if len(distinct_groups) > 1:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="relation_row_duplicate_visible_owner",
                    message="A relation member row has multiple visible owners in one active Workbench scope.",
                    case_id=case_id,
                    scope_key=scope_key,
                    row_id=row_id,
                    row_type=row_type,
                    details={"group_ids": distinct_groups},
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
                        scope_key=scope_key,
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
                        scope_key=scope_key,
                        row_id=row_id,
                        row_type=row_type,
                        details={"payload_relation_mode": payload_mode, "relation_mode": relation_mode},
                    )
                )
            if (
                require_complete
                and _relation_has_multiple_oa_rows(row_types)
                and row_type == "bank"
                and not _payload_source_oa_id(row_payload_dict)
            ):
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_bank_row_missing_source_oa_alignment",
                        message="A bank row in a multi-OA active relation is missing row-level source OA alignment evidence.",
                        case_id=case_id,
                        scope_key=scope_key,
                        row_id=row_id,
                        row_type=row_type,
                        details={
                            "relation_mode": relation_mode,
                            "expected_fields": ["source_oa_id", "source_oa_row_id", "derived_from_oa_id"],
                        },
                    )
                )
    return issues


def _row_type_at(row_types: list[str], index: int) -> str:
    if index < len(row_types):
        return row_types[index]
    return ""


def _relation_has_multiple_oa_rows(row_types: list[str]) -> bool:
    return sum(1 for row_type in row_types if str(row_type or "").strip() == "oa") >= 2


def _payload_source_oa_id(payload: dict[str, Any]) -> str:
    for key in ("source_oa_id", "source_oa_row_id", "derived_from_oa_id", "oa_row_id", "oa_id"):
        value = text(payload.get(key))
        if value:
            return value
    detail_fields = payload.get("detail_fields")
    if isinstance(detail_fields, dict):
        for key in ("source_oa_id", "source_oa_row_id", "derived_from_oa_id", "oa_row_id", "oa_id"):
            value = text(detail_fields.get(key))
            if value:
                return value
    return ""


def _audit_issue_counts_by_code(issues: list[AuditIssue]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.code] += 1
    return dict(sorted(counts.items()))
