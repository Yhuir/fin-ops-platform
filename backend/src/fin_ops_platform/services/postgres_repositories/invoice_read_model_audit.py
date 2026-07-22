from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation_audit import (
    workbench_relation_edge_equality_issues,
)


@dataclass(frozen=True)
class InvoiceReadModelAuditContract:
    direction: str
    localized_prefix: str
    title: str
    read_model_key: str
    rows_table: str
    scopes_table: str
    member_invoice_id_sql: str
    active_count_key: str
    active_total_key: str
    scope_count_key: str
    scope_row_count_issue_code: str
    source_version_issue_code: str
    missing_member_issue_code: str
    orphan_member_issue_code: str
    duplicate_member_issue_code: str
    amount_mismatch_issue_code: str
    relation_split_issue_code: str
    invalid_projection_status_issue_code: str
    invalid_relation_row_status_issue_code: str
    invalid_relation_group_status_issue_code: str
    relation_group_ids_column: str


INPUT_INVOICE_AUDIT_CONTRACT = InvoiceReadModelAuditContract(
    direction="input",
    localized_prefix="进项",
    title="Input invoice usage",
    read_model_key="input_invoice_usage",
    rows_table="read_model.input_invoice_usage_rows",
    scopes_table="read_model.input_invoice_usage_scopes",
    member_invoice_id_sql="coalesce(nullif(member.value->>'invoiceId', ''), row.invoice_id)",
    active_count_key="active_input_invoice_count",
    active_total_key="active_input_invoice_total_with_tax",
    scope_count_key="input_invoice_usage_scope_count",
    scope_row_count_issue_code="input_scope_row_count_mismatch",
    source_version_issue_code="input_usage_relation_source_versions_mismatch",
    missing_member_issue_code="missing_input_invoice_usage_member",
    orphan_member_issue_code="orphan_input_invoice_usage_member",
    duplicate_member_issue_code="duplicate_input_invoice_usage_member",
    amount_mismatch_issue_code="input_invoice_usage_amount_mismatch",
    relation_split_issue_code="active_relation_members_split_across_input_usage_rows",
    invalid_projection_status_issue_code="invalid_relation_status_in_input_usage",
    invalid_relation_row_status_issue_code="invalid_workbench_relation_row_status_for_input_invoice",
    invalid_relation_group_status_issue_code="invalid_workbench_relation_group_status_for_input_invoice",
    relation_group_ids_column="input_invoice_ids",
)

OUTPUT_INVOICE_AUDIT_CONTRACT = InvoiceReadModelAuditContract(
    direction="output",
    localized_prefix="销项",
    title="Output invoice collection",
    read_model_key="output_invoice_collection",
    rows_table="read_model.output_invoice_collection_rows",
    scopes_table="read_model.output_invoice_collection_scopes",
    member_invoice_id_sql=(
        "coalesce(nullif(member.value->>'relatedInvoiceId', ''), "
        "nullif(member.value->>'invoiceId', ''), row.invoice_id)"
    ),
    active_count_key="active_output_invoice_count",
    active_total_key="active_output_invoice_total_with_tax",
    scope_count_key="output_invoice_collection_scope_count",
    scope_row_count_issue_code="output_scope_row_count_mismatch",
    source_version_issue_code="output_collection_relation_source_versions_mismatch",
    missing_member_issue_code="missing_output_invoice_collection_member",
    orphan_member_issue_code="orphan_output_invoice_collection_member",
    duplicate_member_issue_code="duplicate_output_invoice_collection_member",
    amount_mismatch_issue_code="output_invoice_collection_amount_mismatch",
    relation_split_issue_code="active_relation_members_split_across_output_collection_rows",
    invalid_projection_status_issue_code="invalid_relation_status_in_output_collection",
    invalid_relation_row_status_issue_code="invalid_workbench_relation_row_status_for_output_invoice",
    invalid_relation_group_status_issue_code="invalid_workbench_relation_group_status_for_output_invoice",
    relation_group_ids_column="output_invoice_ids",
)


def invoice_predicate(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
    i.status <> 'deleted'
    and (
        i.invoice_type = '{contract.direction}'
        or i.invoice_type = '{contract.direction}_invoice'
        or i.invoice_type like '{contract.localized_prefix}%%'
    )
"""


def _active_invoices_cte(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
active_invoices as (
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
    where {invoice_predicate(contract)}
)
"""


def _invoice_lookup_cte(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
{_active_invoices_cte(contract)},
invoice_relation_lookup as (
    select invoice_id, invoice_id as relation_row_id, scope_key from active_invoices
    union
    select invoice_id, source_row_id as relation_row_id, scope_key
    from active_invoices
    cross join lateral unnest(source_workbench_row_ids) as source_row_id
    where nullif(source_row_id, '') is not null
)
"""


def _read_model_members_cte(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
read_model_invoice_members as (
    select distinct
        row.scope_key,
        row.row_id,
        row.invoice_id as primary_invoice_id,
        {contract.member_invoice_id_sql} as invoice_id,
        row.total_with_tax as row_total_with_tax,
        row.payload,
        row.generated_at::text as generated_at
    from {contract.rows_table} row
    join lateral jsonb_array_elements(
        case
            when jsonb_typeof(row.payload->'invoiceRelations'->'summaries') = 'array'
             and jsonb_array_length(row.payload->'invoiceRelations'->'summaries') > 0
            then row.payload->'invoiceRelations'->'summaries'
            else jsonb_build_array(jsonb_build_object('invoiceId', row.invoice_id, 'totalWithTax', row.total_with_tax))
        end
    ) as member(value) on true
    where row.cache_status = 'fresh'
)
"""


def _active_relation_members_cte(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
{_invoice_lookup_cte(contract)},
active_relation_invoice_members as (
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
        select row_item.row_id, relation.row_types[row_item.ordinality] as row_type
        from unnest(relation.row_ids) with ordinality as row_item(row_id, ordinality)
    ) member on true
    join invoice_relation_lookup lookup on lookup.relation_row_id = member.row_id
    where relation.status = 'active'
)
"""


def _summary_sql(contract: InvoiceReadModelAuditContract) -> str:
    return f"""
/* check: summary */
with
{_active_invoices_cte(contract)},
{_read_model_members_cte(contract)}
select
    (select count(*)::integer from active_invoices) as {contract.active_count_key},
    (select coalesce(sum(total_with_tax), 0)::numeric from active_invoices) as {contract.active_total_key},
    (select count(distinct invoice_id)::integer from read_model_invoice_members) as read_model_invoice_member_count,
    (select count(*)::integer from {contract.rows_table} where cache_status = 'fresh') as read_model_row_count,
    (select count(*)::integer from {contract.scopes_table}) as {contract.scope_count_key},
    (select count(*)::integer from read_model.workbench_relation_scopes where tenant_id = %s) as workbench_relation_scope_count,
    (select count(*)::integer from app.workbench_pair_relations where status = 'active') as active_workbench_pair_relation_count,
    (select count(*)::integer from read_model.workbench_relation_groups where tenant_id = %s and relation_status = 'linked')
        as linked_workbench_relation_group_count
"""


def audit_invoice_read_model(
    connection: Any,
    *,
    contract: InvoiceReadModelAuditContract,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    limit = max(int(example_limit or 50), 1)
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_invoice_read_model_snapshot(
            snapshot.connection,
            contract=contract,
            tenant_id=normalized_tenant_id,
            limit=limit,
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_invoice_read_model_snapshot(
    connection: Any,
    *,
    contract: InvoiceReadModelAuditContract,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    summary = _fetch_summary(connection, contract=contract, tenant_id=tenant_id)
    issues: list[AuditIssue] = []
    checks = (
        _noncanonical_invoice_type_issues,
        _dirty_scope_issues,
        _outbox_backlog_issues,
        _missing_scope_issues,
        _scope_row_count_mismatch_issues,
        _missing_workbench_relation_scope_issues,
        _source_version_mismatch_issues,
        _missing_read_model_member_issues,
        _orphan_read_model_member_issues,
        _duplicate_invoice_member_issues,
        _amount_mismatch_issues,
        _relation_edge_equality_issues,
        _consumer_relation_edge_equality_issues,
        _relation_member_split_row_issues,
        _invalid_relation_status_issues,
    )
    for check in checks:
        issues.extend(check(connection, contract=contract, tenant_id=tenant_id, limit=limit + 1))

    evaluation = evaluate_audit_issues(issues, sample_limit=limit)
    summary.update(evaluation.summary)
    return {
        "mode": "dry-run",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": summary,
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": [
                "app.invoices",
                "app.workbench_pair_relations",
                contract.rows_table,
                contract.scopes_table,
                "read_model.workbench_relation_rows",
                "read_model.workbench_relation_groups",
                "read_model.workbench_relation_scopes",
                "job.read_model_dirty_scopes",
                "job.outbox_events",
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "canonical_expected_set": (
                f"all active canonical {contract.direction} invoices, including every collapsed invoice member"
            ),
            "key_display_fields": [
                "invoice_id",
                "scope_key",
                "invoice_type",
                "invoice_no",
                "total_with_tax",
                "relation members",
            ],
            "relation_edge_equality": (
                "canonical == relation_groups == relation_rows == invoice page consumer summaries"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": "invoice/OA source completeness before App import",
            "proof_checks": [
                "canonical_expected_set_equality",
                "missing_or_orphan_identity",
                "key_display_field_recalculation",
                "scope_count_and_source_version_equality",
                "bidirectional_relation_edge_equality",
                "consumer_relation_edge_equality",
                "durable_queue_and_freshness_gate",
            ],
            "scope_types": [contract.read_model_key, "workbench_relation", "invoice_lifecycle"],
            "event_types": [
                f"{contract.read_model_key}.read_model.refresh",
                "workbench_relation.read_model.refresh",
                "invoice_lifecycle.read_model.refresh",
            ],
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _relation_edge_equality_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    return workbench_relation_edge_equality_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit,
        code_prefix=contract.read_model_key,
        label=contract.title,
    )


def _consumer_relation_edge_equality_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: consumer_relation_edge_equality */
        with
        {_invoice_lookup_cte(contract)},
        relevant_groups as (
            select group_row.*
            from read_model.workbench_relation_groups group_row
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
              and exists (
                  select 1
                  from unnest(group_row.{contract.relation_group_ids_column}) member(row_id)
                  join invoice_relation_lookup lookup
                    on lookup.relation_row_id = member.row_id
              )
        ),
        expected_edge_rows as (
            select group_row.group_id as case_id, group_row.scope_key,
                   member.row_id, 'oa'::text as row_type
            from relevant_groups group_row
            join lateral unnest(group_row.oa_row_ids) member(row_id) on true
            union all
            select group_row.group_id, group_row.scope_key,
                   member.row_id, 'bank_transaction'::text
            from relevant_groups group_row
            join lateral unnest(group_row.bank_transaction_ids) member(row_id) on true
            union all
            select group_row.group_id, group_row.scope_key,
                   lookup.invoice_id, '{contract.direction}_invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.{contract.relation_group_ids_column}) member(row_id) on true
            join invoice_relation_lookup lookup
              on lookup.relation_row_id = member.row_id
        ),
        expected_edges as (
            select case_id, row_id, row_type, min(scope_key) as scope_key
            from expected_edge_rows
            where nullif(case_id, '') is not null
              and nullif(row_id, '') is not null
            group by case_id, row_id, row_type
        ),
        consumer_edge_rows as (
            select oa_summary.value->>'relationCaseId' as case_id, row.scope_key,
                   coalesce(nullif(oa_summary.value->>'oaId', ''), oa_summary.value->>'id') as row_id,
                   'oa'::text as row_type
            from {contract.rows_table} row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'oa'->'summaries') = 'array'
                     then row.payload->'oa'->'summaries' else '[]'::jsonb end
            ) oa_summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(oa_summary.value->>'relationStatus', '')) = 'linked'
            union all
            select bank_summary.value->>'relationCaseId', row.scope_key,
                   bank_summary.value->>'bankTransactionId', 'bank_transaction'::text
            from {contract.rows_table} row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'bankTransactions'->'summaries') = 'array'
                     then row.payload->'bankTransactions'->'summaries' else '[]'::jsonb end
            ) bank_summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(bank_summary.value->>'relationStatus', '')) = 'linked'
            union all
            select invoice_summary.value->>'relationCaseId', row.scope_key,
                   invoice_summary.value->>'invoiceId', '{contract.direction}_invoice'::text
            from {contract.rows_table} row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'invoiceRelations'->'summaries') = 'array'
                     then row.payload->'invoiceRelations'->'summaries' else '[]'::jsonb end
            ) invoice_summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(invoice_summary.value->>'relationStatus', '')) = 'linked'
        ),
        consumer_edges as (
            select case_id, row_id, row_type, min(scope_key) as scope_key
            from consumer_edge_rows
            where nullif(case_id, '') is not null
              and nullif(row_id, '') is not null
            group by case_id, row_id, row_type
        ),
        mismatches as (
            select 'shared_edge_missing_consumer' as mismatch_kind, expected.*
            from expected_edges expected
            where not exists (
                select 1 from consumer_edges consumer
                where consumer.case_id = expected.case_id
                  and consumer.row_id = expected.row_id
                  and consumer.row_type = expected.row_type
            )
            union all
            select 'consumer_edge_not_shared', consumer.*
            from consumer_edges consumer
            where not exists (
                select 1 from expected_edges expected
                where expected.case_id = consumer.case_id
                  and expected.row_id = consumer.row_id
                  and expected.row_type = consumer.row_type
            )
        )
        select mismatch_kind, case_id as subject_id, scope_key, row_id, row_type
        from mismatches
        order by mismatch_kind, subject_id, row_type, row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"{contract.read_model_key}_consumer_relation_edge_mismatch",
            message=f"{contract.title} consumer relation summaries do not equal the shared linked relation edges.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "mismatch_kind", "row_id", "row_type"),
        )
        for row in rows
    ]


def _fetch_summary(
    connection: Any,
    *,
    contract: InvoiceReadModelAuditContract,
    tenant_id: str,
) -> dict[str, Any]:
    row = connection.fetch_one(_summary_sql(contract), (tenant_id, tenant_id)) or {}
    return {
        contract.active_count_key: _int(row.get(contract.active_count_key)),
        contract.active_total_key: _text(row.get(contract.active_total_key)) or "0",
        "read_model_invoice_member_count": _int(row.get("read_model_invoice_member_count")),
        "read_model_row_count": _int(row.get("read_model_row_count")),
        contract.scope_count_key: _int(row.get(contract.scope_count_key)),
        "workbench_relation_scope_count": _int(row.get("workbench_relation_scope_count")),
        "active_workbench_pair_relation_count": _int(row.get("active_workbench_pair_relation_count")),
        "linked_workbench_relation_group_count": _int(row.get("linked_workbench_relation_group_count")),
    }


def _noncanonical_invoice_type_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: noncanonical_{contract.direction}_invoice_type */
        with {_active_invoices_cte(contract)}
        select invoice_id, scope_key, invoice_type, invoice_no
        from active_invoices
        where invoice_type <> '{contract.direction}'
        order by scope_key, invoice_id
        limit %s
        """,
        (limit,),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"noncanonical_{contract.direction}_invoice_type",
            message=f"{contract.direction.title()} invoice facts use a noncanonical invoice_type that the page service does not read directly.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_type", "invoice_no"),
        )
        for row in rows
    ]


def _dirty_scope_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: dirty_scope */
        select scope_type, scope_key, status, updated_at::text as updated_at, last_error
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type in ('{contract.read_model_key}', 'workbench_relation')
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
            message=f"{contract.title} cannot be guaranteed while a required read model scope is pending, processing, or failed.",
            subject_id=_text(row.get("scope_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in rows
    ]


def _outbox_backlog_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: outbox_backlog */
        select event_type, coalesce(scope_key, aggregate_id, '') as scope_key,
               status, updated_at::text as updated_at, last_error
        from job.outbox_events
        where tenant_id = %s
          and event_type in (
              '{contract.read_model_key}.read_model.refresh',
              'workbench_relation.read_model.refresh',
              'invoice_lifecycle.read_model.refresh'
          )
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
            message=f"{contract.title} cannot be guaranteed while a required refresh event is not drained.",
            subject_id=_text(row.get("event_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in rows
    ]


def _missing_scope_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: missing_{contract.read_model_key}_scope */
        with {_active_invoices_cte(contract)}
        select invoices.scope_key, count(*)::integer as invoice_count
        from active_invoices invoices
        left join {contract.scopes_table} scope
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
            code=f"missing_{contract.read_model_key}_scope",
            message=f"A month with {contract.direction} invoice facts has no {contract.read_model_key} scope row.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_count"),
        )
        for row in rows
    ]


def _scope_row_count_mismatch_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: {contract.scope_row_count_issue_code} */
        select
            scope.scope_key,
            scope.row_count::integer as scope_row_count,
            count(row.row_id)::integer as actual_row_count
        from {contract.scopes_table} scope
        left join {contract.rows_table} row
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
            code=contract.scope_row_count_issue_code,
            message=f"{contract.read_model_key} scope row_count does not match the stored row count.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "scope_row_count", "actual_row_count"),
        )
        for row in rows
    ]


def _missing_workbench_relation_scope_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: missing_workbench_relation_scope */
        with {_active_invoices_cte(contract)}
        select invoices.scope_key, count(*)::integer as invoice_count
        from active_invoices invoices
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
            message=f"A month with {contract.direction} invoice facts has no workbench_relation scope proof.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_count"),
        )
        for row in rows
    ]


def _source_version_mismatch_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: source_version_mismatch */
        with
        {_active_invoices_cte(contract)},
        invoice_scope_versions as (
            select
                invoice_scope.scope_key,
                coalesce(
                    invoice_scope.source_versions->'workbench_relation_source_versions',
                    '{{}}'::jsonb
                ) as embedded_relation_versions,
                coalesce(relation_scope.source_versions, '{{}}'::jsonb) as current_relation_versions
            from {contract.scopes_table} invoice_scope
            join read_model.workbench_relation_scopes relation_scope
              on relation_scope.tenant_id = %s
             and relation_scope.scope_key = invoice_scope.scope_key
            where invoice_scope.scope_key <> 'all'
              and exists (
                  select 1
                  from {contract.rows_table} row
                  where row.scope_key = invoice_scope.scope_key
              )
        )
        select
            invoice_versions.scope_key,
            invoice_versions.embedded_relation_versions,
            invoice_versions.current_relation_versions
        from invoice_scope_versions invoice_versions
        where invoice_versions.embedded_relation_versions <> invoice_versions.current_relation_versions
          and (
              invoice_versions.embedded_relation_versions - 'workbench_pair_relations_updated_at'
                  <> invoice_versions.current_relation_versions - 'workbench_pair_relations_updated_at'
              or exists (
                  select 1
                  from active_invoices active_invoice
                  join app.workbench_pair_relations changed_relation
                    on (
                        active_invoice.invoice_id = any(changed_relation.row_ids)
                        or active_invoice.postgres_invoice_id = any(changed_relation.row_ids)
                        or changed_relation.row_ids && active_invoice.source_workbench_row_ids
                    )
                  where active_invoice.scope_key = invoice_versions.scope_key
                    and changed_relation.updated_at > coalesce(
                        nullif(
                            invoice_versions.embedded_relation_versions
                                ->> 'workbench_pair_relations_updated_at',
                            ''
                        )::timestamptz,
                        '-infinity'::timestamptz
                    )
              )
          )
        order by invoice_versions.scope_key
        limit %s
        """,
        (tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=contract.source_version_issue_code,
            message=f"{contract.read_model_key} scope was built with stale workbench_relation source_versions.",
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "embedded_relation_versions", "current_relation_versions"),
        )
        for row in rows
    ]


def _missing_read_model_member_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: missing_read_model_member */
        with
        {_active_invoices_cte(contract)},
        {_read_model_members_cte(contract)}
        select
            invoices.invoice_id,
            invoices.invoice_no,
            invoices.invoice_type,
            invoices.scope_key,
            invoices.total_with_tax
        from active_invoices invoices
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
            code=contract.missing_member_issue_code,
            message=f"An active {contract.direction} invoice is missing from {contract.rows_table}.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_no", "invoice_type", "total_with_tax"),
        )
        for row in rows
    ]


def _orphan_read_model_member_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: orphan_read_model_member */
        with
        {_active_invoices_cte(contract)},
        {_read_model_members_cte(contract)}
        select
            member.invoice_id,
            member.scope_key,
            member.row_id,
            member.generated_at
        from read_model_invoice_members member
        left join active_invoices invoices
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
            code=contract.orphan_member_issue_code,
            message=f"A read model row references an invoice that is not an active {contract.direction} invoice fact.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_id", "generated_at"),
        )
        for row in rows
    ]


def _duplicate_invoice_member_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: duplicate_invoice_member */
        with {_read_model_members_cte(contract)}
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
            code=contract.duplicate_member_issue_code,
            message=f"The same {contract.direction} invoice appears in multiple read model rows within one scope.",
            subject_id=_text(row.get("invoice_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_count", "row_ids"),
        )
        for row in rows
    ]


def _amount_mismatch_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: amount_mismatch */
        with
        {_active_invoices_cte(contract)},
        {_read_model_members_cte(contract)},
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
            join active_invoices invoices
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
            code=contract.amount_mismatch_issue_code,
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


def _relation_member_split_row_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    rows = connection.fetch_all(
        f"""
        /* check: relation_member_split_row */
        with
        {_active_relation_members_cte(contract)},
        {_read_model_members_cte(contract)}
        select
            relation_member.case_id,
            read_member.scope_key,
            count(distinct read_member.row_id)::integer as row_count,
            array_agg(distinct read_member.row_id order by read_member.row_id) as row_ids,
            array_agg(distinct relation_member.invoice_id order by relation_member.invoice_id) as invoice_ids
        from active_relation_invoice_members relation_member
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
            code=contract.relation_split_issue_code,
            message=f"{contract.direction.title()} invoices from the same active relation are split across multiple page rows in one scope.",
            subject_id=_text(row.get("case_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "row_count", "row_ids", "invoice_ids"),
        )
        for row in rows
    ]


def _invalid_relation_status_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    _ = tenant_id
    invalid_status_exists_sql = """
        exists (
            select 1
            from jsonb_array_elements(
                case
                    when jsonb_typeof(row.payload->%s->'summaries') = 'array'
                    then row.payload->%s->'summaries'
                    else '[]'::jsonb
                end
            ) as summary(value)
            where coalesce(summary.value->>'relationStatus', summary.value->>'relation_status') not in ('linked', 'unlinked')
        )
    """
    rows = connection.fetch_all(
        f"""
        /* check: invalid_relation_projection_status */
        select row.scope_key, row.row_id, row.invoice_id, row.payment_status
        from {contract.rows_table} row
        where {invalid_status_exists_sql}
           or {invalid_status_exists_sql}
           or {invalid_status_exists_sql}
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
    issues = [
        AuditIssue(
            severity="error",
            code=contract.invalid_projection_status_issue_code,
            message=f"A relation status outside linked/unlinked appears inside {contract.read_model_key} summaries.",
            subject_id=_text(row.get("row_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "payment_status"),
        )
        for row in rows
    ]
    issues.extend(
        _invalid_workbench_relation_status_issues(
            connection,
            contract=contract,
            tenant_id=tenant_id,
            limit=limit,
        )
    )
    return issues


def _invalid_workbench_relation_status_issues(
    connection: Any,
    contract: InvoiceReadModelAuditContract,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: invalid_workbench_relation_status */
        with {_invoice_lookup_cte(contract)}
        select
            relation_row.scope_key,
            relation_row.row_id,
            relation_row.row_type,
            relation_row.group_ids,
            lookup.invoice_id
        from read_model.workbench_relation_rows relation_row
        join invoice_relation_lookup lookup
          on lookup.relation_row_id = relation_row.row_id
        where relation_row.tenant_id = %s
          and relation_row.relation_status not in ('linked', 'unlinked')
        order by relation_row.scope_key, relation_row.row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    issues = [
        AuditIssue(
            severity="error",
            code=contract.invalid_relation_row_status_issue_code,
            message=f"A workbench_relation row has a status outside linked/unlinked for a {contract.direction} invoice.",
            subject_id=_text(row.get("row_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "invoice_id", "row_type", "group_ids"),
        )
        for row in rows
    ]
    group_rows = connection.fetch_all(
        f"""
        /* check: invalid_workbench_relation_group_status */
        select scope_key, group_id, {contract.relation_group_ids_column}
        from read_model.workbench_relation_groups
        where tenant_id = %s
          and relation_status not in ('linked', 'unlinked')
          and coalesce(array_length({contract.relation_group_ids_column}, 1), 0) > 0
        order by scope_key, group_id
        limit %s
        """,
        (tenant_id, limit),
    )
    issues.extend(
        AuditIssue(
            severity="error",
            code=contract.invalid_relation_group_status_issue_code,
            message=f"A workbench_relation group has a status outside linked/unlinked for {contract.direction} invoices.",
            subject_id=_text(row.get("group_id")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, contract.relation_group_ids_column),
        )
        for row in group_rows
    )
    return issues


def _details(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
