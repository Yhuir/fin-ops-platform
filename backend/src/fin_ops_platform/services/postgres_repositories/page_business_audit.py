from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any

from fin_ops_platform.services.oa_pending_payment_sql_projection import oa_pending_payment_base_source_versions
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
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
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresInvoiceUsageCollectionReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation_audit import (
    workbench_relation_edge_equality_issues,
)
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE


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
        label="OA 待付款核对",
        source_tables=(
            "app.oa_applications",
            "app.oa_application_items",
            "app.oa_pending_payment_admissions",
            "app.oa_pending_payment_bank_relations",
            "app.oa_pending_payment_status_snapshots",
            "app.oa_sync_watermarks",
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
        _page_statistics_issues,
        _read_model_source_version_mismatch_issues,
        _oa_pending_payment_fresh_gate_issues,
        _missing_read_model_scope_issues,
        _missing_read_model_row_issues,
        _orphan_read_model_row_issues,
        _duplicate_read_model_identity_issues,
        _canonical_expected_set_issues,
        _key_display_field_issues,
        _relation_edge_equality_issues,
        _consumer_relation_edge_equality_issues,
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
                "page_statistics_recalculation",
                "bidirectional_relation_edge_equality",
                *(["consumer_relation_edge_equality"] if contract.consumer_relation_contract else []),
                *(
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


def _page_statistics_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if contract.domain_key == "oa_pending_payments":
        rows = connection.fetch_all(
            """
            /* check: oa_pending_payment_page_statistics_recalculation */
            with canonical_oa as (
                select row_id as oa_id, to_char(scope_month, 'YYYY-MM') as scope_key, 'completed' as workflow_kind
                from app.oa_applications
                where status <> 'deleted'
                  and scope_month is not null
                  and (
                        workflow_status is null or workflow_status = ''
                     or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
                  )
                union
                select oa_id, scope_key, 'in_progress' as workflow_kind
                from app.oa_pending_payment_admissions
                where tenant_id = %s
                  and workflow_status = 'in_progress'
            ), canonical_counts as (
                select scope_key,
                       count(distinct oa_id)::integer as oa_count,
                       count(distinct oa_id) filter (where workflow_kind = 'completed')::integer as completed_oa_count,
                       count(distinct oa_id) filter (where workflow_kind = 'in_progress')::integer as in_progress_oa_count
                from canonical_oa
                group by scope_key
            ), projected_oa as (
                select row.scope_key, member.oa_id,
                       bool_or(row.payment_status = 'paid') as paid,
                       bool_or(
                           coalesce((row.payload->'bankTransaction'->>'linkedRelationCount')::integer, 0) > 0
                       ) as linked_bank,
                       bool_or(exists (
                           select 1
                           from jsonb_array_elements(
                               case
                                   when jsonb_typeof(row.payload->'invoice'->'summaries') = 'array'
                                   then row.payload->'invoice'->'summaries'
                                   else '[]'::jsonb
                               end
                           ) invoice(value)
                           where invoice.value->>'relationStatus' = 'linked'
                       )) as linked_input_invoice
                from read_model.oa_pending_payment_rows row
                join lateral unnest(
                    case
                        when cardinality(row.oa_ids) > 0 then row.oa_ids
                        else array[row.oa_id]
                    end
                ) member(oa_id) on true
                group by row.scope_key, member.oa_id
            ), projected_counts as (
                select scope_key,
                       count(*) filter (where paid)::integer as paid_oa_count,
                       count(*) filter (where linked_bank)::integer as linked_bank_oa_count,
                       count(*) filter (where linked_input_invoice)::integer as linked_input_invoice_oa_count
                from projected_oa
                group by scope_key
            ), bank_counts as (
                select to_char(txn_month, 'YYYY-MM') as scope_key,
                       count(distinct coalesce(legacy_mongo_id, id::text))::integer as bank_transaction_count,
                       count(distinct coalesce(legacy_mongo_id, id::text)) filter (
                           where txn_direction = 'outflow'
                       )::integer as expense_transaction_count,
                       count(distinct coalesce(legacy_mongo_id, id::text)) filter (
                           where txn_direction = 'inflow'
                       )::integer as income_transaction_count,
                       md5(coalesce(string_agg(
                           concat(
                               coalesce(legacy_mongo_id, id::text),
                               '|',
                               coalesce(txn_direction, '')
                           ),
                           E'\n' order by coalesce(legacy_mongo_id, id::text)
                       ), '')) as membership_digest
                from app.bank_transactions
                where status <> 'deleted' and txn_month is not null
                group by txn_month
            ), invoice_counts as (
                select to_char(invoice_month, 'YYYY-MM') as scope_key,
                       count(distinct coalesce(legacy_mongo_id, id::text))::integer as input_invoice_count,
                       md5(coalesce(string_agg(
                           concat(
                               coalesce(legacy_mongo_id, id::text),
                               '|',
                               coalesce(invoice_type, '')
                           ),
                           E'\n' order by coalesce(legacy_mongo_id, id::text)
                       ), '')) as membership_digest
                from app.invoices
                where status <> 'deleted'
                  and invoice_month is not null
                  and not (
                      coalesce(invoice_type, '') ilike '%%output%%'
                      or coalesce(invoice_type, '') like '%%销%%'
                  )
                group by invoice_month
            ), recalculated as (
                select scope.scope_key,
                       jsonb_build_object(
                           'oa_count', coalesce(canonical.oa_count, 0),
                           'bank_transaction_count', coalesce(bank.bank_transaction_count, 0),
                           'input_invoice_count', coalesce(invoice.input_invoice_count, 0),
                           'paid_oa_count', coalesce(projected.paid_oa_count, 0),
                           'completed_oa_count', coalesce(canonical.completed_oa_count, 0),
                           'in_progress_oa_count', coalesce(canonical.in_progress_oa_count, 0),
                           'expense_transaction_count', coalesce(bank.expense_transaction_count, 0),
                           'income_transaction_count', coalesce(bank.income_transaction_count, 0),
                           'unpaid_oa_count', greatest(
                               coalesce(canonical.oa_count, 0) - coalesce(projected.paid_oa_count, 0), 0
                           ),
                           'linked_bank_oa_count', coalesce(projected.linked_bank_oa_count, 0),
                           'linked_input_invoice_oa_count', coalesce(projected.linked_input_invoice_oa_count, 0)
                       ) as statistics,
                       concat(
                           'rows:', coalesce(bank.bank_transaction_count, 0),
                           '|digest:', coalesce(bank.membership_digest, md5(''))
                       ) as bank_coverage_signature,
                       concat(
                           'rows:', coalesce(invoice.input_invoice_count, 0),
                           '|digest:', coalesce(invoice.membership_digest, md5(''))
                       ) as input_invoice_coverage_signature
                from read_model.oa_pending_payment_scopes scope
                left join canonical_counts canonical using (scope_key)
                left join projected_counts projected using (scope_key)
                left join bank_counts bank using (scope_key)
                left join invoice_counts invoice using (scope_key)
                where scope.scope_key <> 'all'
            )
            select scope.scope_key,
                   scope.raw_payload->'statistics' as stored_statistics,
                   recalculated.statistics as recalculated_statistics,
                   scope.source_versions->>'oa_pending_payment_bank_coverage_signature'
                       as stored_bank_coverage_signature,
                   recalculated.bank_coverage_signature as recalculated_bank_coverage_signature,
                   scope.source_versions->>'oa_pending_payment_input_invoice_coverage_signature'
                       as stored_input_invoice_coverage_signature,
                   recalculated.input_invoice_coverage_signature as recalculated_input_invoice_coverage_signature
            from read_model.oa_pending_payment_scopes scope
            join recalculated using (scope_key)
            where scope.raw_payload->'statistics' is distinct from recalculated.statistics
               or scope.source_versions->>'oa_pending_payment_bank_coverage_signature'
                    is distinct from recalculated.bank_coverage_signature
               or scope.source_versions->>'oa_pending_payment_input_invoice_coverage_signature'
                    is distinct from recalculated.input_invoice_coverage_signature
            order by scope.scope_key
            limit %s
            """,
            (tenant_id, limit),
        )
        return [
            AuditIssue(
                severity="error",
                code="oa_pending_payments_page_statistics_mismatch",
                message="OA 待付款核对页面统计与独立重算结果不一致。",
                scope_key=_text(row.get("scope_key")),
                details=_details(
                    row,
                    "stored_statistics",
                    "recalculated_statistics",
                    "stored_bank_coverage_signature",
                    "recalculated_bank_coverage_signature",
                    "stored_input_invoice_coverage_signature",
                    "recalculated_input_invoice_coverage_signature",
                ),
            )
            for row in rows
        ]
    if contract.domain_key != "bank_details":
        return []
    rows = connection.fetch_all(
        """
        /* check: page_statistics_recalculation */
        with recalculated as (
            select scope.scope_key,
                   jsonb_build_object(
                       'transaction_count', count(row.transaction_id)::integer,
                       'expense_transaction_count', count(row.transaction_id) filter (
                           where row.direction = 'expense'
                       )::integer,
                       'income_transaction_count', count(row.transaction_id) filter (
                           where row.direction = 'income'
                       )::integer,
                       'classified_transaction_count', count(row.transaction_id) filter (
                           where nullif(btrim(row.effective_category_code), '') is not null
                       )::integer,
                       'unclassified_transaction_count', count(row.transaction_id) filter (
                           where nullif(btrim(row.effective_category_code), '') is null
                       )::integer,
                       'linked_transaction_count', count(row.transaction_id) filter (
                           where row.payload->>'relation_status' = 'linked'
                       )::integer,
                       'unlinked_transaction_count', count(row.transaction_id) filter (
                           where coalesce(row.payload->>'relation_status', '') <> 'linked'
                       )::integer
                   ) as statistics
            from read_model.bank_detail_scopes scope
            left join read_model.bank_detail_rows row
              on row.tenant_id = scope.tenant_id
             and row.scope_key = scope.scope_key
            where scope.tenant_id = %s
              and scope.scope_type = 'bank_detail'
            group by scope.scope_key
        )
        select scope.scope_key,
               scope.raw_payload->'statistics' as stored_statistics,
               recalculated.statistics as recalculated_statistics
        from read_model.bank_detail_scopes scope
        join recalculated on recalculated.scope_key = scope.scope_key
        where scope.tenant_id = %s
          and scope.scope_type = 'bank_detail'
          and scope.raw_payload->'statistics' is distinct from recalculated.statistics
        order by scope.scope_key
        limit %s
        """,
        (tenant_id, tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="bank_details_page_statistics_mismatch",
            message="银行明细页面统计与页面 Read model 行不一致。",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "stored_statistics", "recalculated_statistics"),
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


def _oa_pending_payment_fresh_gate_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if contract.domain_key != "oa_pending_payments":
        return []
    state = OaPendingPaymentReadModelRepositoryPort(
        PostgresInvoiceUsageCollectionReadModelRepository(connection)
    ).query_state(
        scope_key="all",
        tenant_id=tenant_id,
        base_source_versions=oa_pending_payment_base_source_versions(),
    ) or {}
    if state.get("status") == "fresh":
        return []
    blocking_scope_keys = [str(value) for value in state.get("blocking_scope_keys", []) if str(value).strip()]
    stale_reasons = [str(value) for value in state.get("stale_reasons", []) if str(value).strip()]
    actual_by_scope = state.get("source_versions_by_scope")
    expected_by_scope = state.get("expected_source_versions_by_scope")
    return [
        AuditIssue(
            severity="error",
            code="read_model_scope_not_fresh",
            message="OA 待付款核对的动态来源版本与已发布 Read model 不一致。",
            subject_id="oa_pending_payment",
            scope_key=scope_key,
            details={
                "reasons": [reason for reason in stale_reasons if reason == scope_key or reason.startswith(f"{scope_key}:")],
                "actual_source_versions": (
                    actual_by_scope.get(scope_key) if isinstance(actual_by_scope, dict) else None
                ),
                "expected_source_versions": (
                    expected_by_scope.get(scope_key) if isinstance(expected_by_scope, dict) else None
                ),
            },
        )
        for scope_key in blocking_scope_keys[:limit]
    ] or [
        AuditIssue(
            severity="error",
            code="read_model_scope_not_fresh",
            message="OA 待付款核对的动态来源版本与已发布 Read model 不一致。",
            subject_id="oa_pending_payment",
            scope_key="all",
            details={"reasons": stale_reasons},
        )
    ]


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
        select member.oa_id as subject_id, row.scope_key, row.row_id
        from read_model.oa_pending_payment_rows row
        join lateral unnest(row.oa_ids) member(oa_id) on true
        left join canonical source
          on source.oa_id = member.oa_id
        where nullif(member.oa_id, '') is not null
          and source.oa_id is null
        order by row.scope_key, member.oa_id
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
        select
            row_id as subject_id,
            min(scope_key) as scope_key,
            count(*)::integer as row_count,
            array_agg(distinct scope_key order by scope_key) as scope_keys
        from read_model.oa_pending_payment_rows
        group by row_id
        having count(*) > 1
        order by row_id
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
            select distinct member.oa_id, row.scope_key
            from read_model.oa_pending_payment_rows row
            join lateral unnest(row.oa_ids) member(oa_id) on true
        ),
        mismatches as (
            select 'canonical_missing_projection' as mismatch_kind,
                   canonical.oa_id, canonical.scope_key
            from canonical
            where not exists (
                select 1 from projected
                where projected.oa_id = canonical.oa_id
                  and projected.scope_key = canonical.scope_key
            )
            union all
            select 'projection_not_registered_in_app', projected.oa_id, projected.scope_key
            from projected
            where not exists (
                select 1 from canonical source
                where source.oa_id = projected.oa_id
                  and source.scope_key = projected.scope_key
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
            ),
            (
                """
                /* check: turnover_statistics_projection */
                with expected as (
                    select ledger.relation_id,
                           member.row_id,
                           case when source.txn_direction = 'inflow' then 'income' else 'expense' end
                               as expected_direction
                    from read_model.turnover_ledger_rows ledger
                    join lateral unnest(ledger.bank_row_ids) member(row_id) on true
                    left join app.bank_transactions source
                      on coalesce(source.legacy_mongo_id, source.id::text) = member.row_id
                     and source.status <> 'deleted'
                ), projected as (
                    select ledger.relation_id,
                           nullif(btrim(flow.value->>'source_bank_row_id'), '') as row_id,
                           flow.value->>'flow_direction' as flow_direction,
                           count(*) over (
                               partition by ledger.relation_id, flow.value->>'source_bank_row_id'
                           )::integer as identity_count
                    from read_model.turnover_ledger_rows ledger
                    join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(ledger.payload->'flow_rows') = 'array'
                            then ledger.payload->'flow_rows'
                            else '[]'::jsonb
                        end
                    ) flow(value) on true
                ), mismatches as (
                    select coalesce(expected.relation_id, projected.relation_id) as relation_id,
                           coalesce(expected.row_id, projected.row_id) as row_id,
                           expected.expected_direction,
                           projected.flow_direction,
                           projected.identity_count
                    from expected
                    full join projected
                      on projected.relation_id = expected.relation_id
                     and projected.row_id = expected.row_id
                    where expected.row_id is null
                       or projected.row_id is null
                       or projected.identity_count <> 1
                       or projected.flow_direction <> expected.expected_direction
                )
                select relation_id || ':' || coalesce(row_id, '') as subject_id,
                       relation_id as scope_key,
                       row_id, expected_direction, flow_direction, identity_count
                from mismatches
                order by relation_id, row_id
                limit %s
                """,
                (limit,),
                "turnover_ledger_statistics_projection_mismatch",
            ),
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






def collect_bank_detail_projection_integrity_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    """Return the registered Bank Detail canonical/field/version proof for downstream consumers."""
    contract = PAGE_AUDIT_CONTRACTS["bank_details"]
    checks: tuple[Callable[[Any, PageAuditContract, str, int], list[AuditIssue]], ...] = (
        _scope_row_count_mismatch_issues,
        _page_statistics_issues,
        _read_model_source_version_mismatch_issues,
        _missing_read_model_scope_issues,
        _missing_read_model_row_issues,
        _orphan_read_model_row_issues,
        _duplicate_read_model_identity_issues,
        _canonical_expected_set_issues,
        _key_display_field_issues,
    )
    issues: list[AuditIssue] = []
    for check in checks:
        issues.extend(check(connection, contract, tenant_id, limit))
    return issues


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
        with scope_bank_identities as (
            select {alias}.scope_key,
                   coalesce(
                       array_agg(distinct identity.row_id) filter (where identity.row_id is not null),
                       '{{}}'::text[]
                   ) as row_ids
            from {scope_table} {alias}
            left join app.bank_transactions source
              on source.status <> 'deleted'
             and source.txn_date >= ({alias}.scope_key || '-01')::date
             and source.txn_date < (({alias}.scope_key || '-01')::date + interval '1 month')
            left join lateral (
                select unnest(array[
                    coalesce(source.legacy_mongo_id, source.id::text),
                    source.id::text
                ]) as row_id
            ) identity on source.id is not null
            where {alias}.tenant_id = %s
              and {alias}.scope_key ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            group by {alias}.scope_key
        ),
        canonical_relation_summary as (
            select {alias}.scope_key,
                   jsonb_build_object(
                       'source', 'workbench_pair_relations',
                       'scope_key', {alias}.scope_key,
                       'relation_count', count(relation.id)::integer,
                       'relation_updated_at', coalesce(max(relation.updated_at)::text, '')
                   ) as source_versions
            from {scope_table} {alias}
            join scope_bank_identities identities on identities.scope_key = {alias}.scope_key
            left join app.workbench_pair_relations relation
              on relation.status = 'active'
             and relation.relation_mode <> %s
             and (
                    relation.month_scope = ({alias}.scope_key || '-01')::date
                 or relation.row_ids && identities.row_ids
             )
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
        (
            tenant_id,
            TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
            tenant_id,
            tenant_id,
            limit,
        ),
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
