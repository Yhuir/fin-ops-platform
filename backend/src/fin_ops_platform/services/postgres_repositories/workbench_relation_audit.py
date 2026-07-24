from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE


def workbench_relation_edge_equality_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    code_prefix: str,
    label: str,
) -> list[AuditIssue]:
    """Compare canonical relation edges with both relation projections.

    A relation is projected into its own month and every month containing
    one of its canonical members.  Equality is checked in both directions
    for the group arrays and the row index.
    """

    rows = connection.fetch_all(
        """
        /* check: relation_edge_equality */
        with eligible_active_relations as (
            select *
            from app.workbench_pair_relations
            where status = 'active'
              and relation_mode <> %s
        ),
        active_relation_members as (
            select
                relation.case_id,
                relation.month_scope,
                member.row_id,
                case
                    when lower(coalesce(relation.row_types[member.ordinality], ''))
                         in ('bank', 'bank_transaction') then 'bank_transaction'
                    when lower(coalesce(relation.row_types[member.ordinality], '')) = 'oa' then 'oa'
                    when lower(coalesce(relation.row_types[member.ordinality], ''))
                         in ('input', 'input_invoice') then 'input_invoice'
                    when lower(coalesce(relation.row_types[member.ordinality], ''))
                         in ('output', 'output_invoice') then 'output_invoice'
                    when lower(coalesce(relation.row_types[member.ordinality], ''))
                         in ('invoice', 'formal_invoice') then
                        case
                            when coalesce(invoice.invoice_type, '') like 'output%%'
                              or coalesce(invoice.invoice_type, '') like '销项%%'
                            then 'output_invoice'
                            else 'input_invoice'
                        end
                    else lower(coalesce(relation.row_types[member.ordinality], ''))
                end as row_type
            from eligible_active_relations relation
            join lateral unnest(relation.row_ids) with ordinality
              as member(row_id, ordinality) on true
            left join app.invoices invoice
              on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.row_id
             and invoice.status <> 'deleted'
        ),
        relation_scope_candidates as (
            select relation.case_id, to_char(relation.month_scope, 'YYYY-MM') as scope_key
            from eligible_active_relations relation
            where relation.month_scope is not null
            union
            select member.case_id, to_char(bank.txn_month, 'YYYY-MM')
            from active_relation_members member
            join app.bank_transactions bank
              on coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
             and bank.status <> 'deleted'
            where bank.txn_month is not null
            union
            select member.case_id, to_char(invoice.invoice_month, 'YYYY-MM')
            from active_relation_members member
            join app.invoices invoice
              on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.row_id
             and invoice.status <> 'deleted'
            where invoice.invoice_month is not null
            union
            select member.case_id, to_char(date_trunc('month', oa.application_date), 'YYYY-MM')
            from active_relation_members member
            join app.oa_applications oa on oa.row_id = member.row_id
            where oa.status <> 'deleted'
              and oa.application_date is not null
        ),
        expected_edges as (
            select distinct member.case_id, scope.scope_key, member.row_id, member.row_type
            from active_relation_members member
            join relation_scope_candidates scope on scope.case_id = member.case_id
            where nullif(member.row_id, '') is not null
              and nullif(member.row_type, '') is not null
              and nullif(scope.scope_key, '') is not null
        ),
        projected_group_edges as (
            select distinct group_row.group_id as case_id, group_row.scope_key, edge.row_id, edge.row_type
            from read_model.workbench_relation_groups group_row
            join lateral (
                select row_id, 'oa'::text as row_type from unnest(group_row.oa_row_ids) as item(row_id)
                union all
                select row_id, 'bank_transaction' from unnest(group_row.bank_transaction_ids) as item(row_id)
                union all
                select row_id, 'input_invoice' from unnest(group_row.input_invoice_ids) as item(row_id)
                union all
                select row_id, 'output_invoice' from unnest(group_row.output_invoice_ids) as item(row_id)
            ) edge on true
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
        ),
        projected_index_edges as (
            select distinct group_id as case_id, relation_row.scope_key,
                   relation_row.row_id, relation_row.row_type
            from read_model.workbench_relation_rows relation_row
            join lateral unnest(relation_row.group_ids) as item(group_id) on true
            where relation_row.tenant_id = %s
              and relation_row.relation_status = 'linked'
        ),
        mismatches as (
            select 'canonical_missing_group_edge' as mismatch_kind, expected.*
            from expected_edges expected
            where not exists (
                select 1 from projected_group_edges projected
                where projected.case_id = expected.case_id
                  and projected.scope_key = expected.scope_key
                  and projected.row_id = expected.row_id
                  and projected.row_type = expected.row_type
            )
            union all
            select 'projected_group_edge_not_canonical', projected.*
            from projected_group_edges projected
            where not exists (
                select 1 from expected_edges expected
                where expected.case_id = projected.case_id
                  and expected.scope_key = projected.scope_key
                  and expected.row_id = projected.row_id
                  and expected.row_type = projected.row_type
            )
            union all
            select 'group_edge_missing_row_index', projected.*
            from projected_group_edges projected
            where not exists (
                select 1 from projected_index_edges index_edge
                where index_edge.case_id = projected.case_id
                  and index_edge.scope_key = projected.scope_key
                  and index_edge.row_id = projected.row_id
                  and index_edge.row_type = projected.row_type
            )
            union all
            select 'row_index_edge_missing_group', index_edge.*
            from projected_index_edges index_edge
            where not exists (
                select 1 from projected_group_edges projected
                where projected.case_id = index_edge.case_id
                  and projected.scope_key = index_edge.scope_key
                  and projected.row_id = index_edge.row_id
                  and projected.row_type = index_edge.row_type
            )
        )
        select mismatch_kind, case_id as subject_id, scope_key, row_id, row_type
        from mismatches
        order by mismatch_kind, scope_key, case_id, row_id
        limit %s
        """,
        (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, tenant_id, tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"{code_prefix}_relation_edge_mismatch",
            message=f"{label} canonical and projected relation edges are not equal in both directions.",
            subject_id=str(row.get("subject_id") or "").strip(),
            scope_key=str(row.get("scope_key") or "").strip(),
            details={
                "mismatch_kind": str(row.get("mismatch_kind") or "").strip(),
                "row_id": str(row.get("row_id") or "").strip(),
                "row_type": str(row.get("row_type") or "").strip(),
            },
        )
        for row in rows
    ]
