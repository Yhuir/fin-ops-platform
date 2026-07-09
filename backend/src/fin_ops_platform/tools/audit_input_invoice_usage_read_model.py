from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


INPUT_INVOICE_PREDICATE = """
    i.status <> 'deleted'
    and (
        i.invoice_type = 'input'
        or i.invoice_type = 'input_invoice'
        or i.invoice_type like '进项%'
    )
"""

ACTIVE_INPUT_INVOICES_CTE = f"""
active_input_invoices as (
    select
        coalesce(
            nullif(i.raw_payload->'normalized_payload'->>'id', ''),
            nullif(i.legacy_mongo_id, ''),
            i.id::text
        ) as invoice_id,
        i.id::text as postgres_invoice_id,
        i.invoice_type,
        i.invoice_no,
        to_char(coalesce(i.invoice_month, date_trunc('month', i.invoice_date)), 'YYYY-MM') as scope_key,
        coalesce(i.total_with_tax, i.amount, 0)::numeric as total_with_tax,
        i.updated_at::text as updated_at,
        coalesce(source_rows.source_workbench_row_ids, array[]::text[]) as source_workbench_row_ids
    from app.invoices i
    left join lateral (
        select array_agg(distinct nullif(source_link->>'source_workbench_row_id', '')) filter (
            where nullif(source_link->>'source_workbench_row_id', '') is not null
        ) as source_workbench_row_ids
        from jsonb_array_elements(
            case
                when jsonb_typeof(i.source_links) = 'array' then i.source_links
                else '[]'::jsonb
            end
        ) as source_link
        where coalesce(source_link->>'source_type', source_link->>'type', source_link->>'source')
            = 'oa_attachment_invoice'
    ) source_rows on true
    where {INPUT_INVOICE_PREDICATE}
)
"""

INPUT_INVOICE_LOOKUP_CTE = f"""
{ACTIVE_INPUT_INVOICES_CTE},
input_invoice_relation_lookup as (
    select invoice_id, invoice_id as relation_row_id, scope_key
    from active_input_invoices
    union
    select invoice_id, source_row_id as relation_row_id, scope_key
    from active_input_invoices
    cross join lateral unnest(source_workbench_row_ids) as source_row_id
    where nullif(source_row_id, '') is not null
)
"""

READ_MODEL_MEMBERS_CTE = """
read_model_invoice_members as (
    select distinct
        row.scope_key,
        row.row_id,
        row.invoice_id as primary_invoice_id,
        coalesce(nullif(member.value->>'invoiceId', ''), row.invoice_id) as invoice_id,
        row.total_with_tax as row_total_with_tax,
        row.payload,
        row.generated_at::text as generated_at
    from read_model.input_invoice_usage_rows row
    join lateral jsonb_array_elements(
        case
            when jsonb_typeof(row.payload->'invoiceRelations'->'summaries') = 'array'
             and jsonb_array_length(row.payload->'invoiceRelations'->'summaries') > 0
            then row.payload->'invoiceRelations'->'summaries'
            else jsonb_build_array(
                jsonb_build_object(
                    'invoiceId', row.invoice_id,
                    'totalWithTax', row.total_with_tax
                )
            )
        end
    ) as member(value) on true
    where row.cache_status = 'fresh'
)
"""

ACTIVE_RELATION_INPUT_MEMBERS_CTE = f"""
{INPUT_INVOICE_LOOKUP_CTE},
active_relation_input_members as (
    select distinct
        relation.case_id,
        relation.relation_mode,
        to_char(relation.month_scope, 'YYYY-MM') as relation_scope_key,
        lookup.scope_key as invoice_scope_key,
        lookup.invoice_id,
        member.row_id as relation_row_id,
        relation.updated_at::text as relation_updated_at
    from app.workbench_pair_relations relation
    join lateral (
        select
            row_item.row_id,
            relation.row_types[row_item.ordinality] as row_type
        from unnest(relation.row_ids) with ordinality as row_item(row_id, ordinality)
    ) member on true
    join input_invoice_relation_lookup lookup
      on lookup.relation_row_id = member.row_id
    where relation.status = 'active'
)
"""

SUMMARY_SQL = f"""
/* check: summary */
with
{ACTIVE_INPUT_INVOICES_CTE},
{READ_MODEL_MEMBERS_CTE}
select
    (select count(*)::integer from active_input_invoices) as active_input_invoice_count,
    (select coalesce(sum(total_with_tax), 0)::numeric from active_input_invoices) as active_input_invoice_total_with_tax,
    (select count(distinct invoice_id)::integer from read_model_invoice_members) as read_model_invoice_member_count,
    (select count(*)::integer from read_model.input_invoice_usage_rows where cache_status = 'fresh') as read_model_row_count,
    (select count(*)::integer from read_model.input_invoice_usage_scopes) as input_invoice_usage_scope_count,
    (select count(*)::integer from read_model.workbench_relation_scopes where tenant_id = %s) as workbench_relation_scope_count,
    (select count(*)::integer from app.workbench_pair_relations where status = 'active') as active_workbench_pair_relation_count,
    (select count(*)::integer from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked')
        as linked_workbench_relation_group_count
"""


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    subject_id: str = ""
    scope_key: str = ""
    details: dict[str, Any] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit for the input invoice usage read model against canonical "
            "input invoices and Workbench relation distribution."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This tool is read-only either way.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when blocking issues exist.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue code.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        active_connection = connection or _connection_from_env()
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(
            tool="audit_input_invoice_usage_read_model",
            message=str(exc),
        )
        report["required_env"] = [
            "FIN_OPS_POSTGRES_READ_DATABASE_URL",
            "FIN_OPS_POSTGRES_DATABASE_URL",
            "DATABASE_URL",
        ]
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
        return 2
    report = audit_input_invoice_usage_read_model(
        active_connection,
        tenant_id=str(args.tenant_id or "default"),
        example_limit=max(int(args.limit or 50), 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    if args.fail_on_issues and int(report["summary"].get("blocking_issue_count") or 0):
        return 1
    return 0


def audit_input_invoice_usage_read_model(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
) -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    limit = max(int(example_limit or 50), 1)
    summary = _fetch_summary(connection, tenant_id=normalized_tenant_id)
    issues: list[AuditIssue] = []
    checks = (
        _noncanonical_input_invoice_type_issues,
        _dirty_scope_issues,
        _missing_input_scope_issues,
        _input_scope_row_count_mismatch_issues,
        _missing_workbench_relation_scope_issues,
        _source_version_mismatch_issues,
        _missing_read_model_member_issues,
        _orphan_read_model_member_issues,
        _duplicate_invoice_member_issues,
        _amount_mismatch_issues,
        _active_relation_missing_workbench_row_issues,
        _active_relation_missing_workbench_group_issues,
        _cross_scope_relation_distribution_issues,
        _relation_member_split_row_issues,
        _candidate_relation_in_input_usage_issues,
        _candidate_workbench_relation_issues,
    )
    for check in checks:
        issues.extend(check(connection, tenant_id=normalized_tenant_id, limit=limit))

    limited_issues = _limit_issue_examples(issues, example_limit=limit)
    issue_counts_by_code = dict(sorted(Counter(issue.code for issue in issues).items()))
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    summary.update(
        {
            "issue_count": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "blocking_issue_count": error_count,
            "issue_counts_by_code": issue_counts_by_code,
        }
    )
    return {
        "mode": "dry-run",
        "tenant_id": normalized_tenant_id,
        "overall_status": "pass" if error_count == 0 else "issues_found",
        "summary": summary,
        "issues": [asdict(issue) for issue in limited_issues],
        "audit_contract": {
            "source_tables": [
                "app.invoices",
                "app.workbench_pair_relations",
                "read_model.input_invoice_usage_rows",
                "read_model.input_invoice_usage_scopes",
                "read_model.workbench_relation_rows",
                "read_model.workbench_relation_groups",
                "read_model.workbench_relation_scopes",
                "job.read_model_dirty_scopes",
            ],
            "pass_condition": "blocking_issue_count == 0",
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(60_000)
    return connection


def _fetch_summary(connection: Any, *, tenant_id: str) -> dict[str, Any]:
    row = connection.fetch_one(SUMMARY_SQL, (tenant_id, tenant_id)) or {}
    return {
        "active_input_invoice_count": _int(row.get("active_input_invoice_count")),
        "active_input_invoice_total_with_tax": _text(row.get("active_input_invoice_total_with_tax")) or "0",
        "read_model_invoice_member_count": _int(row.get("read_model_invoice_member_count")),
        "read_model_row_count": _int(row.get("read_model_row_count")),
        "input_invoice_usage_scope_count": _int(row.get("input_invoice_usage_scope_count")),
        "workbench_relation_scope_count": _int(row.get("workbench_relation_scope_count")),
        "active_workbench_pair_relation_count": _int(row.get("active_workbench_pair_relation_count")),
        "linked_workbench_relation_group_count": _int(row.get("linked_workbench_relation_group_count")),
    }


def _noncanonical_input_invoice_type_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: noncanonical_input_invoice_type */
        with {ACTIVE_INPUT_INVOICES_CTE}
        select invoice_id, scope_key, invoice_type, invoice_no
        from active_input_invoices
        where invoice_type <> 'input'
        order by scope_key, invoice_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="noncanonical_input_invoice_type",
            message="Input invoice facts use a noncanonical invoice_type that the page service does not read directly.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_type", "invoice_no"),
        )
        for row in rows
    ]


def _dirty_scope_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: dirty_scope */
        select scope_type, scope_key, status, updated_at::text as updated_at, last_error
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type in ('input_invoice_usage', 'workbench_relation')
          and status in ('pending', 'processing', 'failed')
        order by scope_type, scope_key, updated_at desc
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="read_model_scope_not_fresh",
            message="Input invoice usage cannot be guaranteed while a required read model scope is pending, processing, or failed.",
            subject_id=_text(row.get("scope_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in rows
    ]


def _missing_input_scope_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: missing_input_invoice_usage_scope */
        with {ACTIVE_INPUT_INVOICES_CTE}
        select invoices.scope_key, count(*)::integer as invoice_count
        from active_input_invoices invoices
        left join read_model.input_invoice_usage_scopes scope
          on scope.scope_key = invoices.scope_key
        where invoices.scope_key is not null
          and scope.scope_key is null
        group by invoices.scope_key
        order by invoices.scope_key
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="missing_input_invoice_usage_scope",
            message="A month with input invoice facts has no input_invoice_usage scope row.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_count"),
        )
        for row in rows
    ]


def _input_scope_row_count_mismatch_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        """
        /* check: input_scope_row_count_mismatch */
        select
            scope.scope_key,
            scope.row_count::integer as scope_row_count,
            count(row.row_id)::integer as actual_row_count
        from read_model.input_invoice_usage_scopes scope
        left join read_model.input_invoice_usage_rows row
          on row.scope_key = scope.scope_key
        where scope.scope_key <> 'all'
        group by scope.scope_key, scope.row_count
        having scope.row_count <> count(row.row_id)
        order by scope.scope_key
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="input_scope_row_count_mismatch",
            message="input_invoice_usage scope row_count does not match the stored row count.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "scope_row_count", "actual_row_count"),
        )
        for row in rows
    ]


def _missing_workbench_relation_scope_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: missing_workbench_relation_scope */
        with {ACTIVE_INPUT_INVOICES_CTE}
        select invoices.scope_key, count(*)::integer as invoice_count
        from active_input_invoices invoices
        left join read_model.workbench_relation_scopes scope
          on scope.tenant_id = %s
         and scope.scope_key = invoices.scope_key
        where invoices.scope_key is not null
          and scope.scope_key is null
        group by invoices.scope_key
        order by invoices.scope_key
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="missing_workbench_relation_scope",
            message="A month with input invoice facts has no workbench_relation scope proof.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_count"),
        )
        for row in rows
    ]


def _source_version_mismatch_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: source_version_mismatch */
        select
            input_scope.scope_key,
            input_scope.source_versions->'workbench_relation_source_versions' as embedded_relation_versions,
            relation_scope.source_versions as current_relation_versions
        from read_model.input_invoice_usage_scopes input_scope
        join read_model.workbench_relation_scopes relation_scope
          on relation_scope.tenant_id = %s
         and relation_scope.scope_key = input_scope.scope_key
        where input_scope.scope_key <> 'all'
          and exists (
              select 1
              from read_model.input_invoice_usage_rows row
              where row.scope_key = input_scope.scope_key
          )
          and coalesce(input_scope.source_versions->'workbench_relation_source_versions', '{}'::jsonb)
              <> coalesce(relation_scope.source_versions, '{}'::jsonb)
        order by input_scope.scope_key
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="input_usage_relation_source_versions_mismatch",
            message="input_invoice_usage scope was built with stale workbench_relation source_versions.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "embedded_relation_versions", "current_relation_versions"),
        )
        for row in rows
    ]


def _missing_read_model_member_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: missing_read_model_member */
        with
        {ACTIVE_INPUT_INVOICES_CTE},
        {READ_MODEL_MEMBERS_CTE}
        select
            invoices.invoice_id,
            invoices.invoice_no,
            invoices.invoice_type,
            invoices.scope_key,
            invoices.total_with_tax
        from active_input_invoices invoices
        left join read_model_invoice_members member
          on member.invoice_id = invoices.invoice_id
        where member.invoice_id is null
        order by invoices.scope_key, invoices.invoice_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="missing_input_invoice_usage_member",
            message="An active input invoice is missing from read_model.input_invoice_usage_rows.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_no", "invoice_type", "total_with_tax"),
        )
        for row in rows
    ]


def _orphan_read_model_member_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: orphan_read_model_member */
        with
        {ACTIVE_INPUT_INVOICES_CTE},
        {READ_MODEL_MEMBERS_CTE}
        select
            member.invoice_id,
            member.scope_key,
            member.row_id,
            member.generated_at
        from read_model_invoice_members member
        left join active_input_invoices invoices
          on invoices.invoice_id = member.invoice_id
        where invoices.invoice_id is null
        order by member.scope_key, member.invoice_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="orphan_input_invoice_usage_member",
            message="A read model row references an invoice that is not an active input invoice fact.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_id", "generated_at"),
        )
        for row in rows
    ]


def _duplicate_invoice_member_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: duplicate_invoice_member */
        with {READ_MODEL_MEMBERS_CTE}
        select
            scope_key,
            invoice_id,
            count(distinct row_id)::integer as row_count,
            array_agg(distinct row_id order by row_id) as row_ids
        from read_model_invoice_members
        group by scope_key, invoice_id
        having count(distinct row_id) > 1
        order by scope_key, invoice_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="duplicate_input_invoice_usage_member",
            message="The same input invoice appears in multiple read model rows within one scope.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_count", "row_ids"),
        )
        for row in rows
    ]


def _amount_mismatch_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: amount_mismatch */
        with
        {ACTIVE_INPUT_INVOICES_CTE},
        {READ_MODEL_MEMBERS_CTE},
        row_amounts as (
            select
                member.scope_key,
                member.row_id,
                sum(invoices.total_with_tax)::numeric as app_total_with_tax,
                max(member.row_total_with_tax)::numeric as native_row_total_with_tax,
                max(
                    case
                        when member.payload->'invoice'->>'totalWithTax' ~ '^-?[0-9]+(\\.[0-9]+)?$'
                        then (member.payload->'invoice'->>'totalWithTax')::numeric
                    end
                ) as payload_total_with_tax,
                count(distinct member.invoice_id)::integer as invoice_member_count
            from read_model_invoice_members member
            join active_input_invoices invoices
              on invoices.invoice_id = member.invoice_id
            group by member.scope_key, member.row_id
        )
        select *
        from row_amounts
        where abs(coalesce(app_total_with_tax, 0) - coalesce(payload_total_with_tax, 0)) > 0.01
           or abs(coalesce(native_row_total_with_tax, 0) - coalesce(payload_total_with_tax, 0)) > 0.01
        order by scope_key, row_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="input_invoice_usage_amount_mismatch",
            message="Read model invoice total does not match canonical invoice member totals.",
            subject_id=_text(row.get("row_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(
                row,
                "app_total_with_tax",
                "native_row_total_with_tax",
                "payload_total_with_tax",
                "invoice_member_count",
            ),
        )
        for row in rows
    ]


def _active_relation_missing_workbench_row_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: active_relation_missing_workbench_row */
        with {ACTIVE_RELATION_INPUT_MEMBERS_CTE}
        select
            member.case_id,
            member.invoice_id,
            member.relation_row_id,
            member.invoice_scope_key as scope_key,
            member.relation_updated_at
        from active_relation_input_members member
        left join read_model.workbench_relation_rows relation_row
          on relation_row.tenant_id = %s
         and relation_row.row_id = member.relation_row_id
         and relation_row.relation_status = 'linked'
         and member.case_id = any(relation_row.group_ids)
        where relation_row.row_id is null
        order by member.case_id, member.relation_row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="active_relation_missing_workbench_relation_row",
            message="An active Workbench relation input invoice member is not projected as a linked workbench_relation row.",
            subject_id=_text(row.get("case_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "relation_row_id", "relation_updated_at"),
        )
        for row in rows
    ]


def _active_relation_missing_workbench_group_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: active_relation_missing_workbench_group */
        with {ACTIVE_RELATION_INPUT_MEMBERS_CTE}
        select
            member.case_id,
            member.invoice_id,
            member.relation_row_id,
            member.invoice_scope_key as scope_key
        from active_relation_input_members member
        left join read_model.workbench_relation_groups relation_group
          on relation_group.tenant_id = %s
         and relation_group.group_id = member.case_id
         and relation_group.relation_status = 'linked'
         and (
                member.relation_row_id = any(relation_group.input_invoice_ids)
             or member.invoice_id = any(relation_group.input_invoice_ids)
         )
        where relation_group.group_id is null
        order by member.case_id, member.relation_row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="active_relation_missing_workbench_relation_group",
            message="An active Workbench relation input invoice member is not projected in a linked relation group.",
            subject_id=_text(row.get("case_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "relation_row_id"),
        )
        for row in rows
    ]


def _cross_scope_relation_distribution_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: cross_scope_relation_distribution */
        with
        {ACTIVE_RELATION_INPUT_MEMBERS_CTE},
        relation_scopes as (
            select distinct case_id, invoice_scope_key as scope_key
            from active_relation_input_members
            where invoice_scope_key is not null
            union
            select distinct case_id, relation_scope_key as scope_key
            from active_relation_input_members
            where relation_scope_key is not null
        )
        select
            member.case_id,
            member.invoice_id,
            member.relation_row_id,
            relation_scopes.scope_key
        from active_relation_input_members member
        join relation_scopes
          on relation_scopes.case_id = member.case_id
        left join read_model.workbench_relation_rows relation_row
          on relation_row.tenant_id = %s
         and relation_row.scope_key = relation_scopes.scope_key
         and relation_row.row_id = member.relation_row_id
         and relation_row.relation_status = 'linked'
         and member.case_id = any(relation_row.group_ids)
        where relation_row.row_id is null
        order by member.case_id, relation_scopes.scope_key, member.relation_row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="cross_scope_relation_member_not_distributed",
            message="A cross-scope active relation member is missing from one affected workbench_relation scope.",
            subject_id=_text(row.get("case_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "relation_row_id"),
        )
        for row in rows
    ]


def _relation_member_split_row_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: relation_member_split_row */
        with
        {ACTIVE_RELATION_INPUT_MEMBERS_CTE},
        {READ_MODEL_MEMBERS_CTE}
        select
            relation_member.case_id,
            read_member.scope_key,
            count(distinct read_member.row_id)::integer as row_count,
            array_agg(distinct read_member.row_id order by read_member.row_id) as row_ids,
            array_agg(distinct relation_member.invoice_id order by relation_member.invoice_id) as invoice_ids
        from active_relation_input_members relation_member
        join read_model_invoice_members read_member
          on read_member.invoice_id = relation_member.invoice_id
        group by relation_member.case_id, read_member.scope_key
        having count(distinct read_member.row_id) > 1
        order by relation_member.case_id, read_member.scope_key
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="active_relation_members_split_across_input_usage_rows",
            message="Input invoices from the same active relation are split across multiple page rows in one scope.",
            subject_id=_text(row.get("case_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_count", "row_ids", "invoice_ids"),
        )
        for row in rows
    ]


def _candidate_relation_in_input_usage_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    candidate_exists_sql = """
        exists (
            select 1
            from jsonb_array_elements(
                case
                    when jsonb_typeof(row.payload->%s->'summaries') = 'array'
                    then row.payload->%s->'summaries'
                    else '[]'::jsonb
                end
            ) as summary(value)
            where coalesce(summary.value->>'relationStatus', summary.value->>'relation_status') = 'candidate'
        )
    """
    rows = connection.fetch_all(
        f"""
        /* check: candidate_relation_in_input_usage */
        select row.scope_key, row.row_id, row.invoice_id, row.payment_status
        from read_model.input_invoice_usage_rows row
        where {candidate_exists_sql}
           or {candidate_exists_sql}
           or {candidate_exists_sql}
        order by row.scope_key, row.row_id
        limit %s
        """,
        (
            "oa",
            "oa",
            "bankTransactions",
            "bankTransactions",
            "invoiceRelations",
            "invoiceRelations",
            limit,
        ),
    )
    return [
        AuditIssue(
            severity="error",
            code="candidate_relation_projected_into_input_usage",
            message="A candidate relation appears inside input invoice usage relation summaries.",
            subject_id=_text(row.get("row_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "payment_status"),
        )
        for row in rows
    ]


def _candidate_workbench_relation_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: candidate_workbench_relation */
        with {INPUT_INVOICE_LOOKUP_CTE}
        select
            relation_row.scope_key,
            relation_row.row_id,
            relation_row.row_type,
            relation_row.group_ids,
            lookup.invoice_id
        from read_model.workbench_relation_rows relation_row
        join input_invoice_relation_lookup lookup
          on lookup.relation_row_id = relation_row.row_id
        where relation_row.tenant_id = %s
          and relation_row.relation_status = 'candidate'
        order by relation_row.scope_key, relation_row.row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    issues = [
        AuditIssue(
            severity="error",
            code="candidate_workbench_relation_for_input_invoice",
            message="A candidate workbench_relation row exists for an input invoice relation lookup id.",
            subject_id=_text(row.get("row_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "row_type", "group_ids"),
        )
        for row in rows
    ]
    group_rows = connection.fetch_all(
        """
        /* check: candidate_workbench_relation_group */
        select scope_key, group_id, input_invoice_ids
        from read_model.workbench_relation_groups
        where tenant_id = %s
          and relation_status = 'candidate'
          and coalesce(array_length(input_invoice_ids, 1), 0) > 0
        order by scope_key, group_id
        limit %s
        """,
        (tenant_id, limit),
    )
    issues.extend(
        AuditIssue(
            severity="error",
            code="candidate_workbench_relation_group_for_input_invoice",
            message="A candidate workbench_relation group contains input invoice members.",
            subject_id=_text(row.get("group_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "input_invoice_ids"),
        )
        for row in group_rows
    )
    return issues


def _limit_issue_examples(issues: list[AuditIssue], *, example_limit: int) -> list[AuditIssue]:
    counts: dict[str, int] = {}
    result: list[AuditIssue] = []
    for issue in issues:
        count = counts.get(issue.code, 0)
        if count < example_limit:
            result.append(issue)
        counts[issue.code] = count + 1
    return result


def _details(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
