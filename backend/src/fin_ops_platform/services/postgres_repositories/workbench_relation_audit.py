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
    """Validate canonical relation members against canonical source facts."""
    del tenant_id
    rows = connection.fetch_all(
        """
        /* check: canonical_relation_member_integrity */
        with active_relations as (
            select case_id, row_ids, row_types
            from app.workbench_pair_relations
            where status = 'active'
              and relation_mode <> %s
        ),
        malformed as (
            select
                relation.case_id,
                'member_cardinality_mismatch'::text as mismatch_kind,
                ''::text as row_id,
                ''::text as row_type
            from active_relations relation
            where cardinality(relation.row_ids) = 0
               or cardinality(relation.row_ids) <> cardinality(relation.row_types)
        ),
        members as (
            select
                relation.case_id,
                member.row_id,
                case
                    when lower(member.row_type) in ('bank', 'bank_transaction') then 'bank'
                    when lower(member.row_type) in ('oa', 'oa_application') then 'oa'
                    when lower(member.row_type) in (
                        'invoice', 'invoice_record', 'formal', 'formal_invoice',
                        'input', 'input_invoice', 'output', 'output_invoice',
                        'etc_summary', 'etc_invoice_summary'
                    ) then 'invoice'
                    else lower(coalesce(member.row_type, ''))
                end as row_type
            from active_relations relation
            join lateral unnest(relation.row_ids, relation.row_types)
                as member(row_id, row_type)
              on cardinality(relation.row_ids) = cardinality(relation.row_types)
        ),
        missing_source as (
            select
                member.case_id,
                'canonical_member_missing'::text as mismatch_kind,
                member.row_id,
                member.row_type
            from members member
            where nullif(btrim(member.row_id), '') is null
               or member.row_type not in ('oa', 'bank', 'invoice')
               or (
                    member.row_type = 'bank'
                    and not exists (
                        select 1 from app.bank_transactions source
                        where coalesce(source.legacy_mongo_id, source.id::text) = member.row_id
                          and source.status <> 'deleted'
                    )
               )
               or (
                    member.row_type = 'oa'
                    and not exists (
                        select 1 from app.oa_applications source
                        where source.row_id = member.row_id
                          and source.status <> 'deleted'
                    )
               )
               or (
                    member.row_type = 'invoice'
                    and not exists (
                        select 1 from app.invoices source
                        where coalesce(source.legacy_mongo_id, source.id::text) = member.row_id
                          and source.status <> 'deleted'
                    )
               )
        ),
        duplicate_members as (
            select
                member.case_id,
                'duplicate_canonical_member'::text as mismatch_kind,
                member.row_id,
                member.row_type
            from members member
            group by member.case_id, member.row_id, member.row_type
            having count(*) > 1
        )
        select mismatch_kind, case_id as subject_id, row_id, row_type
        from (
            select * from malformed
            union all
            select * from missing_source
            union all
            select * from duplicate_members
        ) issue
        order by mismatch_kind, subject_id, row_type, row_id
        limit %s
        """,
        (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=f"{code_prefix}_relation_edge_mismatch",
            message=f"{label} canonical relation members do not match canonical source facts.",
            subject_id=str(row.get("subject_id") or "").strip(),
            details={
                "mismatch_kind": str(row.get("mismatch_kind") or "").strip(),
                "row_id": str(row.get("row_id") or "").strip(),
                "row_type": str(row.get("row_type") or "").strip(),
            },
        )
        for row in rows
    ]
