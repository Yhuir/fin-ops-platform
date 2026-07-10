from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import re
import sys
from typing import Any, TextIO

from fin_ops_platform.services.pending_invoice_status import pending_invoice_filter_status_codes
from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_.]+$")


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    subject_id: str = ""
    scope_key: str = ""
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class PageAuditContract:
    domain_key: str
    label: str
    source_tables: tuple[str, ...]
    read_model_tables: tuple[str, ...]
    relation_tables: tuple[str, ...] = ()
    scope_types: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()


PAGE_AUDIT_CONTRACTS: dict[str, PageAuditContract] = {
    "pending_invoices": PageAuditContract(
        domain_key="pending_invoices",
        label="待找发票",
        source_tables=("app.bank_transactions", "app.bank_transaction_categories"),
        read_model_tables=("read_model.pending_invoice_rows", "read_model.pending_invoice_scopes"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("pending_invoice", "bank_detail", "workbench_relation", "invoice_lifecycle"),
        event_types=(
            "pending_invoice.read_model.refresh",
            "bank_detail.read_model.refresh",
            "workbench_relation.read_model.refresh",
            "invoice_lifecycle.read_model.refresh",
        ),
    ),
    "turnover_ledger": PageAuditContract(
        domain_key="turnover_ledger",
        label="外部往来款管理",
        source_tables=("app.turnover_relations", "app.turnover_ledger_extras"),
        read_model_tables=("read_model.turnover_ledger_rows",),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("turnover_ledger", "bank_detail", "workbench_relation"),
        event_types=(
            "turnover_ledger.read_model.refresh",
            "bank_detail.read_model.refresh",
            "workbench_relation.read_model.refresh",
        ),
    ),
    "batch_accounting": PageAuditContract(
        domain_key="batch_accounting",
        label="批量账务",
        source_tables=("app.workbench_pair_relations",),
        read_model_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups", "read_model.workbench_relation_scopes"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("workbench_relation",),
        event_types=("workbench_relation.read_model.refresh",),
    ),
    "bank_flow_rule_batches": PageAuditContract(
        domain_key="bank_flow_rule_batches",
        label="流水规则批量处理",
        source_tables=("app.bank_flow_rule_batches", "app.bank_flow_rule_batch_events"),
        read_model_tables=("read_model.bank_flow_rule_batch_rows",),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("bank_flow_rule_batch", "workbench_relation"),
        event_types=("bank_flow_rule_batch.read_model.refresh", "workbench_relation.read_model.refresh"),
    ),
    "oa_pending_payments": PageAuditContract(
        domain_key="oa_pending_payments",
        label="OA 代付款核对",
        source_tables=("app.oa_applications", "app.oa_application_items"),
        read_model_tables=("read_model.oa_pending_payment_rows", "read_model.oa_pending_payment_scopes"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("oa_pending_payment", "workbench_relation", "invoice_lifecycle"),
        event_types=(
            "oa_pending_payment.read_model.refresh",
            "workbench_relation.read_model.refresh",
            "invoice_lifecycle.read_model.refresh",
            "oa.sync",
        ),
    ),
    "bank_details": PageAuditContract(
        domain_key="bank_details",
        label="银行明细",
        source_tables=("app.bank_transactions", "app.bank_transaction_categories"),
        read_model_tables=("read_model.bank_detail_rows", "read_model.bank_detail_scopes", "read_model.bank_account_balances"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("bank_detail", "bank_account_balance", "workbench_relation"),
        event_types=(
            "bank_detail.read_model.refresh",
            "bank_account_balance.read_model.refresh",
            "workbench_relation.read_model.refresh",
            "bank_transaction_import",
        ),
    ),
    "cost_statistics": PageAuditContract(
        domain_key="cost_statistics",
        label="成本统计",
        source_tables=("app.bank_transactions", "app.turnover_relations", "app.workbench_pair_relations"),
        read_model_tables=("read_model.cost_statistics_read_models", "read_model.cost_statistics_rows"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("cost_statistics", "bank_detail", "workbench_relation"),
        event_types=(
            "cost_statistics.read_model.refresh",
            "bank_detail.read_model.refresh",
            "workbench_relation.read_model.refresh",
        ),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only page business read-model audit.")
    parser.add_argument("domain_key", choices=sorted(PAGE_AUDIT_CONTRACTS))
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
            tool="audit_page_business_read_model",
            message=str(exc),
        )
        report["required_env"] = [
            "FIN_OPS_POSTGRES_READ_DATABASE_URL",
            "FIN_OPS_POSTGRES_DATABASE_URL",
            "DATABASE_URL",
        ]
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
        return 2
    report = audit_page_business_read_model(
        active_connection,
        domain_key=str(args.domain_key),
        tenant_id=str(args.tenant_id or "default"),
        example_limit=max(int(args.limit or 50), 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    if args.fail_on_issues and int(report["summary"].get("blocking_issue_count") or 0):
        return 1
    return 0


def audit_page_business_read_model(
    connection: Any,
    *,
    domain_key: str,
    tenant_id: str = "default",
    example_limit: int = 50,
) -> dict[str, Any]:
    normalized_domain_key = str(domain_key or "").strip()
    contract = PAGE_AUDIT_CONTRACTS.get(normalized_domain_key)
    if contract is None:
        raise ValueError(f"Unsupported page audit domain: {domain_key}")
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    limit = max(int(example_limit or 50), 1)
    summary = _fetch_summary(connection, contract=contract, tenant_id=normalized_tenant_id)
    issues: list[AuditIssue] = []
    checks: tuple[Callable[[Any, PageAuditContract, str, int], list[AuditIssue]], ...] = (
        _dirty_scope_issues,
        _outbox_backlog_issues,
        _scope_row_count_mismatch_issues,
        _read_model_source_version_mismatch_issues,
        _missing_read_model_scope_issues,
        _missing_read_model_row_issues,
        _orphan_read_model_row_issues,
        _duplicate_read_model_identity_issues,
        _relation_distribution_issues,
        _candidate_relation_projection_issues,
    )
    for check in checks:
        issues.extend(check(connection, contract, normalized_tenant_id, limit))

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
            "fresh": error_count == 0,
        }
    )
    return {
        "mode": "page-business-read-model-audit",
        "tenant_id": normalized_tenant_id,
        "domain_key": contract.domain_key,
        "label": contract.label,
        "overall_status": "pass" if error_count == 0 else "issues_found",
        "summary": summary,
        "issues": [asdict(issue) for issue in limited_issues],
        "audit_contract": {
            "source_tables": list(contract.source_tables),
            "read_model_tables": list(contract.read_model_tables),
            "relation_tables": list(contract.relation_tables),
            "scope_types": list(contract.scope_types),
            "event_types": list(contract.event_types),
            "pass_condition": "blocking_issue_count == 0",
            "guarantee_boundary": (
                "App-internal canonical facts, read_model rows/scopes/source_versions, "
                "durable refresh state, and projected relation distribution agree for this page."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(60_000)
    return connection


def _fetch_summary(connection: Any, *, contract: PageAuditContract, tenant_id: str) -> dict[str, Any]:
    sql, params = _summary_sql(contract, tenant_id=tenant_id)
    row = connection.fetch_one(sql, params) or {}
    return {
        "source_fact_count": _int(row.get("source_fact_count")),
        "read_model_row_count": _int(row.get("read_model_row_count")),
        "read_model_scope_count": _int(row.get("read_model_scope_count")),
        "active_relation_count": _int(row.get("active_relation_count")),
        "linked_relation_group_count": _int(row.get("linked_relation_group_count")),
        "dirty_scope_count": _int(row.get("dirty_scope_count")),
        "outbox_backlog_count": _int(row.get("outbox_backlog_count")),
    }


def _summary_sql(contract: PageAuditContract, *, tenant_id: str) -> tuple[str, tuple[Any, ...]]:
    domain = contract.domain_key
    scope_types = _quoted_list(contract.scope_types)
    event_types = _quoted_list(contract.event_types)
    if domain == "bank_details":
        source_sql = "select count(*) from app.bank_transactions where status <> 'deleted'"
        row_sql = "select count(*) from read_model.bank_detail_rows where tenant_id = %s"
        scope_sql = "select count(*) from read_model.bank_detail_scopes where tenant_id = %s and scope_type in ('bank_detail', 'bank_account_balance')"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active'"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked'"
        params: tuple[Any, ...] = (tenant_id, tenant_id, tenant_id)
    elif domain == "pending_invoices":
        source_sql = """
        select count(*)
        from read_model.pending_invoice_rows row
        join app.bank_transactions source
          on coalesce(source.legacy_mongo_id, source.id::text) = row.row_id
         and source.status <> 'deleted'
         and source.txn_direction = case when row.direction = 'expense' then 'outflow' else 'inflow' end
        """
        row_sql = "select count(*) from read_model.pending_invoice_rows"
        scope_sql = "select count(*) from read_model.pending_invoice_scopes"
        relation_sql = """
        select count(distinct relation.case_id)
        from app.workbench_pair_relations relation
        join lateral unnest(relation.row_ids) with ordinality as member(row_id, ordinality) on true
        join read_model.pending_invoice_rows pending_row
          on pending_row.row_id = member.row_id
        where relation.status = 'active'
          and relation.row_types[member.ordinality] in ('bank', 'bank_transaction')
        """
        linked_sql = """
        select count(distinct relation_group.group_id)
        from read_model.workbench_relation_rows relation_row
        join read_model.pending_invoice_rows pending_row
          on pending_row.row_id = relation_row.row_id
        join read_model.workbench_relation_groups relation_group
          on relation_group.tenant_id = relation_row.tenant_id
         and relation_group.scope_key = relation_row.scope_key
         and relation_group.group_id = any(relation_row.group_ids)
         and relation_group.relation_status = 'linked'
        where relation_row.tenant_id = %s
          and relation_row.row_type = 'bank_transaction'
          and relation_row.relation_status = 'linked'
        """
        params = (tenant_id,)
    elif domain == "oa_pending_payments":
        source_sql = "select count(*) from app.oa_applications where status <> 'deleted'"
        row_sql = "select count(distinct row_id) from read_model.oa_pending_payment_rows"
        scope_sql = "select count(*) from read_model.oa_pending_payment_scopes"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active' and 'oa' = any(row_types)"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked' and cardinality(oa_row_ids) > 0"
        params = (tenant_id,)
    elif domain == "batch_accounting":
        source_sql = "select count(*) from app.workbench_pair_relations where status = 'active' and special_metadata->>'source' = 'batch_accounting'"
        row_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked' and payload->'special_metadata'->>'source' = 'batch_accounting'"
        scope_sql = "select count(*) from read_model.workbench_relation_scopes where tenant_id = %s"
        relation_sql = source_sql
        linked_sql = row_sql
        params = (tenant_id, tenant_id, tenant_id)
    elif domain == "bank_flow_rule_batches":
        source_sql = "select count(*) from app.bank_flow_rule_batches where status <> 'deleted'"
        row_sql = "select count(*) from read_model.bank_flow_rule_batch_rows where cache_status = 'fresh'"
        scope_sql = "select count(distinct to_char(scope_month, 'YYYY-MM')) from read_model.bank_flow_rule_batch_rows where scope_month is not null"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active'"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked'"
        params = (tenant_id,)
    elif domain == "turnover_ledger":
        source_sql = "select count(*) from app.turnover_relations where status <> 'deleted'"
        row_sql = "select count(*) from read_model.turnover_ledger_rows where cache_status = 'fresh'"
        scope_sql = "select count(distinct to_char(scope_month, 'YYYY-MM')) from read_model.turnover_ledger_rows where scope_month is not null"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active'"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked'"
        params = (tenant_id,)
    elif domain == "cost_statistics":
        source_sql = "select count(*) from app.bank_transactions where status <> 'deleted'"
        row_sql = "select count(*) from read_model.cost_statistics_rows where cache_status = 'fresh'"
        scope_sql = "select count(*) from read_model.cost_statistics_read_models"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active'"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked'"
        params = (tenant_id,)
    else:
        raise ValueError(f"Unsupported page audit domain: {domain}")
    return f"""
    /* check: summary */
    select
        ({source_sql})::integer as source_fact_count,
        ({row_sql})::integer as read_model_row_count,
        ({scope_sql})::integer as read_model_scope_count,
        ({relation_sql})::integer as active_relation_count,
        ({linked_sql})::integer as linked_relation_group_count,
        (
            select count(*)::integer
            from job.read_model_dirty_scopes
            where scope_type in ({scope_types})
              and status in ('pending', 'processing', 'failed')
        ) as dirty_scope_count,
        (
            select count(*)::integer
            from job.outbox_events
            where event_type in ({event_types})
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
        ) as outbox_backlog_count
    """, params


def _dirty_scope_issues(connection: Any, contract: PageAuditContract, tenant_id: str, limit: int) -> list[AuditIssue]:
    if not contract.scope_types:
        return []
    rows = connection.fetch_all(
        f"""
        /* check: dirty_scope */
        select scope_type, scope_key, status, updated_at::text as updated_at, last_error
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type in ({_quoted_list(contract.scope_types)})
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
            message=f"{contract.label} cannot be guaranteed while a required read model scope is pending, processing, or failed.",
            subject_id=_text(row.get("scope_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in rows
    ]


def _outbox_backlog_issues(connection: Any, contract: PageAuditContract, tenant_id: str, limit: int) -> list[AuditIssue]:
    _ = tenant_id
    if not contract.event_types:
        return []
    rows = connection.fetch_all(
        f"""
        /* check: outbox_backlog */
        select event_type, coalesce(scope_key, aggregate_id, '') as scope_key, status, updated_at::text as updated_at, last_error
        from job.outbox_events
        where event_type in ({_quoted_list(contract.event_types)})
          and status in ('pending', 'processing', 'failed', 'dead_lettered')
        order by event_type, updated_at desc
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code="read_model_outbox_not_drained",
            message=f"{contract.label} cannot be guaranteed while a required refresh/outbox event is not drained.",
            subject_id=_text(row.get("event_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in rows
    ]


def _scope_row_count_mismatch_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        sql = """
        /* check: scope_row_count_mismatch */
        select scope.scope_type, scope.scope_key, scope.row_count::integer as scope_row_count,
               count(row.transaction_id)::integer as actual_row_count
        from read_model.bank_detail_scopes scope
        left join read_model.bank_detail_rows row
          on row.tenant_id = scope.tenant_id
         and row.scope_key = scope.scope_key
        where scope.tenant_id = %s
          and scope.scope_type = 'bank_detail'
        group by scope.scope_type, scope.scope_key, scope.row_count
        having scope.row_count <> count(row.transaction_id)
        order by scope.scope_key
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "pending_invoices":
        sql = """
        /* check: scope_row_count_mismatch */
        with scopes as (
            select scope_key, direction, filter_group, row_count,
                   substring(scope_key from '([0-9]{4}-[0-9]{2})$') as scope_month_key
            from read_model.pending_invoice_scopes
        )
        select scope.scope_key, scope.row_count::integer as scope_row_count,
               count(row.row_id)::integer as actual_row_count
        from scopes scope
        left join read_model.pending_invoice_rows row
          on row.direction = scope.direction
         and (scope.scope_month_key is null or row.scope_month = (scope.scope_month_key || '-01')::date)
         and (""" + _pending_invoice_visible_scope_condition_sql() + """)
        group by scope.scope_key, scope.row_count
        having scope.row_count <> count(row.row_id)
        order by scope.scope_key
        limit %s
        """
        params = (limit,)
    elif domain == "oa_pending_payments":
        sql = """
        /* check: scope_row_count_mismatch */
        select scope.scope_key, scope.row_count::integer as scope_row_count,
               count(row.row_id)::integer as actual_row_count
        from read_model.oa_pending_payment_scopes scope
        left join read_model.oa_pending_payment_rows row
          on row.scope_key = scope.scope_key
        group by scope.scope_key, scope.row_count
        having scope.row_count <> count(row.row_id)
        order by scope.scope_key
        limit %s
        """
        params = (limit,)
    elif domain == "batch_accounting":
        sql = """
        /* check: scope_row_count_mismatch */
        select scope.scope_key, scope.group_count::integer as scope_group_count,
               count(group_row.group_id)::integer as actual_group_count
        from read_model.workbench_relation_scopes scope
        left join read_model.workbench_relation_groups group_row
          on group_row.tenant_id = scope.tenant_id
         and group_row.scope_key = scope.scope_key
        where scope.tenant_id = %s
        group by scope.scope_key, scope.group_count
        having scope.group_count <> count(group_row.group_id)
        order by scope.scope_key
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "cost_statistics":
        sql = """
        /* check: scope_row_count_mismatch */
        select model.scope_key, model.entry_count::integer as scope_row_count,
               count(row.row_key)::integer as actual_row_count
        from read_model.cost_statistics_read_models model
        left join read_model.cost_statistics_rows row
          on row.scope_key = model.scope_key
        where model.scope_key !~ ':(all)$'
        group by model.scope_key, model.entry_count
        having model.entry_count <> count(row.row_key)
        order by model.scope_key
        limit %s
        """
        params = (limit,)
    else:
        return []
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_scope_row_count_mismatch",
            message=f"{contract.label} scope row_count does not match stored row count.",
            subject_id=_text(row.get("scope_type")),
            scope_key=_text(row.get("scope_key")),
            details={key: _jsonable(value) for key, value in row.items() if key not in {"scope_type", "scope_key"}},
        )
        for row in rows
    ]


def _read_model_source_version_mismatch_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    queries: list[tuple[str, tuple[Any, ...], str]] = []
    if domain == "bank_details":
        queries.append(
            (
                """
                /* check: source_versions_mismatch */
                select row.scope_key, row.transaction_id as subject_id,
                       row.source_versions as row_source_versions,
                       scope.source_versions as scope_source_versions
                from read_model.bank_detail_rows row
                join read_model.bank_detail_scopes scope
                  on scope.tenant_id = row.tenant_id
                 and scope.scope_type = 'bank_detail'
                 and scope.scope_key = row.scope_key
                where row.tenant_id = %s
                  and coalesce(row.source_versions, '{}'::jsonb) <> coalesce(scope.source_versions, '{}'::jsonb)
                order by row.scope_key, row.transaction_id
                limit %s
                """,
                (tenant_id, limit),
                "bank_details_row_source_versions_mismatch",
            )
        )
        queries.append(_embedded_relation_versions_query(domain, "read_model.bank_detail_scopes", "scope", tenant_id, limit))
    elif domain == "pending_invoices":
        queries = []
    elif domain == "oa_pending_payments":
        queries.append(
            (
                """
                /* check: source_versions_mismatch */
                select row.scope_key, row.row_id as subject_id,
                       row.source_versions as row_source_versions,
                       scope.source_versions as scope_source_versions
                from read_model.oa_pending_payment_rows row
                join read_model.oa_pending_payment_scopes scope
                  on scope.scope_key = row.scope_key
                where coalesce(row.source_versions, '{}'::jsonb) <> coalesce(scope.source_versions, '{}'::jsonb)
                order by row.scope_key, row.row_id
                limit %s
                """,
                (limit,),
                "oa_pending_payments_row_source_versions_mismatch",
            )
        )
        queries.append(_embedded_relation_versions_query(domain, "read_model.oa_pending_payment_scopes", "scope", tenant_id, limit))
    elif domain == "bank_flow_rule_batches":
        queries.append(
            (
                """
                /* check: source_business_fields_mismatch */
                select read_model.batch_id as subject_id,
                       to_char(read_model.scope_month, 'YYYY-MM') as scope_key,
                       source.status as source_status,
                       read_model.status as read_model_status,
                       source.status_bucket as source_status_bucket,
                       read_model.status_bucket as read_model_status_bucket,
                       source.account_key as source_account_key,
                       read_model.account_key as read_model_account_key,
                       source.total_amount::text as source_total_amount,
                       read_model.total_amount::text as read_model_total_amount,
                       cardinality(source.bank_transaction_ids)::integer as source_row_count,
                       read_model.row_count::integer as read_model_row_count
                from read_model.bank_flow_rule_batch_rows read_model
                join app.bank_flow_rule_batches source
                  on source.batch_id = read_model.batch_id
                where source.status <> 'deleted'
                  and (
                        coalesce(read_model.status, '') <> coalesce(source.status, '')
                     or coalesce(read_model.status_bucket, '') <> coalesce(source.status_bucket, '')
                     or coalesce(read_model.account_key, '') <> coalesce(source.account_key, '')
                     or abs(coalesce(read_model.total_amount, 0) - coalesce(source.total_amount, 0)) > 0.01
                     or coalesce(read_model.row_count, 0) <> coalesce(cardinality(source.bank_transaction_ids), 0)
                  )
                order by read_model.batch_id
                limit %s
                """,
                (limit,),
                "bank_flow_rule_batches_business_fields_mismatch",
            )
        )
    elif domain == "cost_statistics":
        queries.append(
            (
                """
                /* check: source_versions_mismatch */
                select row.scope_key, row.row_key as subject_id,
                       row.source_versions as row_source_versions,
                       model.source_versions as scope_source_versions
                from read_model.cost_statistics_rows row
                join read_model.cost_statistics_read_models model
                  on model.scope_key = row.scope_key
                where coalesce(row.source_versions, '{}'::jsonb) <> coalesce(model.source_versions, '{}'::jsonb)
                order by row.scope_key, row.row_key
                limit %s
                """,
                (limit,),
                "cost_statistics_row_source_versions_mismatch",
            )
        )
    elif domain == "turnover_ledger":
        queries.append(
            (
                """
                /* check: source_business_fields_mismatch */
                select row.relation_id as subject_id,
                       to_char(row.scope_month, 'YYYY-MM') as scope_key,
                       source.status as source_status,
                       row.status as read_model_status,
                       source.relation_type as source_relation_type,
                       row.relation_type as read_model_relation_type,
                       source.counterparty_name as source_counterparty_name,
                       row.counterparty_name as read_model_counterparty_name,
                       source.amount::text as source_amount,
                       row.amount::text as read_model_amount,
                       source.bank_transaction_id as source_bank_transaction_id,
                       row.bank_row_ids as read_model_bank_row_ids
                from read_model.turnover_ledger_rows row
                join app.turnover_relations source
                  on source.relation_id = row.relation_id
                where source.status <> 'deleted'
                  and (
                        coalesce(row.status, '') <> coalesce(source.status, '')
                     or coalesce(row.relation_type, '') <> coalesce(source.relation_type, '')
                     or coalesce(row.counterparty_name, '') <> coalesce(source.counterparty_name, '')
                     or abs(coalesce(row.amount, 0) - coalesce(source.amount, 0)) > 0.01
                     or (
                            nullif(source.bank_transaction_id, '') is not null
                        and not source.bank_transaction_id = any(row.bank_row_ids)
                     )
                  )
                order by row.relation_id
                limit %s
                """,
                (limit,),
                "turnover_ledger_business_fields_mismatch",
            )
        )
    issues: list[AuditIssue] = []
    for sql, params, code in queries:
        rows = connection.fetch_all(sql, params)
        issues.extend(
            AuditIssue(
                severity="error",
                code=code,
                message=f"{contract.label} read model does not match the required source proof.",
                subject_id=_text(row.get("subject_id")),
                scope_key=_text(row.get("scope_key")),
                details={
                    key: _jsonable(value)
                    for key, value in row.items()
                    if key not in {"subject_id", "scope_key"}
                },
            )
            for row in rows
        )
    return issues


def _missing_read_model_scope_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        sql = """
        /* check: missing_read_model_scope */
        select source.scope_key, count(*)::integer as source_count
        from (
            select to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where status <> 'deleted'
              and txn_month is not null
        ) source
        left join read_model.bank_detail_scopes scope
          on scope.tenant_id = %s
         and scope.scope_type = 'bank_detail'
         and scope.scope_key = source.scope_key
        where scope.scope_key is null
        group by source.scope_key
        order by source.scope_key
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "pending_invoices":
        sql = """
        /* check: missing_read_model_scope */
        with expected_scopes as (
            select distinct
                case when txn_direction = 'outflow' then 'expense' else 'income' end
                || ':all:' || to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where status <> 'deleted'
              and txn_direction in ('outflow', 'inflow')
              and txn_month is not null
        )
        select expected.scope_key, count(*)::integer as source_count
        from expected_scopes expected
        left join read_model.pending_invoice_scopes scope
          on scope.scope_key = expected.scope_key
        where scope.scope_key is null
        group by expected.scope_key
        order by expected.scope_key
        limit %s
        """
        params = (limit,)
    elif domain == "oa_pending_payments":
        sql = """
        /* check: missing_read_model_scope */
        select row.scope_key, count(*)::integer as source_count
        from read_model.oa_pending_payment_rows row
        left join read_model.oa_pending_payment_scopes scope
          on scope.scope_key = row.scope_key
        where scope.scope_key is null
        group by row.scope_key
        order by row.scope_key
        limit %s
        """
        params = (limit,)
    elif domain == "cost_statistics":
        sql = """
        /* check: missing_read_model_scope */
        with expected_scopes as (
            select project_scope || ':' || to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            cross join (values ('active'), ('all')) scopes(project_scope)
            where status <> 'deleted'
              and txn_month is not null
            group by project_scope, txn_month
        )
        select expected.scope_key, count(*)::integer as source_count
        from expected_scopes expected
        left join read_model.cost_statistics_read_models model
          on model.scope_key = expected.scope_key
        where model.scope_key is null
        group by expected.scope_key
        order by expected.scope_key
        limit %s
        """
        params = (limit,)
    else:
        return []
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_missing_read_model_scope",
            message=f"{contract.label} has canonical source facts without a required read model scope.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "source_count"),
        )
        for row in rows
    ]


def _missing_read_model_row_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        sql = """
        /* check: missing_read_model_row */
        select coalesce(source.legacy_mongo_id, source.id::text) as subject_id,
               to_char(source.txn_month, 'YYYY-MM') as scope_key,
               source.amount::text as amount
        from app.bank_transactions source
        left join read_model.bank_detail_rows row
          on row.tenant_id = %s
         and row.transaction_id = source.id::text
        where source.status <> 'deleted'
          and row.transaction_id is null
        order by source.txn_month, source.id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "pending_invoices":
        return []
    elif domain == "bank_flow_rule_batches":
        sql = """
        /* check: missing_read_model_row */
        select source.batch_id as subject_id,
               to_char(source.scope_month, 'YYYY-MM') as scope_key,
               source.status, source.total_amount::text as total_amount
        from app.bank_flow_rule_batches source
        left join read_model.bank_flow_rule_batch_rows row
          on row.batch_id = source.batch_id
        where source.status <> 'deleted'
          and row.batch_id is null
        order by source.scope_month, source.batch_id
        limit %s
        """
        params = (limit,)
    elif domain == "turnover_ledger":
        sql = """
        /* check: missing_read_model_row */
        select source.relation_id as subject_id,
               to_char(source.scope_month, 'YYYY-MM') as scope_key,
               source.status, source.amount::text as amount
        from app.turnover_relations source
        left join read_model.turnover_ledger_rows row
          on row.relation_id = source.relation_id
        where source.status <> 'deleted'
          and row.relation_id is null
        order by source.scope_month, source.relation_id
        limit %s
        """
        params = (limit,)
    elif domain == "batch_accounting":
        sql = """
        /* check: missing_read_model_row */
        select relation.case_id as subject_id,
               to_char(relation.month_scope, 'YYYY-MM') as scope_key,
               relation.version
        from app.workbench_pair_relations relation
        left join read_model.workbench_relation_groups group_row
          on group_row.tenant_id = %s
         and group_row.group_id = relation.case_id
         and group_row.relation_status = 'linked'
        where relation.status = 'active'
          and relation.special_metadata->>'source' = 'batch_accounting'
          and group_row.group_id is null
        order by relation.month_scope, relation.case_id
        limit %s
        """
        params = (tenant_id, limit)
    else:
        return []
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_missing_read_model_row",
            message=f"{contract.label} has canonical source facts missing from the page read model.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={key: _jsonable(value) for key, value in row.items() if key not in {"subject_id", "scope_key"}},
        )
        for row in rows
    ]


def _orphan_read_model_row_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        sql = """
        /* check: orphan_read_model_row */
        select row.transaction_id as subject_id, row.scope_key, row.amount::text as amount
        from read_model.bank_detail_rows row
        left join app.bank_transactions source
          on source.id::text = row.transaction_id
         and source.status <> 'deleted'
        where row.tenant_id = %s
          and source.id is null
        order by row.scope_key, row.transaction_id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "pending_invoices":
        sql = """
        /* check: orphan_read_model_row */
        select row.row_id as subject_id, row.scope_key, row.direction, row.amount::text as amount
        from read_model.pending_invoice_rows row
        left join app.bank_transactions source
          on coalesce(source.legacy_mongo_id, source.id::text) = row.row_id
         and source.status <> 'deleted'
         and source.txn_direction = case when row.direction = 'expense' then 'outflow' else 'inflow' end
        where source.id is null
        order by row.scope_key, row.row_id
        limit %s
        """
        params = (limit,)
    elif domain == "oa_pending_payments":
        sql = """
        /* check: orphan_read_model_row */
        select row.oa_id as subject_id, row.scope_key, row.row_id
        from read_model.oa_pending_payment_rows row
        left join app.oa_applications source
          on source.row_id = row.oa_id
         and source.status <> 'deleted'
        where nullif(row.oa_id, '') is not null
          and source.id is null
        order by row.scope_key, row.oa_id
        limit %s
        """
        params = (limit,)
    elif domain == "bank_flow_rule_batches":
        sql = """
        /* check: orphan_read_model_row */
        select row.batch_id as subject_id, to_char(row.scope_month, 'YYYY-MM') as scope_key
        from read_model.bank_flow_rule_batch_rows row
        left join app.bank_flow_rule_batches source
          on source.batch_id = row.batch_id
         and source.status <> 'deleted'
        where source.id is null
        order by row.scope_month, row.batch_id
        limit %s
        """
        params = (limit,)
    elif domain == "turnover_ledger":
        sql = """
        /* check: orphan_read_model_row */
        select row.relation_id as subject_id, to_char(row.scope_month, 'YYYY-MM') as scope_key
        from read_model.turnover_ledger_rows row
        left join app.turnover_relations source
          on source.relation_id = row.relation_id
         and source.status <> 'deleted'
        where source.id is null
        order by row.scope_month, row.relation_id
        limit %s
        """
        params = (limit,)
    elif domain == "batch_accounting":
        sql = """
        /* check: orphan_read_model_row */
        select group_row.group_id as subject_id, group_row.scope_key
        from read_model.workbench_relation_groups group_row
        left join app.workbench_pair_relations relation
          on relation.case_id = group_row.group_id
         and relation.status = 'active'
         and relation.special_metadata->>'source' = 'batch_accounting'
        where group_row.tenant_id = %s
          and group_row.relation_status = 'linked'
          and group_row.payload->'special_metadata'->>'source' = 'batch_accounting'
          and relation.id is null
        order by group_row.scope_key, group_row.group_id
        limit %s
        """
        params = (tenant_id, limit)
    else:
        return []
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_orphan_read_model_row",
            message=f"{contract.label} read model contains rows whose canonical source fact is no longer active.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={key: _jsonable(value) for key, value in row.items() if key not in {"subject_id", "scope_key"}},
        )
        for row in rows
    ]


def _duplicate_read_model_identity_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        sql = """
        /* check: duplicate_read_model_identity */
        select transaction_id as subject_id, count(*)::integer as row_count
        from read_model.bank_detail_rows
        where tenant_id = %s
        group by transaction_id
        having count(*) > 1
        order by transaction_id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "pending_invoices":
        sql = """
        /* check: duplicate_read_model_identity */
        select direction || ':' || row_id as subject_id, count(*)::integer as row_count
        from read_model.pending_invoice_rows
        group by direction, row_id
        having count(*) > 1
        order by subject_id
        limit %s
        """
        params = (limit,)
    elif domain == "oa_pending_payments":
        sql = """
        /* check: duplicate_read_model_identity */
        select scope_key || ':' || row_id as subject_id, scope_key, count(*)::integer as row_count
        from read_model.oa_pending_payment_rows
        group by scope_key, row_id
        having count(*) > 1
        order by scope_key, row_id
        limit %s
        """
        params = (limit,)
    elif domain == "bank_flow_rule_batches":
        sql = """
        /* check: duplicate_read_model_identity */
        select batch_id as subject_id, count(*)::integer as row_count
        from read_model.bank_flow_rule_batch_rows
        group by batch_id
        having count(*) > 1
        order by batch_id
        limit %s
        """
        params = (limit,)
    elif domain == "turnover_ledger":
        sql = """
        /* check: duplicate_read_model_identity */
        select relation_id as subject_id, count(*)::integer as row_count
        from read_model.turnover_ledger_rows
        group by relation_id
        having count(*) > 1
        order by relation_id
        limit %s
        """
        params = (limit,)
    elif domain == "batch_accounting":
        sql = """
        /* check: duplicate_read_model_identity */
        select scope_key || ':' || group_id as subject_id, scope_key, count(*)::integer as row_count
        from read_model.workbench_relation_groups
        where tenant_id = %s
          and payload->'special_metadata'->>'source' = 'batch_accounting'
        group by scope_key, group_id
        having count(*) > 1
        order by scope_key, group_id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "cost_statistics":
        sql = """
        /* check: duplicate_read_model_identity */
        select scope_key || ':' || row_key as subject_id, scope_key, count(*)::integer as row_count
        from read_model.cost_statistics_rows
        group by scope_key, row_key
        having count(*) > 1
        order by scope_key, row_key
        limit %s
        """
        params = (limit,)
    else:
        return []
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_duplicate_read_model_identity",
            message=f"{contract.label} read model has duplicate business row identities.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_count"),
        )
        for row in rows
    ]


def _relation_distribution_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain not in {
        "pending_invoices",
        "oa_pending_payments",
        "bank_details",
        "bank_flow_rule_batches",
        "turnover_ledger",
        "batch_accounting",
        "cost_statistics",
    }:
        return []
    relation_filter = "true"
    if domain == "batch_accounting":
        relation_filter = "relation.special_metadata->>'source' = 'batch_accounting'"
    if domain == "pending_invoices":
        rows = connection.fetch_all(
            f"""
            /* check: relation_distribution */
            with active_relation_members as (
                select distinct
                    relation.case_id,
                    coalesce(to_char(relation.month_scope, 'YYYY-MM'), '') as scope_key,
                    member.row_id,
                    relation.row_types[member.ordinality] as row_type,
                    relation.updated_at::text as relation_updated_at
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality as member(row_id, ordinality) on true
                join read_model.pending_invoice_rows pending_row
                  on pending_row.row_id = member.row_id
                where relation.status = 'active'
                  and relation.row_types[member.ordinality] in ('bank', 'bank_transaction')
                  and {relation_filter}
            )
            select member.case_id as subject_id, member.scope_key, member.row_id, member.row_type, member.relation_updated_at
            from active_relation_members member
            where not exists (
                select 1
                from read_model.workbench_relation_rows relation_row
                join read_model.workbench_relation_groups relation_group
                  on relation_group.tenant_id = relation_row.tenant_id
                 and relation_group.scope_key = relation_row.scope_key
                 and relation_group.group_id = member.case_id
                 and relation_group.relation_status = 'linked'
                where relation_row.tenant_id = %s
                  and relation_row.row_id = member.row_id
                  and relation_row.relation_status = 'linked'
                  and member.case_id = any(relation_row.group_ids)
            )
            order by member.case_id, member.row_id
            limit %s
            """,
            (tenant_id, limit),
        )
        return [
            AuditIssue(
                severity="error",
                code=f"{domain}_active_relation_missing_distribution",
                message=f"{contract.label} has active Workbench relations missing from the relation read model distribution.",
                subject_id=_text(row.get("subject_id")),
                scope_key=_text(row.get("scope_key")),
                details=_details(row, "row_id", "row_type", "relation_updated_at"),
            )
            for row in rows
        ]
    rows = connection.fetch_all(
        f"""
        /* check: relation_distribution */
        with active_relation_members as (
            select
                relation.case_id,
                to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                member.row_id,
                relation.row_types[member.ordinality] as row_type,
                relation.updated_at::text as relation_updated_at
            from app.workbench_pair_relations relation
            join lateral unnest(relation.row_ids) with ordinality as member(row_id, ordinality) on true
            where relation.status = 'active'
              and {relation_filter}
        )
        select member.case_id as subject_id, member.scope_key, member.row_id, member.row_type, member.relation_updated_at
        from active_relation_members member
        left join read_model.workbench_relation_rows relation_row
          on relation_row.tenant_id = %s
         and relation_row.scope_key = member.scope_key
         and relation_row.row_id = member.row_id
         and relation_row.relation_status = 'linked'
         and member.case_id = any(relation_row.group_ids)
        left join read_model.workbench_relation_groups relation_group
          on relation_group.tenant_id = %s
         and relation_group.scope_key = member.scope_key
         and relation_group.group_id = member.case_id
         and relation_group.relation_status = 'linked'
        where relation_row.row_id is null
           or relation_group.group_id is null
        order by member.case_id, member.row_id
        limit %s
        """,
        (tenant_id, tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"{domain}_active_relation_missing_distribution",
            message=f"{contract.label} has active Workbench relations missing from the relation read model distribution.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_id", "row_type", "relation_updated_at"),
        )
        for row in rows
    ]


def _candidate_relation_projection_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    group_filter = _relation_group_filter(contract.domain_key)
    rows = connection.fetch_all(
        f"""
        /* check: candidate_relation_projection */
        select group_row.group_id as subject_id, group_row.scope_key, group_row.relation_status,
               coalesce((
                   select relation.status
                   from app.workbench_pair_relations relation
                   where relation.case_id = group_row.group_id
                   order by relation.updated_at desc
                   limit 1
               ), '') as canonical_status
        from read_model.workbench_relation_groups group_row
        where group_row.tenant_id = %s
          and group_row.relation_status = 'linked'
          and ({group_filter})
          and not exists (
              select 1
              from app.workbench_pair_relations active_relation
              where active_relation.case_id = group_row.group_id
                and active_relation.status = 'active'
          )
        order by group_row.scope_key, group_row.group_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"{contract.domain_key}_candidate_relation_projected_as_linked",
            message=f"{contract.label} relation read model projects a non-active relation as linked.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "relation_status", "canonical_status"),
        )
        for row in rows
    ]


def _relation_group_filter(domain: str) -> str:
    if domain == "batch_accounting":
        return "group_row.payload->'special_metadata'->>'source' = 'batch_accounting'"
    if domain == "oa_pending_payments":
        return "cardinality(group_row.oa_row_ids) > 0"
    if domain in {"bank_details", "bank_flow_rule_batches", "turnover_ledger", "cost_statistics"}:
        return "cardinality(group_row.bank_transaction_ids) > 0"
    if domain == "pending_invoices":
        return (
            "exists ("
            "select 1 "
            "from unnest(group_row.bank_transaction_ids) as pending_bank(row_id) "
            "join read_model.pending_invoice_rows pending_row "
            "on pending_row.row_id = pending_bank.row_id"
            ")"
        )
    return "true"


def _embedded_relation_versions_query(
    domain: str,
    scope_table: str,
    alias: str,
    tenant_id: str,
    limit: int,
) -> tuple[str, tuple[Any, ...], str]:
    _assert_identifier(scope_table)
    tenant_join = "and relation_scope.tenant_id = %s"
    params: tuple[Any, ...] = (tenant_id, limit)
    return (
        f"""
        /* check: source_versions_mismatch */
        select {alias}.scope_key,
               {alias}.source_versions->'workbench_relation_source_versions' as embedded_relation_versions,
               relation_scope.source_versions as current_relation_versions
        from {scope_table} {alias}
        join read_model.workbench_relation_scopes relation_scope
          on relation_scope.scope_key = coalesce(
                nullif(substring({alias}.scope_key from '([0-9]{{4}}-[0-9]{{2}})$'), ''),
                {alias}.scope_key
             )
         {tenant_join}
        where {alias}.scope_key <> 'all'
          and {alias}.source_versions ? 'workbench_relation_source_versions'
          and coalesce({alias}.source_versions->'workbench_relation_source_versions', '{{}}'::jsonb)
              <> coalesce(relation_scope.source_versions, '{{}}'::jsonb)
        order by {alias}.scope_key
        limit %s
        """,
        params,
        f"{domain}_relation_source_versions_mismatch",
    )


def _embedded_bank_detail_versions_query(
    domain: str,
    scope_table: str,
    alias: str,
    tenant_id: str,
    limit: int,
) -> tuple[str, tuple[Any, ...], str]:
    _assert_identifier(scope_table)
    return (
        f"""
        /* check: source_versions_mismatch */
        select {alias}.scope_key,
               {alias}.source_versions->'bank_detail_source_versions' as embedded_bank_detail_versions,
               bank_scope.source_versions as current_bank_detail_versions
        from {scope_table} {alias}
        join read_model.bank_detail_scopes bank_scope
          on bank_scope.scope_key = substring({alias}.scope_key from '([0-9]{{4}}-[0-9]{{2}})$')
         and bank_scope.tenant_id = %s
         and bank_scope.scope_type = 'bank_detail'
        where {alias}.scope_key <> 'all'
          and {alias}.source_versions ? 'bank_detail_source_versions'
          and coalesce({alias}.source_versions->'bank_detail_source_versions', '{{}}'::jsonb)
              <> coalesce(bank_scope.source_versions, '{{}}'::jsonb)
        order by {alias}.scope_key
        limit %s
        """,
        (tenant_id, limit),
        f"{domain}_bank_detail_source_versions_mismatch",
    )


def _limit_issue_examples(issues: list[AuditIssue], *, example_limit: int) -> list[AuditIssue]:
    limits: Counter[str] = Counter()
    limited: list[AuditIssue] = []
    for issue in issues:
        if limits[issue.code] >= example_limit:
            continue
        limited.append(issue)
        limits[issue.code] += 1
    return limited


def _quoted_list(values: tuple[str, ...]) -> str:
    safe_values = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        safe_values.append("'" + normalized.replace("'", "''") + "'")
    if not safe_values:
        return "''"
    return ", ".join(safe_values)


def _pending_invoice_visible_scope_condition_sql() -> str:
    conditions = ["scope.filter_group = 'all'"]
    for direction, filters in (
        ("expense", ("requires_invoice", "bank_statement_as_invoice", "no_invoice_required")),
        ("income", ("requires_invoice", "no_invoice_required", "cash_income")),
    ):
        for filter_name in filters:
            status_codes = pending_invoice_filter_status_codes(direction=direction, filter_name=filter_name)
            if not status_codes:
                continue
            conditions.append(
                "("
                f"scope.direction = '{direction}' "
                f"and scope.filter_group = '{filter_name}' "
                f"and row.status_code in ({_quoted_list(tuple(status_codes))})"
                ")"
            )
    return " or ".join(conditions)


def _assert_identifier(value: str) -> None:
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value}")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _details(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: _jsonable(row.get(key)) for key in keys if key in row}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
