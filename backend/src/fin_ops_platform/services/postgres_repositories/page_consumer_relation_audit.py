from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue


BANK_FLOW_RULE_BATCH_CONSUMER = "bank_flow_rule_batch_members"


def page_consumer_relation_edge_equality_issues(
    connection: Any,
    *,
    consumer_contract: str,
    tenant_id: str,
    limit: int,
    code_prefix: str,
    label: str,
) -> list[AuditIssue]:
    """Compare a page-owned canonical aggregate with active canonical relations."""

    if consumer_contract == BANK_FLOW_RULE_BATCH_CONSUMER:
        sql, params = _bank_flow_rule_batch_sql(tenant_id=tenant_id, limit=limit)
    else:
        raise ValueError(f"Unsupported page consumer relation contract: {consumer_contract}")
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{code_prefix}_consumer_relation_edge_mismatch",
            message=f"{label} canonical page facts do not equal active canonical relation edges.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={key: value for key, value in row.items() if key not in {"subject_id", "scope_key"}},
        )
        for row in rows
    ]






def _bank_flow_rule_batch_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    _ = tenant_id
    return (
        """
        /* check: consumer_relation_edge_equality */
        with canonical_batches as (
            select batch.batch_id, batch.status, to_char(batch.scope_month, 'YYYY-MM') as scope_key,
                   coalesce(
                       (
                           select array_agg(distinct member.row_id order by member.row_id)
                           from unnest(batch.bank_transaction_ids) member(row_id)
                           where nullif(member.row_id, '') is not null
                       ),
                       array[]::text[]
                   ) as canonical_member_ids
            from app.bank_flow_rule_batches batch
            where batch.status <> 'deleted'
        ),
        projected_batches as (
            select batch_id, canonical_member_ids as projected_member_ids
            from canonical_batches
        ),
        active_bank_relations as (
            select relation.case_id, relation.relation_mode,
                   coalesce(
                       array_agg(distinct member.row_id order by member.row_id) filter (
                           where lower(coalesce(relation.row_types[member.ordinality], ''))
                                 in ('bank', 'bank_transaction')
                             and nullif(member.row_id, '') is not null
                       ),
                       array[]::text[]
                   ) as relation_member_ids
            from app.workbench_pair_relations relation
            join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
            where relation.status = 'active'
            group by relation.case_id, relation.relation_mode
        ),
        active_batch_relations as (
            select case_id, relation_member_ids
            from active_bank_relations
            where relation_mode = 'bank_flow_rule_batch'
        ),
        conflicting_relations as (
            select batch.batch_id,
                   array_agg(relation.case_id order by relation.case_id) as conflicting_case_ids
            from canonical_batches batch
            join active_bank_relations relation
              on relation.case_id <> batch.batch_id
             and relation.relation_member_ids && batch.canonical_member_ids
            where batch.status in ('draft', 'unsubmitted')
            group by batch.batch_id
        ),
        batch_mismatches as (
            select batch.batch_id as subject_id, batch.scope_key,
                   batch.batch_id as row_id, 'bank_flow_rule_batch'::text as row_type,
                   case
                       when projected.batch_id is null then 'canonical_batch_missing_page_consumer'
                       when projected.projected_member_ids <> batch.canonical_member_ids
                       then 'page_consumer_member_set_mismatch'
                       when conflict.conflicting_case_ids is not null
                       then 'batch_members_occupied_by_other_active_relation'
                       when batch.status = 'submitted' and relation.case_id is null
                       then 'submitted_batch_missing_active_relation'
                       when batch.status <> 'submitted' and relation.case_id is not null
                       then 'non_submitted_batch_has_active_relation'
                       when batch.status = 'submitted'
                        and relation.relation_member_ids <> batch.canonical_member_ids
                       then 'active_relation_member_set_mismatch'
                       else null
                   end as mismatch_kind,
                   batch.status as canonical_status,
                   batch.canonical_member_ids,
                   projected.projected_member_ids,
                   relation.relation_member_ids,
                   conflict.conflicting_case_ids
            from canonical_batches batch
            left join projected_batches projected on projected.batch_id = batch.batch_id
            left join active_batch_relations relation on relation.case_id = batch.batch_id
            left join conflicting_relations conflict on conflict.batch_id = batch.batch_id
        ),
        relation_orphans as (
            select relation.case_id as subject_id, ''::text as scope_key,
                   relation.case_id as row_id, 'bank_flow_rule_batch'::text as row_type,
                   'active_relation_without_canonical_batch'::text as mismatch_kind,
                   null::text as canonical_status,
                   null::text[] as canonical_member_ids,
                   null::text[] as projected_member_ids,
                   relation.relation_member_ids,
                   null::text[] as conflicting_case_ids
            from active_batch_relations relation
            left join canonical_batches batch on batch.batch_id = relation.case_id
            where batch.batch_id is null
        ),
        mismatches as (
            select * from batch_mismatches where mismatch_kind is not null
            union all
            select * from relation_orphans
        )
        select mismatch_kind, subject_id, scope_key, row_id, row_type,
               canonical_status, canonical_member_ids, projected_member_ids, relation_member_ids,
               conflicting_case_ids
        from mismatches
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """,
        (limit,),
    )


def _text(value: object) -> str:
    return str(value or "").strip()
