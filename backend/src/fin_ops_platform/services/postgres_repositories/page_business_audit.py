from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any

from fin_ops_platform.services.pending_invoice_status import pending_invoice_filter_status_codes
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.page_consumer_relation_audit import (
    BANK_DETAIL_TAG_CONSUMER,
    BANK_FLOW_RULE_BATCH_CONSUMER,
    BATCH_ACCOUNTING_DIRECT_CONSUMER,
    OA_PENDING_PAYMENT_CONSUMER,
    PENDING_INVOICE_CONSUMER,
    TURNOVER_LEDGER_CONSUMER,
    page_consumer_relation_edge_equality_issues,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation_audit import (
    workbench_relation_edge_equality_issues,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    collect_workbench_page_integrity_issues,
)


_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_.]+$")


@dataclass(frozen=True)
class PageAuditContract:
    domain_key: str
    label: str
    source_tables: tuple[str, ...]
    read_model_tables: tuple[str, ...]
    relation_tables: tuple[str, ...] = ()
    scope_types: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    canonical_expected_set: str = ""
    key_display_fields: tuple[str, ...] = ()
    external_source_boundary: str = ""
    consumer_relation_contract: str | None = None


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
        canonical_expected_set="active bank transactions by direction/month, including every collapsed relation member",
        key_display_fields=("transaction_id", "direction", "scope_month", "trade_date", "amount", "counterparty_name", "status_code"),
        external_source_boundary="bank statement completeness before App import",
        consumer_relation_contract=PENDING_INVOICE_CONSUMER,
    ),
    "turnover_ledger": PageAuditContract(
        domain_key="turnover_ledger",
        label="外部往来款管理",
        source_tables=(
            "app.bank_transactions",
            "app.turnover_relations",
            "app.turnover_ledger_extras",
            "app.app_settings",
        ),
        read_model_tables=("read_model.turnover_ledger_rows",),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("turnover_ledger", "bank_detail", "workbench_relation"),
        event_types=(
            "turnover_ledger.read_model.refresh",
            "bank_detail.read_model.refresh",
            "workbench_relation.read_model.refresh",
        ),
        canonical_expected_set="eligible effective bank-detail turnover leaves, retained manual relations, and ledger extras",
        key_display_fields=(
            "family",
            "counterparty_name",
            "amount breakdown",
            "pending direction",
            "bank_row_ids",
            "interest fields",
        ),
        external_source_boundary="bank statement completeness before App import",
        consumer_relation_contract=TURNOVER_LEDGER_CONSUMER,
    ),
    "batch_accounting": PageAuditContract(
        domain_key="batch_accounting",
        label="批量账务",
        source_tables=("app.workbench_pair_relations",),
        read_model_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups", "read_model.workbench_relation_scopes"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("workbench_relation",),
        event_types=("workbench_relation.read_model.refresh",),
        canonical_expected_set="active batch_accounting Workbench pair relations",
        key_display_fields=("case_id", "relation_mode", "member edges", "special_metadata"),
        external_source_boundary="OA and bank source completeness before App registration",
        consumer_relation_contract=BATCH_ACCOUNTING_DIRECT_CONSUMER,
    ),
    "bank_flow_rule_batches": PageAuditContract(
        domain_key="bank_flow_rule_batches",
        label="流水规则批量处理",
        source_tables=("app.bank_flow_rule_batches", "app.bank_flow_rule_batch_events"),
        read_model_tables=("read_model.bank_flow_rule_batch_rows",),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("bank_flow_rule_batch", "workbench_relation"),
        event_types=("bank_flow_rule_batch.read_model.refresh", "workbench_relation.read_model.refresh"),
        canonical_expected_set="non-deleted bank flow rule batches and their exact bank-transaction member sets",
        key_display_fields=("batch_id", "status", "status_bucket", "account_key", "total_amount", "row_count"),
        external_source_boundary="bank statement completeness before App import",
        consumer_relation_contract=BANK_FLOW_RULE_BATCH_CONSUMER,
    ),
    "oa_pending_payments": PageAuditContract(
        domain_key="oa_pending_payments",
        label="OA 代付款核对",
        source_tables=(
            "app.oa_applications",
            "app.oa_application_items",
            "app.oa_pending_payment_admissions",
        ),
        read_model_tables=("read_model.oa_pending_payment_rows", "read_model.oa_pending_payment_scopes"),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("oa_pending_payment", "workbench_relation", "invoice_lifecycle"),
        event_types=(
            "oa_pending_payment.read_model.refresh",
            "workbench_relation.read_model.refresh",
            "invoice_lifecycle.read_model.refresh",
            "oa.sync",
        ),
        canonical_expected_set="completed App OA records plus externally admitted in-progress OA records already registered in App",
        key_display_fields=("oa_id", "workflow_status", "applicant", "project_name", "amount", "relation members", "payment_status"),
        external_source_boundary="OA source completeness and t_payment_simple admission completeness",
        consumer_relation_contract=OA_PENDING_PAYMENT_CONSUMER,
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
        canonical_expected_set="all active bank transactions and deterministic account-balance identities",
        key_display_fields=("transaction_id", "scope_month", "trade_date", "direction", "amount", "counterparty_name", "account balance"),
        external_source_boundary="bank statement completeness before App import",
        consumer_relation_contract=BANK_DETAIL_TAG_CONSUMER,
    ),
    "cost_statistics": PageAuditContract(
        domain_key="cost_statistics",
        label="成本统计",
        source_tables=(
            "app.bank_transactions",
            "app.oa_applications",
            "app.workbench_pair_relations",
            "app.bank_transaction_categories",
            "app.app_settings",
        ),
        read_model_tables=(
            "read_model.cost_statistics_read_models",
            "read_model.cost_statistics_rows",
            "read_model.workbench_generations",
            "read_model.workbench_groups",
            "read_model.workbench_group_rows",
            "read_model.bank_detail_rows",
            "read_model.bank_detail_scopes",
        ),
        relation_tables=("read_model.workbench_relation_rows", "read_model.workbench_relation_groups"),
        scope_types=("cost_statistics", "bank_detail", "workbench_relation"),
        event_types=(
            "cost_statistics.read_model.refresh",
            "bank_detail.read_model.refresh",
            "workbench_relation.read_model.refresh",
        ),
        canonical_expected_set=(
            "eligible proven active Workbench OA-bank rows plus every active canonical expense bank transaction by month"
        ),
        key_display_fields=(
            "transaction_id",
            "group_id",
            "project_name/project_id",
            "expense_type/content/applicant",
            "amount/counterparty/time",
            "bank tags",
            "bank account mappings",
            "month and parent summaries",
        ),
        external_source_boundary="OA and bank source completeness before App registration",
    ),
}


def audit_page_business_read_model(
    connection: Any,
    *,
    domain_key: str,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    normalized_domain_key = str(domain_key or "").strip()
    contract = PAGE_AUDIT_CONTRACTS.get(normalized_domain_key)
    if contract is None:
        raise ValueError(f"Unsupported page audit domain: {domain_key}")
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    limit = max(int(example_limit or 50), 1)
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_page_business_read_model_snapshot(
            snapshot.connection,
            contract=contract,
            tenant_id=normalized_tenant_id,
            limit=limit,
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_page_business_read_model_snapshot(
    connection: Any,
    *,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    summary = _fetch_summary(connection, contract=contract, tenant_id=tenant_id)
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
        _canonical_expected_set_issues,
        _key_display_field_issues,
        _relation_edge_equality_issues,
        _consumer_relation_edge_equality_issues,
        _upstream_dependency_issues,
    )
    for check in checks:
        issues.extend(check(connection, contract, tenant_id, limit + 1))

    evaluation = evaluate_audit_issues(issues, sample_limit=limit)
    summary.update(evaluation.summary)
    return {
        "mode": "page-business-read-model-audit",
        "tenant_id": tenant_id,
        "domain_key": contract.domain_key,
        "label": contract.label,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": summary,
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": list(contract.source_tables),
            "read_model_tables": list(contract.read_model_tables),
            "relation_tables": list(contract.relation_tables),
            "scope_types": list(contract.scope_types),
            "event_types": list(contract.event_types),
            "canonical_expected_set": contract.canonical_expected_set,
            "key_display_fields": list(contract.key_display_fields),
            "relation_edge_equality": (
                "canonical == relation_groups == relation_rows == registered page consumer summaries"
                if contract.consumer_relation_contract
                else "canonical == relation_groups == relation_rows, including affected month scopes"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": contract.external_source_boundary,
            "proof_checks": [
                "canonical_expected_set_equality",
                "missing_or_orphan_identity",
                "key_display_field_recalculation",
                "scope_count_and_source_version_equality",
                "bidirectional_relation_edge_equality",
                *(["consumer_relation_edge_equality"] if contract.consumer_relation_contract else []),
                *(
                    [
                        "same_snapshot_workbench_and_bank_detail_dependency_integrity",
                        "canonical_bank_transaction_bank_flow_equality",
                        "month_upstream_source_version_equality",
                        "parent_source_shard_map_equality",
                        "project_expense_and_bank_flow_summary_recalculation",
                    ]
                    if contract.domain_key == "cost_statistics"
                    else []
                ),
                "durable_queue_and_freshness_gate",
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "App-internal canonical facts, read_model rows/scopes/source_versions, "
                "durable refresh state, and projected relation distribution agree for this page."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


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
        source_sql = """
            select count(*)
            from (
                select row_id as oa_id
                from app.oa_applications
                where status <> 'deleted'
                  and (
                        workflow_status is null or workflow_status = ''
                     or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
                  )
                union
                select oa_id
                from app.oa_pending_payment_admissions
                where tenant_id = %s
            ) canonical_oa
        """
        row_sql = "select count(distinct row_id) from read_model.oa_pending_payment_rows"
        scope_sql = "select count(*) from read_model.oa_pending_payment_scopes"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active' and 'oa' = any(row_types)"
        linked_sql = "select count(*) from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked' and cardinality(oa_row_ids) > 0"
        params = (tenant_id, tenant_id)
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
        row_sql = "select count(*) from read_model.cost_statistics_rows"
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
            where tenant_id = %s
              and scope_type in ({scope_types})
              and status in ('pending', 'processing', 'failed')
        ) as dirty_scope_count,
        (
            select count(*)::integer
            from job.outbox_events
            where tenant_id = %s
              and event_type in ({event_types})
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
        ) as outbox_backlog_count
    """, params + (tenant_id, tenant_id)


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
    if not contract.event_types:
        return []
    rows = connection.fetch_all(
        f"""
        /* check: outbox_backlog */
        select event_type, coalesce(scope_key, aggregate_id, '') as scope_key, status, updated_at::text as updated_at, last_error
        from job.outbox_events
        where tenant_id = %s
          and event_type in ({_quoted_list(contract.event_types)})
          and status in ('pending', 'processing', 'failed', 'dead_lettered')
        order by event_type, updated_at desc
        limit %s
        """,
        (tenant_id, limit),
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
                  and coalesce(row.source_versions, '{}'::jsonb) - 'source_version'
                      <> coalesce(scope.source_versions, '{}'::jsonb) - 'source_version'
                order by row.scope_key, row.transaction_id
                limit %s
                """,
                (tenant_id, limit),
                "bank_details_row_source_versions_mismatch",
            )
        )
        queries.append(
            _embedded_relation_source_summary_query(
                domain,
                "read_model.bank_detail_scopes",
                "scope",
                tenant_id,
                limit,
            )
        )
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
        queries.extend(
            [
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
                ),
                (
                    """
                    /* check: cost_upstream_source_versions */
                    with month_models as (
                        select model.scope_key,
                               substring(model.scope_key from '([0-9]{4}-[0-9]{2})$') as month_key,
                               model.source_versions
                        from read_model.cost_statistics_read_models model
                        where model.scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
                    ),
                    current_versions as (
                        select model.scope_key, model.month_key, model.source_versions,
                               generation.source_versions as current_workbench_source_versions,
                               bank_scope.source_versions as current_bank_detail_source_versions
                        from month_models model
                        left join lateral (
                            select source_versions
                            from read_model.workbench_generations
                            where tenant_id = %s
                              and scope_key = model.month_key
                              and status = 'active'
                            order by activated_at desc nulls last,
                                     completed_at desc nulls last,
                                     updated_at desc
                            limit 1
                        ) generation on true
                        left join read_model.bank_detail_scopes bank_scope
                          on bank_scope.tenant_id = %s
                         and bank_scope.scope_type = 'bank_detail'
                         and bank_scope.scope_key = model.month_key
                    )
                    select scope_key as subject_id, scope_key,
                           source_versions->'workbench_source_versions' as embedded_workbench_source_versions,
                           current_workbench_source_versions,
                           source_versions->'bank_detail_source_versions' as embedded_bank_detail_source_versions,
                           current_bank_detail_source_versions
                    from current_versions
                    where current_workbench_source_versions is null
                       or current_bank_detail_source_versions is null
                       or not source_versions ? 'workbench_source_versions'
                       or not source_versions ? 'bank_detail_source_versions'
                       or coalesce(source_versions->'workbench_source_versions', '{}'::jsonb)
                          <> coalesce(current_workbench_source_versions, '{}'::jsonb)
                       or coalesce(source_versions->'bank_detail_source_versions', '{}'::jsonb)
                          <> coalesce(current_bank_detail_source_versions, '{}'::jsonb)
                    order by scope_key
                    limit %s
                    """,
                    (tenant_id, tenant_id, limit),
                    "cost_statistics_upstream_source_versions_mismatch",
                ),
                (
                    """
                    /* check: cost_parent_source_shards */
                    with project_scopes(project_scope) as (
                        values ('active'), ('all')
                    ),
                    expected_months as (
                        select distinct generation.scope_key as month_key
                        from read_model.workbench_generations generation
                        where generation.tenant_id = %s
                          and generation.status = 'active'
                          and generation.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
                    ),
                    expected_children as (
                        select project.project_scope,
                               project.project_scope || ':' || month.month_key as scope_key,
                               child.source_versions
                        from project_scopes project
                        cross join expected_months month
                        left join read_model.cost_statistics_read_models child
                          on child.scope_key = project.project_scope || ':' || month.month_key
                    ),
                    expected_maps as (
                        select project.project_scope,
                               count(child.scope_key)::integer as expected_shard_count,
                               count(child.source_versions)::integer as present_shard_count,
                               coalesce(
                                   jsonb_object_agg(child.scope_key, child.source_versions)
                                       filter (where child.source_versions is not null),
                                   '{}'::jsonb
                               ) as expected_source_shards
                        from project_scopes project
                        left join expected_children child
                          on child.project_scope = project.project_scope
                        group by project.project_scope
                    ),
                    expected_parents as (
                        select expected.project_scope,
                               expected.project_scope || ':all' as scope_key,
                               expected.expected_shard_count,
                               expected.present_shard_count,
                               expected.expected_source_shards,
                               parent.source_versions as parent_source_versions
                        from expected_maps expected
                        left join read_model.cost_statistics_read_models parent
                          on parent.scope_key = expected.project_scope || ':all'
                    )
                    select scope_key as subject_id, scope_key,
                           expected_shard_count,
                           present_shard_count,
                           expected_source_shards,
                           parent_source_versions->'source_shards' as stored_source_shards,
                           parent_source_versions->>'source_shard_count' as stored_source_shard_count,
                           parent_source_versions->>'cost_statistics_parent_source' as parent_source
                    from expected_parents
                    where parent_source_versions is null
                       or present_shard_count <> expected_shard_count
                       or parent_source_versions->>'cost_statistics_parent_source' <> 'materialized_shards'
                       or not parent_source_versions ? 'source_shards'
                       or not parent_source_versions ? 'source_shard_count'
                       or coalesce(parent_source_versions->'source_shards', '{}'::jsonb) <> expected_source_shards
                       or case
                              when coalesce(parent_source_versions->>'source_shard_count', '') ~ '^[0-9]+$'
                              then (parent_source_versions->>'source_shard_count')::integer
                              else -1
                          end <> expected_shard_count
                    order by scope_key
                    limit %s
                    """,
                    (tenant_id, limit),
                    "cost_statistics_parent_source_shards_mismatch",
                ),
            ]
        )
    elif domain == "turnover_ledger":
        queries.append(
            (
                """
                /* check: source_business_fields_mismatch */
                with leaf_totals as (
                    select ledger.relation_id,
                           min(to_char(source.txn_month, 'YYYY-MM')) as scope_key,
                           count(distinct detail.effective_turnover_family)::integer as family_count,
                           max(detail.effective_turnover_family) as expected_family,
                           count(distinct coalesce(nullif(btrim(source.counterparty_name_raw), ''), 'UNKNOWN'))::integer
                               as counterparty_count,
                           max(coalesce(nullif(btrim(source.counterparty_name_raw), ''), 'UNKNOWN'))
                               as expected_counterparty_name,
                           coalesce(sum(abs(source.amount)) filter (
                               where detail.effective_turnover_action_type = 'pending_repayment'
                           ), 0)::numeric as borrow_in_principal,
                           coalesce(sum(abs(source.amount)) filter (
                               where detail.effective_turnover_action_type = 'repaid'
                           ), 0)::numeric as borrow_in_settled,
                           coalesce(sum(abs(source.amount)) filter (
                               where detail.effective_turnover_action_type = 'pending_collection'
                           ), 0)::numeric as borrow_out_principal,
                           coalesce(sum(abs(source.amount)) filter (
                               where detail.effective_turnover_action_type = 'collected'
                           ), 0)::numeric as borrow_out_settled
                    from read_model.turnover_ledger_rows ledger
                    join lateral unnest(ledger.bank_row_ids) member(row_id) on true
                    join app.bank_transactions source
                      on coalesce(source.legacy_mongo_id, source.id::text) = member.row_id
                     and source.status <> 'deleted'
                    join read_model.bank_detail_rows detail
                      on detail.tenant_id = %s
                     and detail.transaction_id = source.id::text
                    group by ledger.relation_id
                ),
                recomputed as (
                    select leaf_totals.*,
                           greatest(borrow_in_principal - borrow_in_settled, 0)::numeric
                               as expected_pending_repayment,
                           greatest(borrow_out_principal - borrow_out_settled, 0)::numeric
                               as expected_pending_collection,
                           (
                               case
                                   when borrow_in_principal > 0
                                   then greatest(borrow_in_principal - borrow_in_settled, 0)
                                   else -borrow_in_settled
                               end
                               + case
                                   when borrow_out_principal > 0
                                   then greatest(borrow_out_principal - borrow_out_settled, 0)
                                   else -borrow_out_settled
                               end
                           )::numeric as expected_balance
                    from leaf_totals
                )
                select ledger.relation_id as subject_id, recomputed.scope_key,
                       recomputed.expected_balance::text as source_amount,
                       ledger.amount::text as read_model_amount,
                       recomputed.expected_family as source_family,
                       ledger.family as read_model_family,
                       recomputed.expected_counterparty_name as source_counterparty_name,
                       ledger.counterparty_name as read_model_counterparty_name,
                       recomputed.expected_pending_repayment::text as source_pending_repayment_amount,
                       ledger.payload->>'pending_repayment_amount' as read_model_pending_repayment_amount,
                       recomputed.borrow_in_settled::text as source_repaid_amount,
                       ledger.payload->>'repaid_amount' as read_model_repaid_amount,
                       recomputed.expected_pending_collection::text as source_pending_collection_amount,
                       ledger.payload->>'pending_collection_amount' as read_model_pending_collection_amount,
                       recomputed.borrow_out_settled::text as source_collected_amount,
                       ledger.payload->>'collected_amount' as read_model_collected_amount
                from read_model.turnover_ledger_rows ledger
                join recomputed on recomputed.relation_id = ledger.relation_id
                where abs(
                        coalesce(ledger.amount, 0)
                        - recomputed.expected_balance
                      ) > 0.01
                   or recomputed.family_count <> 1
                   or coalesce(ledger.family, '') <> coalesce(recomputed.expected_family, '')
                   or recomputed.counterparty_count <> 1
                   or coalesce(ledger.counterparty_name, '') <> coalesce(recomputed.expected_counterparty_name, '')
                   or abs(
                        coalesce(nullif(replace(ledger.payload->>'pending_repayment_amount', ',', ''), '')::numeric, 0)
                        - recomputed.expected_pending_repayment
                      ) > 0.01
                   or abs(
                        coalesce(nullif(replace(ledger.payload->>'repaid_amount', ',', ''), '')::numeric, 0)
                        - recomputed.borrow_in_settled
                      ) > 0.01
                   or abs(
                        coalesce(nullif(replace(ledger.payload->>'pending_collection_amount', ',', ''), '')::numeric, 0)
                        - recomputed.expected_pending_collection
                      ) > 0.01
                   or abs(
                        coalesce(nullif(replace(ledger.payload->>'collected_amount', ',', ''), '')::numeric, 0)
                        - recomputed.borrow_out_settled
                      ) > 0.01
                order by ledger.relation_id
                limit %s
                """,
                (tenant_id, limit),
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
        select source.id::text as subject_id,
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
        return []
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
        with canonical as (
            select row_id as oa_id
            from app.oa_applications
            where status <> 'deleted'
              and (
                    workflow_status is null or workflow_status = ''
                 or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
              )
            union
            select oa_id
            from app.oa_pending_payment_admissions
            where tenant_id = %s
        )
        select row.oa_id as subject_id, row.scope_key, row.row_id
        from read_model.oa_pending_payment_rows row
        left join canonical source on source.oa_id = row.oa_id
        where nullif(row.oa_id, '') is not null
          and source.oa_id is null
        order by row.scope_key, row.oa_id
        limit %s
        """
        params = (tenant_id, limit)
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
        return []
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


def _canonical_expected_set_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "pending_invoices":
        sql = """
        /* check: canonical_expected_set */
        with canonical as (
            select coalesce(legacy_mongo_id, id::text) as row_id,
                   case when txn_direction = 'outflow' then 'expense' else 'income' end as direction,
                   to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where status <> 'deleted'
              and txn_direction in ('outflow', 'inflow')
        ),
        projected as (
            select distinct
                coalesce(nullif(member.value->>'id', ''), row.row_id) as row_id,
                case when source.txn_direction = 'outflow' then 'expense' else 'income' end as direction,
                to_char(source.txn_month, 'YYYY-MM') as scope_key
            from read_model.pending_invoice_rows row
            join lateral jsonb_array_elements(
                case
                    when jsonb_typeof(row.payload->'bank_transactions'->'summaries') = 'array'
                     and jsonb_array_length(row.payload->'bank_transactions'->'summaries') > 0
                    then row.payload->'bank_transactions'->'summaries'
                    else jsonb_build_array(jsonb_build_object('id', row.row_id))
                end
            ) member(value) on true
            join app.bank_transactions source
              on coalesce(source.legacy_mongo_id, source.id::text)
                 = coalesce(nullif(member.value->>'id', ''), row.row_id)
             and source.status <> 'deleted'
             and source.txn_direction in ('outflow', 'inflow')
        ),
        mismatches as (
            select 'canonical_missing_projection' as mismatch_kind, canonical.*
            from canonical
            where not exists (
                select 1 from projected
                where projected.row_id = canonical.row_id
                  and projected.direction = canonical.direction
            )
            union all
            select 'projection_not_canonical', projected.*
            from projected
            where not exists (
                select 1 from canonical
                where canonical.row_id = projected.row_id
                  and canonical.direction = projected.direction
            )
        )
        select row_id as subject_id, scope_key, direction, mismatch_kind
        from mismatches
        order by mismatch_kind, scope_key, row_id
        limit %s
        """
        params: tuple[Any, ...] = (limit,)
    elif domain == "oa_pending_payments":
        sql = """
        /* check: canonical_expected_set */
        with canonical as (
            select row_id as oa_id, to_char(scope_month, 'YYYY-MM') as scope_key
            from app.oa_applications
            where status <> 'deleted'
              and (
                    workflow_status is null or workflow_status = ''
                 or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
              )
            union
            select oa_id, scope_key
            from app.oa_pending_payment_admissions
            where tenant_id = %s
        ),
        projected as (
            select distinct
                coalesce(nullif(member.value->>'oaId', ''), nullif(member.value->>'id', ''), row.oa_id) as oa_id,
                row.scope_key
            from read_model.oa_pending_payment_rows row
            join lateral jsonb_array_elements(
                case
                    when jsonb_typeof(row.payload->'oa'->'summaries') = 'array'
                     and jsonb_array_length(row.payload->'oa'->'summaries') > 0
                    then row.payload->'oa'->'summaries'
                    else jsonb_build_array(jsonb_build_object('oaId', row.oa_id))
                end
            ) member(value) on true
        ),
        mismatches as (
            select 'canonical_missing_projection' as mismatch_kind,
                   canonical.oa_id, canonical.scope_key
            from canonical
            where not exists (select 1 from projected where projected.oa_id = canonical.oa_id)
            union all
            select 'projection_not_registered_in_app', projected.oa_id, projected.scope_key
            from projected
            where not exists (
                select 1 from canonical source
                where source.oa_id = projected.oa_id
            )
        )
        select oa_id as subject_id, scope_key, mismatch_kind
        from mismatches
        order by mismatch_kind, scope_key, oa_id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "turnover_ledger":
        sql = """
        /* check: canonical_expected_set */
        with settings as (
            select coalesce(
                (
                    select settings_payload
                    from app.app_settings
                    where settings_key = 'app_settings'
                    limit 1
                ),
                '{}'::jsonb
            ) as payload
        ),
        selection as (
            select payload ? 'turnover_ledger_tag_selection' as explicitly_configured,
                   coalesce(
                       array(
                           select jsonb_array_elements_text(
                               case
                                   when jsonb_typeof(
                                       payload->'turnover_ledger_tag_selection'->'selected_tag_codes'
                                   ) = 'array'
                                   then payload->'turnover_ledger_tag_selection'->'selected_tag_codes'
                                   else '[]'::jsonb
                               end
                           )
                       ),
                       array[]::text[]
                   ) as selected_tag_codes
            from settings
        ),
        canonical_leaves as (
            select coalesce(source.legacy_mongo_id, source.id::text) as row_id,
                   to_char(source.txn_month, 'YYYY-MM') as scope_key,
                   source.amount::text as amount,
                   detail.effective_turnover_family as family,
                   coalesce(nullif(btrim(source.counterparty_name_raw), ''), 'UNKNOWN') as counterparty_name
            from read_model.bank_detail_rows detail
            join app.bank_transactions source
              on source.id::text = detail.transaction_id
             and source.status <> 'deleted'
            cross join selection
            where detail.tenant_id = %s
              and (
                    detail.effective_turnover_role = 'external_turnover'
                 or coalesce(detail.effective_category_primary_label, '') like '%%外部往来款%%'
                 or coalesce(detail.effective_category_primary_label, '') like '%%往来款%%'
              )
              and detail.effective_turnover_action_type
                  in ('pending_collection', 'collected', 'pending_repayment', 'repaid')
              and detail.effective_turnover_family in ('personal', 'company', 'bank', 'business')
              and nullif(detail.effective_category_third_label, '') is not null
              and (
                    not selection.explicitly_configured
                 or detail.effective_category_code = any(selection.selected_tag_codes)
              )
        ),
        canonical as (
            select family, counterparty_name, min(scope_key) as scope_key,
                   array_agg(row_id order by row_id) as bank_row_ids
            from canonical_leaves
            group by family, counterparty_name
        ),
        projected as (
            select ledger.relation_id, ledger.family,
                   coalesce(nullif(btrim(ledger.counterparty_name), ''), 'UNKNOWN') as counterparty_name,
                   to_char(ledger.scope_month, 'YYYY-MM') as scope_key,
                   coalesce(
                       (
                           select array_agg(distinct member.row_id order by member.row_id)
                           from unnest(ledger.bank_row_ids) member(row_id)
                       ),
                       array[]::text[]
                   ) as bank_row_ids
            from read_model.turnover_ledger_rows ledger
        ),
        mismatches as (
            select 'canonical_missing_projection' as mismatch_kind,
                   concat(canonical.family, ':', canonical.counterparty_name) as subject_id,
                   canonical.scope_key, canonical.family, canonical.counterparty_name,
                   canonical.bank_row_ids as canonical_bank_row_ids,
                   projected.bank_row_ids as projected_bank_row_ids
            from canonical
            left join projected
              on projected.family = canonical.family
             and projected.counterparty_name = canonical.counterparty_name
            where projected.relation_id is null
               or projected.bank_row_ids <> canonical.bank_row_ids
            union all
            select 'projection_not_canonical', projected.relation_id,
                   projected.scope_key, projected.family, projected.counterparty_name,
                   canonical.bank_row_ids, projected.bank_row_ids
            from projected
            left join canonical
              on canonical.family = projected.family
             and canonical.counterparty_name = projected.counterparty_name
            where canonical.family is null
               or projected.bank_row_ids <> canonical.bank_row_ids
        )
        select subject_id, scope_key, mismatch_kind, family, counterparty_name,
               canonical_bank_row_ids, projected_bank_row_ids
        from mismatches
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """
        params = (tenant_id, limit)
    elif domain == "cost_statistics":
        sql = """
        /* check: canonical_expected_set */
        with active_generations as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        group_candidates as (
            select generation.generation_id, generation.scope_key, group_row.group_id, group_row.zone,
                   case
                       when group_row.payload is not null then
                           case
                               when jsonb_typeof(group_row.payload->'normalized_payload') = 'object'
                               then coalesce(group_row.payload->'normalized_payload', '{}'::jsonb)
                               else group_row.payload
                           end
                       when group_row.raw_payload is not null then
                           case
                               when jsonb_typeof(group_row.raw_payload->'normalized_payload') = 'object'
                               then coalesce(group_row.raw_payload->'normalized_payload', '{}'::jsonb)
                               else group_row.raw_payload
                           end
                       else '{}'::jsonb
                   end as group_payload
            from active_generations generation
            join read_model.workbench_groups group_row
              on group_row.generation_id = generation.generation_id
             and group_row.scope_key = generation.scope_key
            where group_row.zone in ('paired', 'open')
              and group_row.source_kinds && array['oa', 'bank']::text[]
        ),
        member_payloads as (
            select group_row.generation_id, group_row.scope_key, group_row.group_id,
                   group_row.zone, group_row.group_payload,
                   member.pane, member.row_id,
                   case
                       when source.payload is not null then
                           case
                               when jsonb_typeof(source.payload->'normalized_payload') = 'object'
                               then coalesce(source.payload->'normalized_payload', '{}'::jsonb)
                               else source.payload
                           end
                       when source.raw_payload is not null then
                           case
                               when jsonb_typeof(source.raw_payload->'normalized_payload') = 'object'
                               then coalesce(source.raw_payload->'normalized_payload', '{}'::jsonb)
                               else source.raw_payload
                           end
                       when member.payload is not null then
                           case
                               when jsonb_typeof(member.payload->'normalized_payload') = 'object'
                               then coalesce(member.payload->'normalized_payload', '{}'::jsonb)
                               else member.payload
                           end
                       when member.raw_payload is not null then
                           case
                               when jsonb_typeof(member.raw_payload->'normalized_payload') = 'object'
                               then coalesce(member.raw_payload->'normalized_payload', '{}'::jsonb)
                               else member.raw_payload
                           end
                       else '{}'::jsonb
                   end as member_payload
            from group_candidates group_row
            join read_model.workbench_group_rows member
              on member.generation_id = group_row.generation_id
             and member.scope_key = group_row.scope_key
             and member.group_id = group_row.group_id
             and member.pane in ('oa', 'bank')
             and coalesce(member.row_role, '') <> 'collapsed'
            left join read_model.workbench_rows source
              on source.generation_id = member.generation_id
             and source.scope_key = member.scope_key
             and source.row_id = member.row_id
        ),
        group_facts as (
            select generation_id, scope_key, group_id, zone, group_payload,
                   bool_or(pane = 'oa') as has_oa,
                   bool_or(pane = 'bank') as has_bank,
                   bool_or(
                       lower(btrim(coalesce(
                           nullif(member_payload->>'relation_status', ''),
                           nullif(member_payload->>'relationStatus', ''),
                           nullif(member_payload->>'status', ''),
                           ''
                       ))) = 'candidate'
                   ) as has_candidate_member,
                   bool_or(
                       pane = 'oa'
                       and member_payload->'oa_bank_relation'->>'code'
                           in ('fully_linked', 'automatic_match')
                   ) as has_linked_oa,
                   bool_or(
                       pane = 'bank'
                       and member_payload->'available_actions' ? 'cancel_link'
                   ) as has_cancel_link
            from member_payloads
            group by generation_id, scope_key, group_id, zone, group_payload
        ),
        eligible_groups as (
            select generation_id, scope_key, group_id, zone
            from group_facts
            where has_oa
              and has_bank
              and lower(btrim(coalesce(
                    nullif(group_payload->>'relation_status', ''),
                    nullif(group_payload->>'relationStatus', ''),
                    nullif(group_payload->>'status', ''),
                    ''
                  ))) <> 'candidate'
              and not has_candidate_member
              and (
                    has_linked_oa
                 or lower(btrim(coalesce(group_payload->>'group_type', ''))) <> 'candidate'
              )
              and (
                    zone = 'paired'
                 or has_linked_oa
                 or has_cancel_link
              )
        ),
        oa_contexts as (
            select group_row.generation_id, group_row.scope_key, group_row.group_id,
                   coalesce(
                       nullif(case when btrim(member.member_payload->>'project_name') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'project_name') end, ''),
                       nullif(case when btrim(member.member_payload->'detail_fields'->>'项目名称')
                                            in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->'detail_fields'->>'项目名称') end, '')
                   ) as project_name,
                   coalesce(
                       nullif(case when btrim(member.member_payload->>'project_id') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'project_id') end, ''),
                       nullif(case when btrim(member.member_payload->'detail_fields'->>'项目编号')
                                            in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->'detail_fields'->>'项目编号') end, ''),
                       ''
                   ) as project_id,
                   coalesce(
                       nullif(case when btrim(member.member_payload->>'expense_type') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'expense_type') end, ''),
                       nullif(case when btrim(member.member_payload->'detail_fields'->>'费用类型')
                                            in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->'detail_fields'->>'费用类型') end, '')
                   ) as expense_type,
                   coalesce(
                       nullif(case when btrim(member.member_payload->>'expense_content') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'expense_content') end, ''),
                       nullif(case when btrim(member.member_payload->>'reason') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'reason') end, ''),
                       nullif(case when btrim(member.member_payload->'detail_fields'->>'费用内容')
                                            in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->'detail_fields'->>'费用内容') end, '')
                   ) as expense_content,
                   coalesce(
                       nullif(case when btrim(member.member_payload->>'applicant') in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->>'applicant') end, ''),
                       nullif(case when btrim(member.member_payload->'detail_fields'->>'申请人')
                                            in ('', '-', '--', '—', '——')
                                   then '' else btrim(member.member_payload->'detail_fields'->>'申请人') end, ''),
                       ''
                   ) as applicant
            from eligible_groups group_row
            join member_payloads member
              on member.generation_id = group_row.generation_id
             and member.scope_key = group_row.scope_key
             and member.group_id = group_row.group_id
             and member.pane = 'oa'
        ),
        eligible_context_groups as (
            select generation_id, scope_key, group_id,
                   max(project_name) as project_name,
                   max(project_id) as project_id,
                   max(expense_type) as expense_type,
                   max(expense_content) as expense_content,
                   max(applicant) as applicant
            from oa_contexts
            where nullif(project_name, '') is not null
              and nullif(expense_type, '') is not null
              and nullif(expense_content, '') is not null
              and expense_type not in ('借款', '还款')
            group by generation_id, scope_key, group_id
            having count(distinct concat_ws(
                       chr(31), project_name, project_id, expense_type, expense_content, applicant
                   )) = 1
        ),
        bank_tag_sources as (
            select transaction_id,
                   coalesce(effective_category_code, '') as bank_tag_code,
                   coalesce(effective_category_label, effective_category_sub_label, '') as bank_tag_label,
                   effective_category_primary_label as explicit_primary_label,
                   effective_category_sub_label as explicit_sub_label,
                   case
                       when cardinality(effective_category_label_path) > 0 then effective_category_label_path
                       when cardinality(effective_category_path) > 0 then effective_category_path
                       else array[]::text[]
                   end as effective_label_path
            from read_model.bank_detail_rows
            where tenant_id = %s
        ),
        bank_tag_contexts as (
            select transaction_id, bank_tag_code, bank_tag_label,
                   coalesce(
                       explicit_primary_label,
                       effective_label_path[1],
                       nullif(bank_tag_label, ''),
                       '未标记'
                   ) as bank_tag_primary_label,
                   coalesce(
                       explicit_sub_label,
                       effective_label_path[2],
                       nullif(bank_tag_label, ''),
                       explicit_primary_label,
                       effective_label_path[1],
                       '未标记'
                   ) as bank_tag_sub_label,
                   effective_label_path
            from bank_tag_sources
        ),
        expected_cost_members as (
            select group_row.scope_key, group_row.group_id,
                   coalesce(
                       nullif(member.member_payload->>'id', ''),
                       nullif(member.member_payload->>'row_id', ''),
                       member.row_id
                   ) as transaction_id,
                   group_row.project_name,
                   group_row.project_id,
                   group_row.expense_type,
                   group_row.expense_content,
                   coalesce(nullif(group_row.applicant, ''), '—') as oa_applicant,
                   coalesce(
                       nullif(member.member_payload->>'trade_time', ''),
                       member.member_payload->>'date',
                       ''
                   ) as trade_time,
                   coalesce(member.member_payload->>'counterparty_name', '') as counterparty_name,
                   coalesce(
                       nullif(member.member_payload->>'payment_account_label', ''),
                       member.member_payload->>'bank_name',
                       ''
                   ) as payment_account_label,
                   coalesce(nullif(member.member_payload->>'direction', ''), '支出') as direction,
                   coalesce(member.member_payload->>'remark', '') as remark,
                   coalesce(tag.bank_tag_code, '') as bank_tag_code,
                   coalesce(tag.bank_tag_label, '') as bank_tag_label,
                   coalesce(tag.bank_tag_primary_label, '未标记') as bank_tag_primary_label,
                   coalesce(tag.bank_tag_sub_label, '未标记') as bank_tag_sub_label,
                   to_jsonb(
                       case
                           when cardinality(tag.effective_label_path) > 0
                           then tag.effective_label_path
                           when coalesce(tag.bank_tag_primary_label, '未标记')
                                = coalesce(tag.bank_tag_sub_label, '未标记')
                           then array[coalesce(tag.bank_tag_primary_label, '未标记')]::text[]
                           else array[
                                    coalesce(tag.bank_tag_primary_label, '未标记'),
                                    coalesce(tag.bank_tag_sub_label, '未标记')
                                ]::text[]
                       end
                   ) as bank_tag_label_path,
                   lower(btrim(coalesce(
                       nullif(member.member_payload->>'direction', ''),
                       nullif(member.member_payload->>'txn_direction', ''),
                       ''
                   ))) as direction_value,
                   replace(
                       coalesce(
                           nullif(member.member_payload->>'debit_amount', ''),
                           member.member_payload->>'amount'
                       ),
                       ',', ''
                   ) as amount_value
            from eligible_context_groups group_row
            join member_payloads member
              on member.generation_id = group_row.generation_id
             and member.scope_key = group_row.scope_key
             and member.group_id = group_row.group_id
             and member.pane = 'bank'
            left join app.bank_transactions bank_source
              on (
                    bank_source.id::text = coalesce(
                        nullif(member.member_payload->>'id', ''),
                        nullif(member.member_payload->>'row_id', ''),
                        member.row_id
                    )
                 or bank_source.legacy_mongo_id = coalesce(
                        nullif(member.member_payload->>'id', ''),
                        nullif(member.member_payload->>'row_id', ''),
                        member.row_id
                    )
                 )
             and bank_source.status <> 'deleted'
            left join bank_tag_contexts tag
              on tag.transaction_id = bank_source.id::text
        ),
        expected_cost as (
            select scope_key, transaction_id,
                   count(*)::integer as expected_count,
                   sum(abs(amount_value::numeric))::numeric as expected_amount,
                   jsonb_agg(
                       jsonb_build_object(
                           'group_id', group_id,
                           'project_name', project_name,
                           'project_id', project_id,
                           'expense_type', expense_type,
                           'expense_content', expense_content,
                           'oa_applicant', oa_applicant,
                           'trade_time', trade_time,
                           'counterparty_name', counterparty_name,
                           'payment_account_label', payment_account_label,
                           'direction', direction,
                           'remark', remark,
                           'bank_tag_code', bank_tag_code,
                           'bank_tag_label', bank_tag_label,
                           'bank_tag_primary_label', bank_tag_primary_label,
                           'bank_tag_sub_label', bank_tag_sub_label,
                           'bank_tag_label_path', bank_tag_label_path
                       )
                       order by group_id, project_name, expense_type, expense_content
                   ) as expected_fields
            from expected_cost_members
            where (
                    direction_value = ''
                 or position('out' in direction_value) > 0
                 or position('支出' in direction_value) > 0
                 or position('付款' in direction_value) > 0
                 or position('debit' in direction_value) > 0
            )
              and amount_value ~ '^-?[0-9]+([.][0-9]+)?$'
              and amount_value::numeric <> 0
            group by scope_key, transaction_id
        ),
        projected_cost as (
            select substring(scope_key from '([0-9]{4}-[0-9]{2})$') as scope_key,
                   transaction_id, count(*)::integer as projected_count,
                   sum(abs(amount))::numeric as projected_amount,
                   jsonb_agg(
                       jsonb_build_object(
                           'group_id', coalesce(group_id, ''),
                           'project_name', coalesce(project_name, ''),
                           'project_id', coalesce(project_id, ''),
                           'expense_type', coalesce(expense_type, ''),
                           'expense_content', coalesce(expense_content, ''),
                           'oa_applicant', coalesce(nullif(oa_applicant, ''), '—'),
                           'trade_time', coalesce(trade_time_text, trade_date::text, ''),
                           'counterparty_name', coalesce(counterparty_name, ''),
                           'payment_account_label', coalesce(payment_account_label, ''),
                           'direction', coalesce(nullif(direction, ''), '支出'),
                           'remark', coalesce(remark, ''),
                           'bank_tag_code', coalesce(payload->>'bank_tag_code', ''),
                           'bank_tag_label', coalesce(payload->>'bank_tag_label', ''),
                           'bank_tag_primary_label', coalesce(payload->>'bank_tag_primary_label', ''),
                           'bank_tag_sub_label', coalesce(payload->>'bank_tag_sub_label', ''),
                           'bank_tag_label_path', coalesce(payload->'bank_tag_label_path', '[]'::jsonb)
                       )
                       order by coalesce(group_id, ''), project_name, expense_type, expense_content
                   ) as projected_fields
            from read_model.cost_statistics_rows
            where project_scope = 'all'
            group by substring(scope_key from '([0-9]{4}-[0-9]{2})$'), transaction_id
        ),
        cost_mismatches as (
            select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                   coalesce(expected.transaction_id, projected.transaction_id) as transaction_id,
                   expected.expected_count, projected.projected_count,
                   expected.expected_amount, projected.projected_amount,
                   expected.expected_fields, projected.projected_fields
            from expected_cost expected
            full join projected_cost projected
              on projected.scope_key = expected.scope_key
             and projected.transaction_id = expected.transaction_id
            where coalesce(expected.expected_count, -1) <> coalesce(projected.projected_count, -1)
               or abs(coalesce(expected.expected_amount, 0) - coalesce(projected.projected_amount, 0)) > 0.01
               or coalesce(expected.expected_fields, '[]'::jsonb)
                  <> coalesce(projected.projected_fields, '[]'::jsonb)
        ),
        expected_bank_flow as (
            select to_char(source.txn_month, 'YYYY-MM') as scope_key,
                   source.id::text as transaction_id,
                   count(*)::integer as expected_count,
                   sum(abs(source.amount))::numeric as expected_amount
            from app.bank_transactions source
            where source.status <> 'deleted'
              and source.txn_direction = 'outflow'
              and source.txn_month is not null
              and coalesce(source.amount, 0) <> 0
            group by to_char(source.txn_month, 'YYYY-MM'),
                     source.id::text
        ),
        projected_bank_flow as (
            select substring(model.scope_key from '([0-9]{4}-[0-9]{2})$') as scope_key,
                   member.value->>'transaction_id' as transaction_id,
                   count(*)::integer as projected_count,
                   sum(
                       case
                           when replace(coalesce(member.value->>'amount', ''), ',', '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then abs(replace(member.value->>'amount', ',', '')::numeric)
                           else 0
                       end
                   )::numeric as projected_amount,
                   bool_or(
                       replace(coalesce(member.value->>'amount', ''), ',', '')
                       !~ '^-?[0-9]+([.][0-9]+)?$'
                   ) as has_invalid_amount
            from read_model.cost_statistics_read_models model
            join lateral jsonb_array_elements(
                case
                    when jsonb_typeof(model.payload->'payload'->'bank_flow_time_rows') = 'array'
                    then model.payload->'payload'->'bank_flow_time_rows'
                    else '[]'::jsonb
                end
            ) member(value) on true
            where model.project_scope = 'all'
              and model.scope_key !~ ':(all)$'
            group by substring(model.scope_key from '([0-9]{4}-[0-9]{2})$'),
                     member.value->>'transaction_id'
        ),
        bank_flow_mismatches as (
            select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                   coalesce(expected.transaction_id, projected.transaction_id) as transaction_id,
                   expected.expected_count, projected.projected_count,
                   expected.expected_amount, projected.projected_amount,
                   projected.has_invalid_amount
            from expected_bank_flow expected
            full join projected_bank_flow projected
              on projected.scope_key = expected.scope_key
             and projected.transaction_id = expected.transaction_id
            where coalesce(expected.expected_count, -1) <> coalesce(projected.projected_count, -1)
               or abs(coalesce(expected.expected_amount, 0) - coalesce(projected.projected_amount, 0)) > 0.01
               or coalesce(projected.has_invalid_amount, false)
        )
        select transaction_id as subject_id, scope_key,
               'workbench_cost_projection_mismatch' as mismatch_kind,
               expected_count, projected_count,
               expected_amount::text, projected_amount::text,
               expected_fields, projected_fields
        from cost_mismatches
        union all
        select transaction_id as subject_id, scope_key,
               'bank_detail_cost_projection_mismatch' as mismatch_kind,
               expected_count, projected_count,
               expected_amount::text, projected_amount::text,
               null::jsonb as expected_fields, null::jsonb as projected_fields
        from bank_flow_mismatches
        order by scope_key, subject_id
        limit %s
        """
        params = (tenant_id, tenant_id, limit)
    else:
        return []
    return _proof_query_issues(
        connection,
        sql=sql,
        params=params,
        code=f"{domain}_canonical_expected_set_mismatch",
        message=f"{contract.label} canonical expected-set and projected member set are not equal.",
    )


def _key_display_field_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "bank_details":
        queries = [
            (
                """
                /* check: key_display_fields */
                select source.id::text as subject_id,
                       to_char(source.txn_month, 'YYYY-MM') as scope_key,
                       source.amount::text as source_amount, row.amount::text as projected_amount,
                       source.txn_direction as source_direction, row.direction as projected_direction,
                       source.counterparty_name_raw as source_counterparty_name,
                       row.counterparty_name as projected_counterparty_name,
                       coalesce(source.txn_date, source.trade_time::date)::text as source_trade_date,
                       row.trade_date::text as projected_trade_date
                from app.bank_transactions source
                join read_model.bank_detail_rows row
                  on row.tenant_id = %s
                 and row.transaction_id = source.id::text
                where source.status <> 'deleted'
                  and (
                        abs(coalesce(row.amount, 0) - abs(coalesce(source.amount, 0))) > 0.01
                     or row.direction <> case when source.txn_direction = 'inflow' then 'income' else 'expense' end
                     or coalesce(row.counterparty_name, '') <> coalesce(source.counterparty_name_raw, '')
                     or row.trade_date is distinct from coalesce(source.txn_date, source.trade_time::date)
                     or row.scope_key <> to_char(source.txn_month, 'YYYY-MM')
                  )
                order by source.txn_month, subject_id
                limit %s
                """,
                (tenant_id, limit),
                "bank_details_key_display_fields_mismatch",
            ),
            (_bank_account_balance_equality_sql(), (tenant_id, limit), "bank_details_account_balance_mismatch"),
        ]
    elif domain == "pending_invoices":
        queries = [
            (
                """
                /* check: key_display_fields */
                with projected as (
                    select row.row_id as projected_row_id, row.direction, row.scope_month, row.status_code,
                           row.payload->'invoice_acquisition_status'->>'code' as payload_status_code,
                           coalesce(nullif(member.value->>'id', ''), row.row_id) as transaction_id,
                           member.value
                    from read_model.pending_invoice_rows row
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(row.payload->'bank_transactions'->'summaries') = 'array'
                             and jsonb_array_length(row.payload->'bank_transactions'->'summaries') > 0
                            then row.payload->'bank_transactions'->'summaries'
                            else jsonb_build_array(row.payload->'bank_transaction')
                        end
                    ) member(value) on true
                )
                select projected.transaction_id as subject_id,
                       to_char(source.txn_month, 'YYYY-MM') as scope_key,
                       source.amount::text as source_amount,
                       projected.value->>'amount' as projected_amount,
                       source.counterparty_name_raw as source_counterparty_name,
                       projected.value->>'counterparty_name' as projected_counterparty_name,
                       projected.status_code, projected.payload_status_code
                from projected
                join app.bank_transactions source
                  on coalesce(source.legacy_mongo_id, source.id::text) = projected.transaction_id
                 and source.status <> 'deleted'
                where (
                        projected.transaction_id = projected.projected_row_id
                    and (
                            projected.direction
                            <> case when source.txn_direction = 'outflow' then 'expense' else 'income' end
                         or projected.scope_month is distinct from source.txn_month
                        )
                      )
                   or abs(
                        coalesce(nullif(replace(projected.value->>'amount', ',', ''), '')::numeric, 0)
                        - abs(coalesce(source.amount, 0))
                   ) > 0.01
                   or coalesce(projected.value->>'counterparty_name', '')
                      <> coalesce(source.counterparty_name_raw, '')
                   or coalesce(projected.status_code, '') <> coalesce(projected.payload_status_code, '')
                order by scope_key, subject_id
                limit %s
                """,
                (limit,),
                "pending_invoices_key_display_fields_mismatch",
            )
        ]
    elif domain == "oa_pending_payments":
        queries = [
            (
                """
                /* check: key_display_fields */
                with canonical_completed as (
                    select row_id as oa_id, amount, applicant,
                           coalesce(
                               nullif(normalized_payload->>'project_name_display', ''),
                               nullif(raw_payload->'normalized_payload'->>'project_name_display', ''),
                               project_name
                           ) as project_name,
                           coalesce(workflow_status, '') as workflow_status
                    from app.oa_applications
                    where status <> 'deleted'
                      and (
                            workflow_status is null or workflow_status = ''
                         or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
                      )
                ),
                canonical as (
                    select * from canonical_completed
                    union all
                    select admission.oa_id, admission.amount, admission.applicant,
                           coalesce(admission.project_name_display, admission.project_name),
                           coalesce(admission.workflow_status, '')
                    from app.oa_pending_payment_admissions admission
                    where admission.tenant_id = %s
                      and not exists (
                          select 1 from canonical_completed completed
                          where completed.oa_id = admission.oa_id
                      )
                ),
                projected as (
                    select row.scope_key, row.payment_status,
                           row.payload->'paymentStatus'->>'code' as payload_payment_status,
                           coalesce(nullif(member.value->>'oaId', ''), nullif(member.value->>'id', ''), row.oa_id) as oa_id,
                           member.value
                    from read_model.oa_pending_payment_rows row
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(row.payload->'oa'->'summaries') = 'array'
                             and jsonb_array_length(row.payload->'oa'->'summaries') > 0
                            then row.payload->'oa'->'summaries'
                            else jsonb_build_array(row.payload->'oa')
                        end
                    ) member(value) on true
                )
                select projected.oa_id as subject_id, projected.scope_key,
                       source.amount::text as source_amount,
                       projected.value->>'amount' as projected_amount,
                       source.applicant as source_applicant,
                       projected.value->>'applicantName' as projected_applicant,
                       source.project_name as source_project_name,
                       projected.value->>'projectName' as projected_project_name,
                       source.workflow_status as source_workflow_status,
                       projected.value->>'workflowStatus' as projected_workflow_status,
                       projected.payment_status, projected.payload_payment_status
                from projected
                join canonical source on source.oa_id = projected.oa_id
                where (
                        abs(
                            coalesce(nullif(replace(projected.value->>'amount', ',', ''), '')::numeric, 0)
                            - coalesce(source.amount, 0)
                        ) > 0.01
                     or coalesce(projected.value->>'applicantName', '') <> coalesce(source.applicant, '')
                     or coalesce(projected.value->>'projectName', '') <> coalesce(source.project_name, '')
                     or coalesce(projected.value->>'workflowStatus', '') <> coalesce(source.workflow_status, '')
                     or coalesce(projected.payment_status, '') <> coalesce(projected.payload_payment_status, '')
                  )
                order by projected.scope_key, projected.oa_id
                limit %s
                """,
                (tenant_id, limit),
                "oa_pending_payments_key_display_fields_mismatch",
            )
        ]
    elif domain == "turnover_ledger":
        queries = [
            (
                """
                /* check: key_display_fields */
                select extra.ledger_key as subject_id,
                       to_char(extra.scope_month, 'YYYY-MM') as scope_key,
                       extra.extra_payload as canonical_extra,
                       jsonb_build_object(
                           'interest_rate_type', row.payload->'interest_rate_type',
                           'interest_rate_value', row.payload->'interest_rate_value',
                           'interest_paid_amount', row.payload->'interest_paid_amount',
                           'interest_paid_date', row.payload->'interest_paid_date',
                           'interest_payment_method', row.payload->'interest_payment_method',
                           'note', row.payload->'note'
                       ) as projected_extra
                from app.turnover_ledger_extras extra
                left join read_model.turnover_ledger_rows row on row.relation_id = extra.ledger_key
                where row.relation_id is null
                   or coalesce(row.payload->>'interest_rate_type', 'none')
                      <> coalesce(extra.extra_payload->>'interest_rate_type', 'none')
                   or coalesce(row.payload->>'interest_rate_value', '0.000000')
                      <> coalesce(extra.extra_payload->>'interest_rate_value', '0.000000')
                   or coalesce(row.payload->>'interest_paid_amount', '0.00')
                      <> coalesce(extra.extra_payload->>'interest_paid_amount', '0.00')
                   or coalesce(row.payload->>'interest_paid_date', '')
                      <> coalesce(extra.extra_payload->>'interest_paid_date', '')
                   or coalesce(row.payload->>'interest_payment_method', '')
                      <> coalesce(extra.extra_payload->>'interest_payment_method', '')
                   or coalesce(row.payload->>'note', '') <> coalesce(extra.extra_payload->>'note', '')
                order by extra.ledger_key
                limit %s
                """,
                (limit,),
                "turnover_ledger_extra_fields_mismatch",
            )
        ]
    elif domain == "batch_accounting":
        queries = [
            (
                """
                /* check: key_display_fields */
                select relation.case_id as subject_id,
                       to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                       relation.relation_mode as canonical_relation_mode,
                       group_row.relation_kind as projected_relation_kind,
                       group_row.payload->>'relation_mode' as projected_relation_mode,
                       relation.special_metadata as canonical_special_metadata,
                       group_row.payload->'special_metadata' as projected_special_metadata
                from app.workbench_pair_relations relation
                join read_model.workbench_relation_groups group_row
                  on group_row.tenant_id = %s
                 and group_row.group_id = relation.case_id
                 and group_row.scope_key = to_char(relation.month_scope, 'YYYY-MM')
                 and group_row.relation_status = 'linked'
                where relation.status = 'active'
                  and relation.special_metadata->>'source' = 'batch_accounting'
                  and (
                        coalesce(group_row.payload->>'relation_mode', '') <> coalesce(relation.relation_mode, '')
                     or coalesce(group_row.payload->'special_metadata', '{}'::jsonb)
                        <> coalesce(relation.special_metadata, '{}'::jsonb)
                  )
                order by relation.case_id
                limit %s
                """,
                (tenant_id, limit),
                "batch_accounting_key_display_fields_mismatch",
            )
        ]
    elif domain == "bank_flow_rule_batches":
        queries = [
            (
                """
                /* check: key_display_fields */
                with source_batches as (
                    select batch.*,
                           coalesce(
                               nullif(batch.raw_payload->'normalized_payload'->>'batch_type', ''),
                               nullif(batch.raw_payload->>'batch_type', '')
                           ) as canonical_batch_type
                    from app.bank_flow_rule_batches batch
                    where batch.status <> 'deleted'
                ),
                batch_members as (
                    select batch.batch_id, batch.scope_month, batch.canonical_batch_type as batch_type,
                           batch.total_amount,
                           batch.bank_transaction_ids,
                           count(bank.id)::integer as resolved_member_count,
                           case
                               when batch.canonical_batch_type = 'internal_transfer'
                               then coalesce(max(abs(bank.amount)), 0)::numeric
                               else coalesce(sum(abs(bank.amount)), 0)::numeric
                           end as recalculated_total_amount
                    from source_batches batch
                    left join lateral unnest(batch.bank_transaction_ids) member(row_id) on true
                    left join app.bank_transactions bank
                      on coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
                     and bank.status <> 'deleted'
                    group by batch.batch_id, batch.scope_month, batch.canonical_batch_type, batch.total_amount,
                             batch.bank_transaction_ids
                ),
                relation_members as (
                    select relation.case_id,
                           array_agg(member.row_id order by member.row_id) filter (
                               where relation.row_types[member.ordinality]
                                     in ('bank', 'bank_transaction')
                           ) as bank_transaction_ids
                    from app.workbench_pair_relations relation
                    join lateral unnest(relation.row_ids) with ordinality
                      as member(row_id, ordinality) on true
                    where relation.status = 'active'
                      and relation.relation_mode = 'bank_flow_rule_batch'
                    group by relation.case_id
                )
                select batch.batch_id as subject_id,
                       to_char(batch.scope_month, 'YYYY-MM') as scope_key,
                       cardinality(batch.bank_transaction_ids) as canonical_member_count,
                       batch.resolved_member_count,
                       batch.total_amount::text as canonical_total_amount,
                       batch.recalculated_total_amount::text,
                       relation.bank_transaction_ids as relation_bank_transaction_ids
                from batch_members batch
                left join relation_members relation on relation.case_id = batch.batch_id
                where batch.resolved_member_count <> cardinality(batch.bank_transaction_ids)
                   or abs(batch.total_amount - batch.recalculated_total_amount) > 0.01
                   or (
                        relation.case_id is not null
                        and coalesce(
                            (select array_agg(value order by value) from unnest(batch.bank_transaction_ids) item(value)),
                            array[]::text[]
                        ) <> coalesce(relation.bank_transaction_ids, array[]::text[])
                   )
                order by batch.batch_id
                limit %s
                """,
                (limit,),
                "bank_flow_rule_batches_key_display_fields_mismatch",
            )
        ]
    elif domain == "cost_statistics":
        queries = [
            (
                """
                /* check: key_display_fields */
                select row.row_key as subject_id, row.scope_key,
                       row.amount::text as structured_amount,
                       row.payload->>'amount' as payload_amount,
                       row.project_name as structured_project_name,
                       row.payload->>'project_name' as payload_project_name,
                       row.expense_type as structured_expense_type,
                       row.payload->>'expense_type' as payload_expense_type
                from read_model.cost_statistics_rows row
                where case
                          when replace(coalesce(row.payload->>'amount', ''), ',', '')
                               ~ '^-?[0-9]+([.][0-9]+)?$'
                          then replace(row.payload->>'amount', ',', '')::numeric
                          else null
                      end is distinct from row.amount
                   or coalesce(row.project_name, '') <> coalesce(row.payload->>'project_name', '')
                   or coalesce(row.expense_type, '') <> coalesce(row.payload->>'expense_type', '')
                   or coalesce(row.transaction_id, '') <> coalesce(row.payload->>'transaction_id', '')
                order by row.scope_key, row.row_key
                limit %s
                """,
                (limit,),
                "cost_statistics_key_display_fields_mismatch",
            ),
            (
                """
                /* check: cost_bank_flow_key_fields */
                with projected as (
                    select model.scope_key,
                           substring(model.scope_key from '([0-9]{4}-[0-9]{2})$') as month_key,
                           member.value,
                           member.ordinality
                    from read_model.cost_statistics_read_models model
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(model.payload->'payload'->'bank_flow_time_rows') = 'array'
                            then model.payload->'payload'->'bank_flow_time_rows'
                            else '[]'::jsonb
                        end
                    ) with ordinality member(value, ordinality) on true
                    where model.project_scope = 'all'
                      and model.scope_key ~ '^all:[0-9]{4}-[0-9]{2}$'
                ),
                resolved as (
                    select projected.scope_key, projected.month_key, projected.ordinality,
                           projected.value,
                           source.id::text as canonical_id,
                           coalesce(source.legacy_mongo_id, source.id::text) as canonical_transaction_id,
                           source.amount as canonical_amount,
                           detail.transaction_id as bank_detail_transaction_id,
                           detail.trade_date,
                           detail.counterparty_name,
                           detail.bank_name,
                           detail.account_last4,
                           detail.purpose,
                           detail.summary,
                           detail.effective_category_code,
                           detail.effective_category_label,
                           detail.effective_category_primary_label,
                           detail.effective_category_sub_label,
                           detail.effective_category_label_path,
                           detail.effective_category_path
                    from projected
                    left join app.bank_transactions source
                      on (
                            source.id::text = projected.value->>'transaction_id'
                         or source.legacy_mongo_id = projected.value->>'transaction_id'
                         )
                     and source.status <> 'deleted'
                     and source.txn_direction = 'outflow'
                    left join read_model.bank_detail_rows detail
                      on detail.tenant_id = %s
                     and detail.transaction_id = source.id::text
                ),
                tag_sources as (
                    select resolved.*,
                           case
                               when cardinality(effective_category_label_path) > 0
                               then effective_category_label_path
                               when cardinality(effective_category_path) > 0
                               then effective_category_path
                               else array[]::text[]
                           end as effective_label_path
                    from resolved
                ),
                tagged as (
                    select tag_sources.*,
                           coalesce(
                               effective_category_primary_label,
                               effective_label_path[1],
                               effective_category_label,
                               '未标记'
                           ) as expected_primary_label,
                           coalesce(
                               effective_category_sub_label,
                               effective_label_path[2],
                               effective_category_label,
                               effective_category_primary_label,
                               effective_label_path[1],
                               '未标记'
                           ) as expected_sub_label
                    from tag_sources
                )
                select coalesce(value->>'transaction_id', scope_key || ':' || ordinality::text) as subject_id,
                       scope_key,
                       canonical_transaction_id,
                       canonical_amount::text,
                       value as projected_fields
                from tagged
                where canonical_id is null
                   or bank_detail_transaction_id is null
                   or coalesce(value->>'transaction_id', '') <> coalesce(canonical_transaction_id, '')
                   or month_key <> coalesce(substring(trade_date::text from 1 for 7), '')
                   or case
                          when replace(coalesce(value->>'amount', ''), ',', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                          then abs(replace(value->>'amount', ',', '')::numeric)
                          else null
                      end is distinct from abs(canonical_amount)
                   or coalesce(value->>'counterparty_name', '') <> coalesce(counterparty_name, '')
                   or coalesce(value->>'payment_account_label', '') <> case
                          when coalesce(bank_name, '') <> '' and coalesce(account_last4, '') <> ''
                          then bank_name || ' 账户 ' || account_last4
                          else coalesce(bank_name, account_last4, '')
                      end
                   or coalesce(value->>'direction', '') <> '支出'
                   or coalesce(value->>'remark', '') <> coalesce(nullif(purpose, ''), nullif(summary, ''), '')
                   or coalesce(value->>'project_name', '') <> '未配对OA'
                   or coalesce(value->>'project_id', '') <> ''
                   or coalesce(value->>'oa_applicant', '') <> '—'
                   or coalesce(value->>'expense_type', '') <> coalesce(
                        expected_sub_label, '未标记'
                   )
                   or coalesce(value->>'expense_content', '') <> coalesce(
                        nullif(summary, ''),
                        expected_sub_label,
                        '未标记'
                      )
                   or coalesce(value->>'bank_tag_code', '') <> coalesce(effective_category_code, '')
                   or coalesce(value->>'bank_tag_label', '')
                      <> coalesce(effective_category_label, effective_category_sub_label, '')
                   or coalesce(value->>'bank_tag_primary_label', '')
                      <> coalesce(expected_primary_label, '未标记')
                   or coalesce(value->>'bank_tag_sub_label', '')
                      <> coalesce(expected_sub_label, '未标记')
                   or coalesce(value->'bank_tag_label_path', '[]'::jsonb) <> to_jsonb(
                       case
                           when cardinality(effective_label_path) > 0
                           then effective_label_path
                           when coalesce(expected_primary_label, '未标记')
                                = coalesce(expected_sub_label, '未标记')
                           then array[coalesce(expected_primary_label, '未标记')]::text[]
                           else array[
                                    coalesce(expected_primary_label, '未标记'),
                                    coalesce(expected_sub_label, '未标记')
                                ]::text[]
                       end
                   )
                order by scope_key, subject_id
                limit %s
                """,
                (tenant_id, limit),
                "cost_statistics_bank_flow_key_display_fields_mismatch",
            ),
            (
                """
                /* check: cost_summary_recalculation */
                with recalculated as (
                    select model.scope_key,
                           count(row.row_key)::integer as row_count,
                           coalesce(sum(row.amount), 0)::numeric as total_amount
                    from read_model.cost_statistics_read_models model
                    left join read_model.cost_statistics_rows row on row.scope_key = model.scope_key
                    group by model.scope_key
                ),
                bank_recalculated as (
                    select model.scope_key,
                           count(member.value)::integer as row_count,
                           count(*) filter (
                               where replace(coalesce(member.value->>'amount', ''), ',', '')
                                     ~ '^-?[0-9]+([.][0-9]+)?$'
                           )::integer as valid_amount_count,
                           coalesce(sum(
                               case
                                   when replace(coalesce(member.value->>'amount', ''), ',', '')
                                        ~ '^-?[0-9]+([.][0-9]+)?$'
                                   then abs(replace(member.value->>'amount', ',', '')::numeric)
                                   else 0
                               end
                           ), 0)::numeric as total_amount
                    from read_model.cost_statistics_read_models model
                    left join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(model.payload->'payload'->'bank_flow_time_rows') = 'array'
                            then model.payload->'payload'->'bank_flow_time_rows'
                            else '[]'::jsonb
                        end
                    ) member(value) on true
                    group by model.scope_key
                )
                select model.scope_key as subject_id, model.scope_key,
                       model.payload->'payload'->'summary' as stored_summary,
                       recalculated.row_count,
                       recalculated.total_amount::text as recalculated_total_amount,
                       model.payload->'payload'->'bank_flow_summary' as stored_bank_flow_summary,
                       bank_recalculated.row_count as bank_flow_row_count,
                       bank_recalculated.total_amount::text as bank_flow_total_amount
                from read_model.cost_statistics_read_models model
                join recalculated on recalculated.scope_key = model.scope_key
                join bank_recalculated on bank_recalculated.scope_key = model.scope_key
                where case
                          when coalesce(model.payload->'payload'->'summary'->>'transaction_count', '') ~ '^[0-9]+$'
                          then (model.payload->'payload'->'summary'->>'transaction_count')::integer
                          else -1
                      end <> recalculated.row_count
                   or case
                          when coalesce(model.payload->'payload'->'summary'->>'row_count', '') ~ '^[0-9]+$'
                          then (model.payload->'payload'->'summary'->>'row_count')::integer
                          else -1
                      end <> recalculated.row_count
                   or replace(
                        coalesce(model.payload->'payload'->'summary'->>'total_amount', ''), ',', ''
                      ) !~ '^-?[0-9]+([.][0-9]+)?$'
                   or abs(
                        case
                            when replace(
                                    coalesce(model.payload->'payload'->'summary'->>'total_amount', ''), ',', ''
                                 ) ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(
                                    model.payload->'payload'->'summary'->>'total_amount', ',', ''
                                 )::numeric
                            else 0
                        end
                        - recalculated.total_amount
                   ) > 0.01
                   or bank_recalculated.valid_amount_count <> bank_recalculated.row_count
                   or case
                          when coalesce(
                                   model.payload->'payload'->'bank_flow_summary'->>'transaction_count', ''
                               ) ~ '^[0-9]+$'
                          then (model.payload->'payload'->'bank_flow_summary'->>'transaction_count')::integer
                          else -1
                      end <> bank_recalculated.row_count
                   or case
                          when coalesce(model.payload->'payload'->'bank_flow_summary'->>'row_count', '') ~ '^[0-9]+$'
                          then (model.payload->'payload'->'bank_flow_summary'->>'row_count')::integer
                          else -1
                      end <> bank_recalculated.row_count
                   or replace(
                        coalesce(model.payload->'payload'->'bank_flow_summary'->>'total_amount', ''), ',', ''
                      ) !~ '^-?[0-9]+([.][0-9]+)?$'
                   or abs(
                        case
                            when replace(
                                    coalesce(
                                        model.payload->'payload'->'bank_flow_summary'->>'total_amount', ''
                                    ), ',', ''
                                 ) ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(
                                    model.payload->'payload'->'bank_flow_summary'->>'total_amount', ',', ''
                                 )::numeric
                            else 0
                        end
                        - bank_recalculated.total_amount
                   ) > 0.01
                order by model.scope_key
                limit %s
                """,
                (limit,),
                "cost_statistics_summary_recalculation_mismatch",
            ),
            (
                """
                /* check: cost_group_summaries */
                with expected_scope_rows as (
                    select scope_key, project_name, expense_type, amount
                    from read_model.cost_statistics_rows
                    union all
                    select project_scope || ':all', project_name, expense_type, amount
                    from read_model.cost_statistics_rows
                    where scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
                ),
                expected_projects as (
                    select scope_key, project_name as group_key,
                           count(*)::integer as transaction_count,
                           count(distinct expense_type)::integer as related_count,
                           sum(amount)::numeric as total_amount
                    from expected_scope_rows
                    group by scope_key, project_name
                ),
                projected_projects as (
                    select model.scope_key, member.value->>'project_name' as group_key,
                           case
                               when coalesce(member.value->>'transaction_count', '') ~ '^[0-9]+$'
                               then (member.value->>'transaction_count')::integer
                           end as transaction_count,
                           case
                               when coalesce(member.value->>'expense_type_count', '') ~ '^[0-9]+$'
                               then (member.value->>'expense_type_count')::integer
                           end as related_count,
                           case
                               when replace(coalesce(member.value->>'total_amount', ''), ',', '')
                                    ~ '^-?[0-9]+([.][0-9]+)?$'
                               then replace(member.value->>'total_amount', ',', '')::numeric
                           end as total_amount,
                           count(*) over (
                               partition by model.scope_key, member.value->>'project_name'
                           )::integer as projection_identity_count
                    from read_model.cost_statistics_read_models model
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(model.payload->'payload'->'project_rows') = 'array'
                            then model.payload->'payload'->'project_rows'
                            else '[]'::jsonb
                        end
                    ) member(value) on true
                ),
                project_mismatches as (
                    select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                           coalesce(expected.group_key, projected.group_key) as group_key,
                           expected.transaction_count as expected_transaction_count,
                           projected.transaction_count as projected_transaction_count,
                           expected.related_count as expected_related_count,
                           projected.related_count as projected_related_count,
                           expected.total_amount as expected_total_amount,
                           projected.total_amount as projected_total_amount,
                           projected.projection_identity_count
                    from expected_projects expected
                    full join projected_projects projected
                      on projected.scope_key = expected.scope_key
                     and projected.group_key = expected.group_key
                    where expected.group_key is null
                       or projected.group_key is null
                       or projected.projection_identity_count <> 1
                       or expected.transaction_count is distinct from projected.transaction_count
                       or expected.related_count is distinct from projected.related_count
                       or abs(coalesce(expected.total_amount, 0) - coalesce(projected.total_amount, 0)) > 0.01
                ),
                expected_expenses as (
                    select scope_key, expense_type as group_key,
                           count(*)::integer as transaction_count,
                           count(distinct project_name)::integer as related_count,
                           sum(amount)::numeric as total_amount
                    from expected_scope_rows
                    group by scope_key, expense_type
                ),
                projected_expenses as (
                    select model.scope_key, member.value->>'expense_type' as group_key,
                           case
                               when coalesce(member.value->>'transaction_count', '') ~ '^[0-9]+$'
                               then (member.value->>'transaction_count')::integer
                           end as transaction_count,
                           case
                               when coalesce(member.value->>'project_count', '') ~ '^[0-9]+$'
                               then (member.value->>'project_count')::integer
                           end as related_count,
                           case
                               when replace(coalesce(member.value->>'total_amount', ''), ',', '')
                                    ~ '^-?[0-9]+([.][0-9]+)?$'
                               then replace(member.value->>'total_amount', ',', '')::numeric
                           end as total_amount,
                           count(*) over (
                               partition by model.scope_key, member.value->>'expense_type'
                           )::integer as projection_identity_count
                    from read_model.cost_statistics_read_models model
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(model.payload->'payload'->'expense_type_rows') = 'array'
                            then model.payload->'payload'->'expense_type_rows'
                            else '[]'::jsonb
                        end
                    ) member(value) on true
                ),
                expense_mismatches as (
                    select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                           coalesce(expected.group_key, projected.group_key) as group_key,
                           expected.transaction_count as expected_transaction_count,
                           projected.transaction_count as projected_transaction_count,
                           expected.related_count as expected_related_count,
                           projected.related_count as projected_related_count,
                           expected.total_amount as expected_total_amount,
                           projected.total_amount as projected_total_amount,
                           projected.projection_identity_count
                    from expected_expenses expected
                    full join projected_expenses projected
                      on projected.scope_key = expected.scope_key
                     and projected.group_key = expected.group_key
                    where expected.group_key is null
                       or projected.group_key is null
                       or projected.projection_identity_count <> 1
                       or expected.transaction_count is distinct from projected.transaction_count
                       or expected.related_count is distinct from projected.related_count
                       or abs(coalesce(expected.total_amount, 0) - coalesce(projected.total_amount, 0)) > 0.01
                )
                select scope_key || ':project:' || coalesce(group_key, '') as subject_id,
                       scope_key, 'project' as summary_kind, group_key,
                       expected_transaction_count, projected_transaction_count,
                       expected_related_count, projected_related_count,
                       expected_total_amount::text, projected_total_amount::text
                from project_mismatches
                union all
                select scope_key || ':expense:' || coalesce(group_key, '') as subject_id,
                       scope_key, 'expense_type' as summary_kind, group_key,
                       expected_transaction_count, projected_transaction_count,
                       expected_related_count, projected_related_count,
                       expected_total_amount::text, projected_total_amount::text
                from expense_mismatches
                order by scope_key, subject_id
                limit %s
                """,
                (limit,),
                "cost_statistics_group_summaries_mismatch",
            ),
            (
                """
                /* check: cost_bank_accounts */
                with models as (
                    select scope_key, payload
                    from read_model.cost_statistics_read_models
                ),
                settings as (
                    select coalesce(settings_payload, '{}'::jsonb) as payload
                    from app.app_settings
                    where settings_key = 'app_settings'
                    limit 1
                ),
                mapping_items as (
                    select coalesce(nullif(btrim(item.value->>'bank_name'), ''),
                                    nullif(btrim(item.value->>'bankName'), '')) as bank_name,
                           btrim(coalesce(item.value->>'last4', '')) as account_last4,
                           item.ordinality
                    from (select coalesce((select payload from settings), '{}'::jsonb) as payload) source
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(source.payload->'bank_account_mappings') = 'array'
                            then source.payload->'bank_account_mappings'
                            else '[]'::jsonb
                        end
                    ) with ordinality item(value, ordinality) on true
                ),
                expected as (
                    select distinct on (bank_name, account_last4)
                           bank_name, account_last4,
                           bank_name || ' 账户 ' || account_last4 as payment_account_label,
                           'settings'::text as source
                    from mapping_items
                    where bank_name is not null
                      and account_last4 ~ '^[0-9]{4}$'
                    order by bank_name, account_last4, ordinality
                ),
                expected_by_model as (
                    select model.scope_key, expected.*
                    from models model
                    cross join expected
                ),
                projected as (
                    select model.scope_key,
                           btrim(coalesce(member.value->>'bank_name', '')) as bank_name,
                           btrim(coalesce(member.value->>'account_last4', '')) as account_last4,
                           coalesce(member.value->>'payment_account_label', '') as payment_account_label,
                           coalesce(member.value->>'source', '') as source,
                           count(*) over (
                               partition by model.scope_key,
                                            btrim(coalesce(member.value->>'bank_name', '')),
                                            btrim(coalesce(member.value->>'account_last4', ''))
                           )::integer as projection_identity_count
                    from models model
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(model.payload->'payload'->'bank_accounts') = 'array'
                            then model.payload->'payload'->'bank_accounts'
                            else '[]'::jsonb
                        end
                    ) member(value) on true
                ),
                mismatches as (
                    select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                           coalesce(expected.bank_name, projected.bank_name) as bank_name,
                           coalesce(expected.account_last4, projected.account_last4) as account_last4,
                           expected.payment_account_label as expected_payment_account_label,
                           projected.payment_account_label as projected_payment_account_label,
                           expected.source as expected_source,
                           projected.source as projected_source,
                           projected.projection_identity_count
                    from expected_by_model expected
                    full join projected
                      on projected.scope_key = expected.scope_key
                     and projected.bank_name = expected.bank_name
                     and projected.account_last4 = expected.account_last4
                    where expected.scope_key is null
                       or projected.scope_key is null
                       or projected.projection_identity_count <> 1
                       or projected.payment_account_label <> expected.payment_account_label
                       or projected.source <> expected.source
                )
                select scope_key || ':' || coalesce(bank_name, '') || ':' || coalesce(account_last4, '') as subject_id,
                       scope_key, bank_name, account_last4,
                       expected_payment_account_label, projected_payment_account_label,
                       expected_source, projected_source, projection_identity_count
                from mismatches
                union all
                select model.scope_key || ':invalid-bank-accounts' as subject_id,
                       model.scope_key, null::text, null::text,
                       null::text, null::text, null::text, null::text, null::integer
                from models model
                where jsonb_typeof(model.payload->'payload'->'bank_accounts') is distinct from 'array'
                order by scope_key, subject_id
                limit %s
                """,
                (limit,),
                "cost_statistics_bank_accounts_mismatch",
            ),
        ]
    else:
        return []
    issues: list[AuditIssue] = []
    for sql, params, code in queries:
        issues.extend(
            _proof_query_issues(
                connection,
                sql=sql,
                params=params,
                code=code,
                message=f"{contract.label} stored display fields do not equal independently recalculated fields.",
            )
        )
    return issues


def _proof_query_issues(
    connection: Any,
    *,
    sql: str,
    params: tuple[Any, ...],
    code: str,
    message: str,
) -> list[AuditIssue]:
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=code,
            message=message,
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={
                key: _jsonable(value)
                for key, value in row.items()
                if key not in {"subject_id", "scope_key"}
            },
        )
        for row in rows
    ]


def _bank_account_balance_equality_sql() -> str:
    return """
    /* check: bank_account_balance_equality */
    with source_rows as (
        select coalesce(legacy_mongo_id, id::text) as transaction_id,
               balance, coalesce(trade_time, txn_date::timestamptz) as trade_time_sort,
               bank_serial_no,
               nullif(regexp_replace(coalesce(account_no, ''), '[^[:alnum:]]', '', 'g'), '')
                   as normalized_account_no,
               coalesce(
                   nullif(raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                   nullif(raw_payload->'normalized_payload'->>'bank_name', ''),
                   '未知银行'
               ) as bank_name,
               right(coalesce(
                   nullif(raw_payload->'normalized_payload'->>'imported_bank_last4', ''),
                   nullif(raw_payload->'normalized_payload'->>'account_last4', ''),
                   nullif(regexp_replace(coalesce(account_no, ''), '[^[:alnum:]]', '', 'g'), ''),
                   'unknown'
               ), 4) as account_last4
        from app.bank_transactions
        where (balance is not null or account_no is not null or raw_payload is not null)
          and coalesce(nullif(status, ''), 'active')
              not in ('deleted', 'void', 'voided', 'cancelled', 'canceled', 'ignored')
    ),
    identity_rows as (
        select *,
               case
                   when normalized_account_no is not null then
                       'acct:' || substring(encode(digest(normalized_account_no, 'sha256'), 'hex') from 1 for 24)
                   else 'fallback:' || substring(
                       encode(digest(lower(btrim(bank_name)) || ':' || account_last4, 'sha256'), 'hex')
                       from 1 for 24
                   )
               end as account_identity
        from source_rows
    ),
    expected_counts as (
        select account_identity, count(*)::bigint as transaction_total_count
        from identity_rows group by account_identity
    ),
    expected_latest as (
        select distinct on (account_identity)
               account_identity, balance as latest_balance,
               transaction_id as latest_balance_transaction_id
        from identity_rows
        where balance is not null
        order by account_identity, trade_time_sort desc nulls last,
                 bank_serial_no desc nulls last, transaction_id desc
    ),
    expected as (
        select counts.account_identity, counts.transaction_total_count,
               latest.latest_balance, latest.latest_balance_transaction_id
        from expected_counts counts
        left join expected_latest latest using (account_identity)
    ),
    mismatches as (
        select coalesce(expected.account_identity, projected.account_identity) as account_identity,
               expected.transaction_total_count as expected_count,
               projected.transaction_total_count as projected_count,
               expected.latest_balance as expected_balance,
               projected.latest_balance as projected_balance,
               expected.latest_balance_transaction_id as expected_transaction_id,
               projected.latest_balance_transaction_id as projected_transaction_id
        from expected
        full join read_model.bank_account_balances projected
          on projected.tenant_id = %s
         and projected.account_identity = expected.account_identity
        where expected.account_identity is null
           or projected.account_identity is null
           or expected.transaction_total_count <> projected.transaction_total_count
           or expected.latest_balance is distinct from projected.latest_balance
           or coalesce(expected.latest_balance_transaction_id, '')
              <> coalesce(projected.latest_balance_transaction_id, '')
    )
    select account_identity as subject_id, 'all' as scope_key,
           expected_count, projected_count,
           expected_balance::text, projected_balance::text,
           expected_transaction_id, projected_transaction_id
    from mismatches
    order by account_identity
    limit %s
    """


def _relation_edge_equality_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if not contract.relation_tables:
        return []
    return workbench_relation_edge_equality_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit,
        code_prefix=contract.domain_key,
        label=contract.label,
    )


def _consumer_relation_edge_equality_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if contract.consumer_relation_contract is None:
        return []
    return page_consumer_relation_edge_equality_issues(
        connection,
        consumer_contract=contract.consumer_relation_contract,
        tenant_id=tenant_id,
        limit=limit,
        code_prefix=contract.domain_key,
        label=contract.label,
    )


def _upstream_dependency_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if contract.domain_key != "cost_statistics":
        return []

    workbench_issues, _summary = collect_workbench_page_integrity_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit,
    )
    bank_contract = PAGE_AUDIT_CONTRACTS["bank_details"]
    bank_checks: tuple[Callable[[Any, PageAuditContract, str, int], list[AuditIssue]], ...] = (
        _scope_row_count_mismatch_issues,
        _read_model_source_version_mismatch_issues,
        _missing_read_model_scope_issues,
        _missing_read_model_row_issues,
        _orphan_read_model_row_issues,
        _duplicate_read_model_identity_issues,
        _canonical_expected_set_issues,
        _key_display_field_issues,
    )
    bank_issues: list[AuditIssue] = []
    for check in bank_checks:
        bank_issues.extend(check(connection, bank_contract, tenant_id, limit))

    return [
        _dependency_issue(issue, dependency="workbench")
        for issue in workbench_issues
    ] + [
        _dependency_issue(issue, dependency="bank_details")
        for issue in bank_issues
    ]


def _dependency_issue(issue: AuditIssue, *, dependency: str) -> AuditIssue:
    details = dict(issue.details or {})
    details["dependency"] = dependency
    details["dependency_issue_code"] = issue.code
    return AuditIssue(
        severity=issue.severity,
        code=f"cost_statistics_dependency_{dependency}_{issue.code}",
        message=f"成本统计依赖的 {dependency} 完整性证明失败：{issue.message}",
        subject_id=issue.subject_id,
        scope_key=issue.scope_key,
        details=details,
    )


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


def _embedded_relation_source_summary_query(
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
        with canonical_relation_summary as (
            select {alias}.scope_key,
                   jsonb_build_object(
                       'source', 'workbench_pair_relations',
                       'scope_key', {alias}.scope_key,
                       'relation_count', count(relation.id)::integer,
                       'relation_updated_at', coalesce(max(relation.updated_at)::text, '')
                   ) as source_versions
            from {scope_table} {alias}
            left join app.workbench_pair_relations relation
              on relation.status = 'active'
             and relation.month_scope = ({alias}.scope_key || '-01')::date
            where {alias}.tenant_id = %s
              and {alias}.scope_key ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            group by {alias}.scope_key
        )
        select {alias}.scope_key,
               {alias}.source_versions->'workbench_relation_source_versions' as embedded_relation_versions,
               canonical.source_versions as current_relation_versions
        from {scope_table} {alias}
        join canonical_relation_summary canonical on canonical.scope_key = {alias}.scope_key
        where {alias}.tenant_id = %s
          and {alias}.source_versions ? 'workbench_relation_source_versions'
          and coalesce({alias}.source_versions->'workbench_relation_source_versions', '{{}}'::jsonb)
              <> canonical.source_versions
        order by {alias}.scope_key
        limit %s
        """,
        (tenant_id, tenant_id, limit),
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
