from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.page_consumer_relation_audit import (
    BANK_FLOW_RULE_BATCH_CONSUMER,
    page_consumer_relation_edge_equality_issues,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    list_oa_pending_payment_relation_visibility_gaps,
)


@dataclass(frozen=True)
class PageAuditContract:
    domain_key: str
    label: str
    source_tables: tuple[str, ...]
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
        source_tables=(
            "app.bank_transactions",
            "app.bank_transaction_categories",
            "app.workbench_pair_relations",
        ),
        relation_tables=("app.workbench_pair_relations",),
        canonical_expected_set=(
            "active canonical bank transactions, effective categories, pending rules/status overrides, "
            "invoice/OA facts, and active relation membership read in one database snapshot"
        ),
        key_display_fields=("transaction_id", "direction", "scope_month", "trade_date", "amount", "counterparty_name", "status_code"),
        external_source_boundary="bank statement completeness before App import",
    ),
    "input_invoice_usage": PageAuditContract(
        domain_key="input_invoice_usage",
        label="进项发票使用情况",
        source_tables=(
            "app.invoices",
            "app.oa_applications",
            "app.bank_transactions",
            "app.workbench_pair_relations",
            "app.input_invoice_usage_oa_reverse_batches",
            "app.app_settings",
        ),
        relation_tables=("app.workbench_pair_relations",),
        canonical_expected_set=(
            "active input invoices, OA and bank facts, payment rules, OA reverse batches, "
            "and active relation membership read in one database snapshot"
        ),
        key_display_fields=("invoice_id", "invoice_no", "invoice_date", "total_with_tax", "payment_status", "relation members"),
        external_source_boundary="invoice, OA, and bank completeness before App import",
    ),
    "output_invoice_collection": PageAuditContract(
        domain_key="output_invoice_collection",
        label="销项发票收款情况",
        source_tables=(
            "app.invoices",
            "app.bank_transactions",
            "app.workbench_pair_relations",
            "app.output_invoice_collection_status_overrides",
            "app.output_invoice_collection_reminders",
            "app.output_invoice_collection_red_relations",
            "app.output_invoice_receipts",
            "app.output_invoice_receipt_events",
        ),
        relation_tables=("app.workbench_pair_relations",),
        canonical_expected_set=(
            "active output invoices, bank facts, lifecycle overrides, receipts, "
            "and active relation membership read in one database snapshot"
        ),
        key_display_fields=("invoice_id", "invoice_no", "invoice_date", "total_with_tax", "collection_status", "relation members"),
        external_source_boundary="invoice and bank completeness before App import",
    ),
    "turnover_ledger": PageAuditContract(
        domain_key="turnover_ledger",
        label="外部往来款管理",
        source_tables=(
            "app.bank_transactions",
            "app.bank_transaction_categories",
            "app.workbench_pair_relations",
            "app.turnover_relations",
            "app.turnover_ledger_extras",
            "app.app_settings",
        ),
        canonical_expected_set=(
            "eligible bank facts, effective categories, active workbench pair relations, "
            "retained manual turnover relations, settings, and ledger extras read in one database snapshot"
        ),
        key_display_fields=(
            "family",
            "counterparty_name",
            "amount breakdown",
            "pending direction",
            "bank_row_ids",
            "interest fields",
        ),
        external_source_boundary="bank statement completeness before App import",
    ),
    "batch_accounting": PageAuditContract(
        domain_key="batch_accounting",
        label="批量账务",
        source_tables=(
            "app.bank_transactions",
            "app.oa_applications",
            "app.invoices",
            "app.workbench_pair_relations",
        ),
        relation_tables=("app.workbench_pair_relations",),
        canonical_expected_set=(
            "active relation_mode=batch_accounting relations with source=batch_accounting "
            "and aligned unique typed members resolving to canonical bank/OA/invoice facts"
        ),
        key_display_fields=("case_id", "relation_mode", "row_ids", "row_types", "special_metadata.source"),
        external_source_boundary="OA and bank source completeness before App registration",
    ),
    "bank_flow_rule_batches": PageAuditContract(
        domain_key="bank_flow_rule_batches",
        label="流水规则批量处理",
        source_tables=(
            "app.bank_transactions",
            "app.bank_transaction_category_confirmations",
            "app.bank_transaction_categories",
            "app.app_settings",
            "app.workbench_pair_relations",
            "app.bank_flow_rule_batches",
            "app.bank_flow_rule_batch_events",
        ),
        relation_tables=("app.workbench_pair_relations",),
        scope_types=(),
        event_types=(),
        canonical_expected_set=(
            "live candidates from active bank facts, effective categories, current rule settings, "
            "and active relation occupancy plus persisted submitted/withdrawn history"
        ),
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
        relation_tables=(
            "app.workbench_pair_relations",
            "app.oa_pending_payment_bank_relations",
        ),
        canonical_expected_set="completed App OA records plus externally admitted in-progress OA records already registered in App",
        key_display_fields=("oa_id", "workflow_status", "applicant", "project_name", "amount", "relation members", "payment_status"),
        external_source_boundary="OA source completeness and t_payment_simple admission completeness",
    ),
    "bank_details": PageAuditContract(
        domain_key="bank_details",
        label="银行明细",
        source_tables=(
            "app.bank_transactions",
            "app.bank_transaction_categories",
            "app.workbench_pair_relations",
        ),
        relation_tables=("app.workbench_pair_relations",),
        canonical_expected_set=(
            "active canonical bank transactions, current effective categories, deterministic "
            "account identities, and active relation membership read in one database snapshot"
        ),
        key_display_fields=(
            "transaction_id",
            "trade_date",
            "direction",
            "amount",
            "counterparty_name",
            "account balance",
        ),
        external_source_boundary="bank statement completeness before App import",
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
        (_turnover_ledger_direct_canonical_issues,)
        if contract.domain_key == "turnover_ledger"
        else (_oa_pending_payment_direct_canonical_issues,)
        if contract.domain_key == "oa_pending_payments"
        else (_bank_details_direct_canonical_issues,)
        if contract.domain_key in {
            "bank_details",
            "pending_invoices",
            "input_invoice_usage",
            "output_invoice_collection",
        }
        else (
            _canonical_expected_set_issues,
            _key_display_field_issues,
            _consumer_relation_edge_equality_issues,
        )
    )
    for check in checks:
        issues.extend(check(connection, contract, tenant_id, limit + 1))

    evaluation = evaluate_audit_issues(issues, sample_limit=limit)
    summary.update(evaluation.summary)
    return {
        "mode": "page-business-canonical-read-audit",
        "tenant_id": tenant_id,
        "domain_key": contract.domain_key,
        "label": contract.label,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": summary,
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": list(contract.source_tables),
            "read_model_tables": [],
            "relation_tables": list(contract.relation_tables),
            "scope_types": list(contract.scope_types),
            "event_types": list(contract.event_types),
            "canonical_expected_set": contract.canonical_expected_set,
            "key_display_fields": list(contract.key_display_fields),
            "relation_edge_equality": (
                "page reads canonical workbench_pair_relations directly in the same database snapshot"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": contract.external_source_boundary,
            "proof_checks": [
                *(
                    [
                        "single_repeatable_read_snapshot",
                        "canonical_relation_member_existence",
                        "canonical_relation_identity_uniqueness",
                        *(
                            ["oa_pending_payment_relation_visibility"]
                            if contract.domain_key == "oa_pending_payments"
                            else []
                        ),
                        *(
                            ["manual_turnover_relation_member_existence"]
                            if contract.domain_key == "turnover_ledger"
                            else []
                        ),
                    ]
                    if contract.domain_key in {
                        "turnover_ledger",
                        "bank_details",
                        "pending_invoices",
                        "oa_pending_payments",
                        "input_invoice_usage",
                        "output_invoice_collection",
                    }
                    else [
                        "canonical_expected_set_equality",
                        "key_display_field_recalculation",
                        *(["consumer_relation_edge_equality"] if contract.consumer_relation_contract else []),
                    ]
                ),
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "The page reads App-internal canonical facts and active relation membership "
                "directly from one repeatable-read database snapshot; no read model or refresh queue is in the path."
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
        "active_relation_count": _int(row.get("active_relation_count")),
        "linked_relation_group_count": _int(row.get("linked_relation_group_count")),
    }


def _summary_sql(contract: PageAuditContract, *, tenant_id: str) -> tuple[str, tuple[Any, ...]]:
    domain = contract.domain_key
    if domain == "oa_pending_payments":
        return (
            """
            /* check: direct_canonical_summary */
            select
                (
                    select count(*)
                    from app.oa_applications
                    where status <> 'deleted'
                )::integer as source_fact_count,
                (
                    select count(*)
                    from app.workbench_pair_relations
                    where status = 'active'
                      and row_types && array['oa']::text[]
                )::integer as active_relation_count,
                (
                    select count(*)
                    from app.workbench_pair_relations
                    where status = 'active'
                      and row_types && array['oa']::text[]
                )::integer as linked_relation_group_count
            """,
            (),
        )
    if domain in {"input_invoice_usage", "output_invoice_collection"}:
        direction = "input" if domain == "input_invoice_usage" else "output"
        localized_prefix = "进项" if domain == "input_invoice_usage" else "销项"
        return (
            f"""
            /* check: direct_canonical_summary */
            select
                (
                    select count(*) from app.invoices
                    where status <> 'deleted'
                      and (
                        invoice_type in ('{direction}', '{direction}_invoice')
                        or invoice_type like '{localized_prefix}%%'
                      )
                )::integer as source_fact_count,
                (
                    select count(*) from app.workbench_pair_relations
                    where status = 'active'
                      and row_types && array['invoice', 'input_invoice', 'output_invoice']::text[]
                )::integer as active_relation_count,
                (
                    select count(*) from app.workbench_pair_relations
                    where status = 'active'
                      and row_types && array['invoice', 'input_invoice', 'output_invoice']::text[]
                )::integer as linked_relation_group_count
            """,
            (),
        )
    if domain in {"turnover_ledger", "bank_details", "pending_invoices"}:
        return (
            """
            /* check: direct_canonical_summary */
            select
                (
                    select count(*) from app.bank_transactions
                    where coalesce(nullif(status, ''), 'active') <> 'deleted'
                )::integer as source_fact_count,
                (
                    select count(*) from app.workbench_pair_relations
                    where status = 'active'
                      and exists (
                          select 1
                          from unnest(row_types) member(row_type)
                          where member.row_type in ('bank', 'bank_transaction')
                      )
                )::integer as active_relation_count,
                (
                    select count(*) from app.workbench_pair_relations
                    where status = 'active'
                      and exists (
                          select 1
                          from unnest(row_types) member(row_type)
                          where member.row_type in ('bank', 'bank_transaction')
                      )
                )::integer as linked_relation_group_count
            """,
            (),
        )
    if domain == "batch_accounting":
        source_sql = "select count(*) from app.workbench_pair_relations where status = 'active' and relation_mode = 'batch_accounting'"
        relation_sql = source_sql
    elif domain == "bank_flow_rule_batches":
        source_sql = "select count(*) from app.bank_flow_rule_batches where status <> 'deleted'"
        relation_sql = "select count(*) from app.workbench_pair_relations where status = 'active' and relation_mode = 'bank_flow_rule_batch'"
    else:
        raise ValueError(f"Unsupported page audit domain: {domain}")
    return f"""
    /* check: direct_canonical_summary */
    select
        ({source_sql})::integer as source_fact_count,
        ({relation_sql})::integer as active_relation_count,
        ({relation_sql})::integer as linked_relation_group_count
    """, ()


def _turnover_ledger_direct_canonical_issues(
    connection: Any,
    _contract: PageAuditContract,
    _tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    queries = (
        (
            """
            /* check: canonical_relation_member_shape */
            select case_id as subject_id, to_char(month_scope, 'YYYY-MM') as scope_key,
                   cardinality(row_ids) as row_id_count, cardinality(row_types) as row_type_count
            from app.workbench_pair_relations
            where status = 'active'
              and cardinality(row_ids) <> cardinality(row_types)
            order by case_id
            limit %s
            """,
            "turnover_ledger_canonical_relation_member_shape_invalid",
            "统一配对关系的 row_ids 与 row_types 数量不一致。",
        ),
        (
            """
            /* check: canonical_relation_bank_member_exists */
            with members as (
                select relation.case_id, relation.month_scope,
                       member.row_id, relation.row_types[member.ordinality] as row_type
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
            )
            select member.case_id as subject_id, to_char(member.month_scope, 'YYYY-MM') as scope_key,
                   member.row_id, member.row_type
            from members member
            left join app.bank_transactions source
              on source.id::text = member.row_id
              or source.legacy_mongo_id = member.row_id
            where member.row_type in ('bank', 'bank_transaction')
              and source.id is null
            order by member.case_id, member.row_id
            limit %s
            """,
            "turnover_ledger_canonical_relation_bank_member_missing",
            "统一配对关系引用了不存在的银行流水。",
        ),
        (
            """
            /* check: canonical_relation_bank_member_unique */
            with members as (
                select relation.case_id, relation.month_scope, member.row_id
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
                  and relation.row_types[member.ordinality] in ('bank', 'bank_transaction')
            )
            select member.row_id as subject_id, min(to_char(member.month_scope, 'YYYY-MM')) as scope_key,
                   array_agg(distinct member.case_id order by member.case_id) as active_case_ids
            from members member
            group by member.row_id
            having count(distinct member.case_id) > 1
            order by member.row_id
            limit %s
            """,
            "turnover_ledger_canonical_relation_bank_member_duplicated",
            "同一银行流水同时存在于多个有效统一配对关系。",
        ),
        (
            """
            /* check: manual_turnover_relation_bank_member_exists */
            with relation_members as (
                select relation.relation_id, relation.scope_month, member.row_id
                from app.turnover_relations relation
                join lateral jsonb_array_elements_text(
                    case
                        when jsonb_typeof(
                            relation.raw_payload->'normalized_payload'->'bank_row_ids'
                        ) = 'array'
                        then relation.raw_payload->'normalized_payload'->'bank_row_ids'
                        else '[]'::jsonb
                    end
                ) member(row_id) on true
                where relation.status <> 'deleted'
            )
            select member.relation_id as subject_id, to_char(member.scope_month, 'YYYY-MM') as scope_key,
                   member.row_id
            from relation_members member
            left join app.bank_transactions source
              on source.id::text = member.row_id
              or source.legacy_mongo_id = member.row_id
            where source.id is null
            order by member.relation_id, member.row_id
            limit %s
            """,
            "turnover_ledger_manual_relation_bank_member_missing",
            "外部往来款手工关系引用了不存在的银行流水。",
        ),
    )
    issues: list[AuditIssue] = []
    for sql, code, message in queries:
        issues.extend(
            _proof_query_issues(
                connection,
                sql=sql,
                params=(limit,),
                code=code,
                message=message,
            )
        )
    return issues


def _bank_details_direct_canonical_issues(
    connection: Any,
    contract: PageAuditContract,
    _tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    code_prefix = contract.domain_key
    queries = (
        (
            """
            /* check: canonical_relation_member_shape */
            select case_id as subject_id, to_char(month_scope, 'YYYY-MM') as scope_key,
                   cardinality(row_ids) as row_id_count, cardinality(row_types) as row_type_count
            from app.workbench_pair_relations
            where status = 'active'
              and cardinality(row_ids) <> cardinality(row_types)
            order by case_id
            limit %s
            """,
            f"{code_prefix}_canonical_relation_member_shape_invalid",
            "统一配对关系的 row_ids 与 row_types 数量不一致。",
        ),
        (
            """
            /* check: canonical_relation_bank_member_exists */
            with members as (
                select relation.case_id, relation.month_scope,
                       member.row_id, relation.row_types[member.ordinality] as row_type
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
            )
            select member.case_id as subject_id, to_char(member.month_scope, 'YYYY-MM') as scope_key,
                   member.row_id, member.row_type
            from members member
            left join app.bank_transactions source
              on source.id::text = member.row_id
              or source.legacy_mongo_id = member.row_id
            where member.row_type in ('bank', 'bank_transaction')
              and source.id is null
            order by member.case_id, member.row_id
            limit %s
            """,
            f"{code_prefix}_canonical_relation_bank_member_missing",
            "统一配对关系引用了不存在的银行流水。",
        ),
        (
            """
            /* check: canonical_relation_bank_member_unique */
            with members as (
                select relation.case_id, relation.month_scope, member.row_id
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
                  and relation.row_types[member.ordinality] in ('bank', 'bank_transaction')
            )
            select member.row_id as subject_id, min(to_char(member.month_scope, 'YYYY-MM')) as scope_key,
                   array_agg(distinct member.case_id order by member.case_id) as active_case_ids
            from members member
            group by member.row_id
            having count(distinct member.case_id) > 1
            order by member.row_id
            limit %s
            """,
            f"{code_prefix}_canonical_relation_bank_member_duplicated",
            "同一银行流水同时存在于多个有效统一配对关系。",
        ),
        (
            """
            /* check: canonical_relation_oa_member_exists */
            with members as (
                select relation.case_id, relation.month_scope, member.row_id
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
                  and relation.row_types[member.ordinality] = 'oa'
            )
            select member.case_id as subject_id,
                   to_char(member.month_scope, 'YYYY-MM') as scope_key,
                   member.row_id
            from members member
            left join app.oa_applications source on source.row_id = member.row_id
            where source.row_id is null
            order by member.case_id, member.row_id
            limit %s
            """,
            f"{code_prefix}_canonical_relation_oa_member_missing",
            "统一配对关系引用了不存在的 OA 记录。",
        ),
        (
            """
            /* check: canonical_relation_invoice_member_exists */
            with members as (
                select relation.case_id, relation.month_scope,
                       member.row_id, relation.row_types[member.ordinality] as row_type
                from app.workbench_pair_relations relation
                join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
                where relation.status = 'active'
            )
            select member.case_id as subject_id,
                   to_char(member.month_scope, 'YYYY-MM') as scope_key,
                   member.row_id
            from members member
            left join app.invoices source
              on source.id::text = member.row_id
              or source.legacy_mongo_id = member.row_id
            where member.row_type in ('invoice', 'input_invoice', 'output_invoice')
              and source.id is null
            order by member.case_id, member.row_id
            limit %s
            """,
            f"{code_prefix}_canonical_relation_invoice_member_missing",
            "统一配对关系引用了不存在的发票。",
        ),
    )
    issues: list[AuditIssue] = []
    for sql, code, message in queries:
        issues.extend(
            _proof_query_issues(
                connection,
                sql=sql,
                params=(limit,),
                code=code,
                message=message,
            )
        )
    return issues


def _oa_pending_payment_direct_canonical_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    issues = _bank_details_direct_canonical_issues(connection, contract, tenant_id, limit)
    issues.extend(
        AuditIssue(
            severity="error",
            code="oa_pending_payments_active_outflow_relation_not_visible",
            message="有效 OA—支出流水关系没有被 OA 待付款 canonical consumer 正确读取。",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={
                key: _jsonable(value)
                for key, value in row.items()
                if key not in {"subject_id", "scope_key"}
            },
        )
        for row in list_oa_pending_payment_relation_visibility_gaps(
            connection,
            tenant_id=tenant_id,
            limit=limit,
        )
    )
    return issues


def _canonical_expected_set_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    if contract.domain_key == "batch_accounting":
        return _proof_query_issues(
            connection,
            sql="""
                /* check: canonical_expected_set */
                select relation.case_id as subject_id,
                       to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                       relation.relation_mode,
                       relation.special_metadata->>'source' as metadata_source
                from app.workbench_pair_relations relation
                where relation.status = 'active'
                  and (
                      relation.relation_mode = 'batch_accounting'
                      or relation.special_metadata->>'source' = 'batch_accounting'
                  )
                  and (
                      relation.relation_mode <> 'batch_accounting'
                      or relation.special_metadata->>'source' is distinct from 'batch_accounting'
                  )
                order by relation.case_id
                limit %s
            """,
            params=(limit,),
            code="batch_accounting_relation_owner_mismatch",
            message="批量账务 active relation 的 relation_mode 与 source owner 不一致。",
        )
    if contract.domain_key == "bank_flow_rule_batches":
        return _proof_query_issues(
            connection,
            sql="""
                /* check: canonical_expected_set */
                with current_settings as materialized (
                    select settings_payload
                    from app.app_settings
                    where settings_key = 'app_settings'
                    limit 1
                ),
                effective_bank_facts as materialized (
                    select
                        coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
                        to_char(coalesce(bank.txn_date, bank.txn_month), 'YYYY-MM') as scope_key,
                        bank.txn_direction,
                        bank.amount,
                        coalesce(
                            confirmed.category_code,
                            manual.category,
                            ''
                        ) as category_code
                    from app.bank_transactions bank
                    left join lateral (
                        select confirmation.category_code
                        from app.bank_transaction_category_confirmations confirmation
                        where confirmation.tenant_id = 'default'
                          and confirmation.status = 'active'
                          and (
                              confirmation.bank_transaction_id = bank.id
                              or confirmation.legacy_transaction_id in (
                                  coalesce(bank.legacy_mongo_id, bank.id::text),
                                  bank.id::text
                              )
                          )
                        order by confirmation.confirmed_at desc, confirmation.id desc
                        limit 1
                    ) confirmed on true
                    left join lateral (
                        select category.category
                        from app.bank_transaction_categories category
                        where category.status = 'active'
                          and (
                              category.bank_transaction_id = bank.id
                              or category.legacy_transaction_id in (
                                  coalesce(bank.legacy_mongo_id, bank.id::text),
                                  bank.id::text
                              )
                          )
                        order by category.updated_at desc, category.id desc
                        limit 1
                    ) manual on true
                    where bank.status <> 'deleted'
                ),
                occupied_members as materialized (
                    select distinct member.row_id
                    from app.workbench_pair_relations relation
                    cross join lateral unnest(relation.row_ids) member(row_id)
                    where relation.status = 'active'
                ),
                persisted_formal_facts as materialized (
                    select batch.batch_id
                    from app.bank_flow_rule_batches batch
                    where batch.status in ('submitted', 'withdrawn', 'stale')
                )
                select fact.row_id as subject_id,
                       fact.scope_key,
                       'invalid_live_candidate_source_fact' as mismatch_kind,
                       fact.category_code,
                       fact.txn_direction,
                       fact.amount::text
                from effective_bank_facts fact
                cross join current_settings settings
                left join occupied_members occupied on occupied.row_id = fact.row_id
                where nullif(fact.row_id, '') is null
                   or nullif(fact.scope_key, '') is null
                   or nullif(fact.category_code, '') is null
                   or fact.amount is null
                   or settings.settings_payload is null
                   or exists (
                       select 1
                       from persisted_formal_facts formal
                       where formal.batch_id is null
                   )
                order by fact.scope_key, fact.row_id
                limit %s
            """,
            params=(limit,),
            code="bank_flow_rule_batches_canonical_expected_set_mismatch",
            message="流水规则 live candidate expected set 与 canonical facts 不一致。",
        )
    return []


def _key_display_field_issues(
    connection: Any,
    contract: PageAuditContract,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    domain = contract.domain_key
    if domain == "batch_accounting":
        queries = [
            (
                """
                /* check: key_display_fields */
                with batch_relations as (
                    select relation.*
                    from app.workbench_pair_relations relation
                    where relation.status = 'active'
                      and relation.relation_mode = 'batch_accounting'
                ),
                invalid_members as (
                    select relation.case_id,
                           array_agg(member.row_id order by member.ordinality) filter (
                               where nullif(member.row_id, '') is null
                                  or lower(coalesce(relation.row_types[member.ordinality], ''))
                                     not in (
                                         'bank', 'bank_transaction', 'oa',
                                         'invoice', 'input_invoice', 'output_invoice'
                                     )
                                  or (
                                      lower(coalesce(relation.row_types[member.ordinality], ''))
                                          in ('bank', 'bank_transaction')
                                      and bank.id is null
                                  )
                                  or (
                                      lower(coalesce(relation.row_types[member.ordinality], '')) = 'oa'
                                      and oa.id is null
                                  )
                                  or (
                                      lower(coalesce(relation.row_types[member.ordinality], ''))
                                          in ('invoice', 'input_invoice', 'output_invoice')
                                      and invoice.id is null
                                  )
                           ) as invalid_member_ids
                    from batch_relations relation
                    join lateral unnest(relation.row_ids) with ordinality
                      as member(row_id, ordinality) on true
                    left join app.bank_transactions bank
                      on coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
                     and bank.status <> 'deleted'
                    left join app.oa_applications oa
                      on oa.row_id = member.row_id
                     and oa.status <> 'deleted'
                    left join app.invoices invoice
                      on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.row_id
                     and invoice.status <> 'deleted'
                    group by relation.case_id
                )
                select relation.case_id as subject_id,
                       to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                       relation.relation_mode,
                       relation.row_ids,
                       relation.row_types,
                       relation.special_metadata,
                       invalid.invalid_member_ids
                from batch_relations relation
                left join invalid_members invalid on invalid.case_id = relation.case_id
                where cardinality(relation.row_ids) <> cardinality(relation.row_types)
                   or cardinality(relation.row_ids) <> (
                       select count(distinct member.row_id)
                       from unnest(relation.row_ids) member(row_id)
                   )
                   or (
                       select count(*)
                       from unnest(relation.row_types) member(row_type)
                       where lower(member.row_type) in ('bank', 'bank_transaction')
                   ) <> 1
                   or not exists (
                       select 1
                       from unnest(relation.row_types) member(row_type)
                       where lower(member.row_type) = 'oa'
                   )
                   or invalid.invalid_member_ids is not null
                order by relation.case_id
                limit %s
                """,
                (limit,),
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
