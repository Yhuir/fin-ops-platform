from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue


OA_PENDING_PAYMENT_CONSUMER = "oa_pending_payment_summaries"
PENDING_INVOICE_CONSUMER = "pending_invoice_summaries"
BANK_DETAIL_TAG_CONSUMER = "bank_detail_relation_tags"
BANK_FLOW_RULE_BATCH_CONSUMER = "bank_flow_rule_batch_members"
BATCH_ACCOUNTING_DIRECT_CONSUMER = "batch_accounting_direct_shared_relation"
TURNOVER_LEDGER_CONSUMER = "turnover_ledger_relation_summaries"


def page_consumer_relation_edge_equality_issues(
    connection: Any,
    *,
    consumer_contract: str,
    tenant_id: str,
    limit: int,
    code_prefix: str,
    label: str,
) -> list[AuditIssue]:
    """Compare registered page-consumer edges with shared linked relations.

    Canonical-to-shared equality is owned by ``workbench_relation_audit``.
    This boundary proves the next hop only: shared relation groups to the
    complete relation summaries persisted for one page.
    """

    if consumer_contract == OA_PENDING_PAYMENT_CONSUMER:
        sql, params = _oa_pending_payment_sql(tenant_id=tenant_id, limit=limit)
    elif consumer_contract == PENDING_INVOICE_CONSUMER:
        sql, params = _pending_invoice_sql(tenant_id=tenant_id, limit=limit)
    elif consumer_contract == BANK_DETAIL_TAG_CONSUMER:
        sql, params = _bank_detail_tag_sql(tenant_id=tenant_id, limit=limit)
    elif consumer_contract == BANK_FLOW_RULE_BATCH_CONSUMER:
        sql, params = _bank_flow_rule_batch_sql(tenant_id=tenant_id, limit=limit)
    elif consumer_contract == BATCH_ACCOUNTING_DIRECT_CONSUMER:
        sql, params = _batch_accounting_direct_sql(tenant_id=tenant_id, limit=limit)
    elif consumer_contract == TURNOVER_LEDGER_CONSUMER:
        sql, params = _turnover_ledger_sql(tenant_id=tenant_id, limit=limit)
    else:
        raise ValueError(f"Unsupported page consumer relation contract: {consumer_contract}")
    rows = connection.fetch_all(sql, params)
    return [
        AuditIssue(
            severity="error",
            code=f"{code_prefix}_consumer_relation_edge_mismatch",
            message=f"{label} consumer relation summaries do not equal the registered shared linked relation edges.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details={key: value for key, value in row.items() if key not in {"subject_id", "scope_key"}},
        )
        for row in rows
    ]


def _oa_pending_payment_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        /* check: consumer_relation_edge_equality */
        with canonical_oa as (
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
        ),
        identity_aliases as (
            select distinct
                   coalesce(nullif(alias.value->>'id', ''), nullif(alias.value->>'row_id', '')) as alias_row_id,
                   row.row_id as canonical_row_id
            from read_model.workbench_generations generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'identity_alias_rows'->'bank') = 'array'
                     then row.payload->'identity_alias_rows'->'bank' else '[]'::jsonb end
            ) alias(value) on true
            where generation.tenant_id = %s
              and generation.status = 'active'
              and generation.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
              and nullif(coalesce(alias.value->>'id', alias.value->>'row_id'), '') is not null
        ),
        shared_groups as (
            select group_row.*
            from read_model.workbench_relation_groups group_row
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
              and exists (
                  select 1
                  from unnest(group_row.oa_row_ids) member(row_id)
                  join canonical_oa source on source.oa_id = member.row_id
              )
        ),
        pending_groups as (
            select relation.relation_id as group_id,
                   to_char(relation.scope_month, 'YYYY-MM') as scope_key,
                   relation.oa_row_ids,
                   relation.bank_transaction_ids,
                   array[]::text[] as input_invoice_ids
            from app.oa_pending_payment_bank_relations relation
            where relation.status = 'active'
              and exists (
                  select 1
                  from unnest(relation.oa_row_ids) member(row_id)
                  join canonical_oa source on source.oa_id = member.row_id
              )
        ),
        relevant_groups as (
            select group_id, scope_key, oa_row_ids, bank_transaction_ids, input_invoice_ids
            from shared_groups
            union all
            select group_id, scope_key, oa_row_ids, bank_transaction_ids, input_invoice_ids
            from pending_groups
        ),
        expected_edge_rows as (
            select group_row.group_id as case_id, group_row.scope_key,
                   member.row_id, 'oa'::text as row_type
            from relevant_groups group_row
            join lateral unnest(group_row.oa_row_ids) member(row_id) on true
            union all
            select group_row.group_id, group_row.scope_key,
                   coalesce(identity.canonical_row_id, member.row_id), 'bank_transaction'::text
            from relevant_groups group_row
            join lateral unnest(group_row.bank_transaction_ids) member(row_id) on true
            left join identity_aliases identity on identity.alias_row_id = member.row_id
            union all
            select group_row.group_id, group_row.scope_key,
                   member.row_id, 'input_invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.input_invoice_ids) member(row_id) on true
        ),
        expected_edges as (
            select case_id, row_id, row_type, min(scope_key) as scope_key
            from expected_edge_rows
            where nullif(case_id, '') is not null
              and nullif(row_id, '') is not null
            group by case_id, row_id, row_type
        ),
        consumer_edge_rows as (
            select summary.value->>'relationCaseId' as case_id, row.scope_key,
                   coalesce(nullif(summary.value->>'oaId', ''), summary.value->>'id') as row_id,
                   'oa'::text as row_type
            from read_model.oa_pending_payment_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'oa'->'summaries') = 'array'
                     then row.payload->'oa'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relationStatus', '')) = 'linked'
            union all
            select summary.value->>'relationCaseId', row.scope_key,
                   coalesce(identity.canonical_row_id, summary.value->>'bankTransactionId'),
                   'bank_transaction'::text
            from read_model.oa_pending_payment_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'bankTransaction'->'summaries') = 'array'
                     then row.payload->'bankTransaction'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            left join identity_aliases identity
              on identity.alias_row_id = summary.value->>'bankTransactionId'
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relationStatus', '')) = 'linked'
            union all
            select summary.value->>'relationCaseId', row.scope_key,
                   summary.value->>'invoiceId', 'input_invoice'::text
            from read_model.oa_pending_payment_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'invoice'->'summaries') = 'array'
                     then row.payload->'invoice'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relationStatus', '')) = 'linked'
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
        (tenant_id, tenant_id, tenant_id, limit),
    )


def _pending_invoice_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        /* check: consumer_relation_edge_equality */
        with relevant_groups as (
            select group_row.*
            from read_model.workbench_relation_groups group_row
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
              and exists (
                  select 1
                  from unnest(group_row.bank_transaction_ids) member(row_id)
                  join app.bank_transactions source
                    on coalesce(source.legacy_mongo_id, source.id::text) = member.row_id
                   and source.status <> 'deleted'
                   and source.txn_direction in ('outflow', 'inflow')
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
                   member.row_id, 'input_invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.input_invoice_ids) member(row_id) on true
            union all
            select group_row.group_id, group_row.scope_key,
                   member.row_id, 'output_invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.output_invoice_ids) member(row_id) on true
        ),
        expected_edges as (
            select case_id, row_id, row_type, min(scope_key) as scope_key
            from expected_edge_rows
            where nullif(case_id, '') is not null
              and nullif(row_id, '') is not null
            group by case_id, row_id, row_type
        ),
        consumer_edge_rows as (
            select summary.value->>'relation_case_id' as case_id,
                   to_char(row.scope_month, 'YYYY-MM') as scope_key,
                   summary.value->>'id' as row_id, 'oa'::text as row_type
            from read_model.pending_invoice_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'oa'->'summaries') = 'array'
                     then row.payload->'oa'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relation_status', '')) = 'linked'
            union all
            select summary.value->>'relation_case_id',
                   to_char(row.scope_month, 'YYYY-MM'),
                   summary.value->>'id', 'bank_transaction'::text
            from read_model.pending_invoice_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'bank_transactions'->'summaries') = 'array'
                     then row.payload->'bank_transactions'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relation_status', '')) = 'linked'
            union all
            select summary.value->>'relation_case_id',
                   to_char(row.scope_month, 'YYYY-MM'),
                   summary.value->>'id',
                   case when row.direction = 'income'
                        then 'output_invoice'::text else 'input_invoice'::text end
            from read_model.pending_invoice_rows row
            join lateral jsonb_array_elements(
                case when jsonb_typeof(row.payload->'input_invoices'->'summaries') = 'array'
                     then row.payload->'input_invoices'->'summaries' else '[]'::jsonb end
            ) summary(value) on true
            where row.cache_status = 'fresh'
              and lower(coalesce(summary.value->>'relation_status', '')) = 'linked'
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


def _bank_detail_tag_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        /* check: consumer_relation_edge_equality */
        with canonical_bank as (
            select source.id::text as transaction_id,
                   coalesce(source.legacy_mongo_id, source.id::text) as relation_row_id,
                   to_char(source.txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions source
            where source.status <> 'deleted'
        ),
        linked_case_rows as (
            select member.row_id as relation_row_id,
                   group_row.group_id as case_id,
                   cardinality(group_row.oa_row_ids) > 0 as has_oa,
                   cardinality(group_row.input_invoice_ids) > 0
                     or cardinality(group_row.output_invoice_ids) > 0 as has_invoice
            from read_model.workbench_relation_groups group_row
            join lateral unnest(group_row.bank_transaction_ids) member(row_id) on true
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
        ),
        expected as (
            select bank.transaction_id, bank.scope_key,
                   count(distinct linked.case_id)::integer as linked_case_count,
                   min(linked.case_id) as expected_case_id,
                   coalesce(bool_or(linked.has_oa), false) as expected_has_oa,
                   coalesce(bool_or(linked.has_invoice), false) as expected_has_invoice
            from canonical_bank bank
            left join linked_case_rows linked
              on linked.relation_row_id = bank.relation_row_id
            group by bank.transaction_id, bank.scope_key
        ),
        projected as (
            select row.transaction_id, row.scope_key,
                   coalesce(row.oa_relation_tag, '') as oa_relation_tag,
                   coalesce(row.invoice_relation_tag, '') as invoice_relation_tag,
                   nullif(row.relation_case_id, '') as relation_case_id,
                   lower(coalesce(row.payload->>'relation_status', '')) as relation_status
            from read_model.bank_detail_rows row
            where row.tenant_id = %s
        ),
        mismatches as (
            select expected.transaction_id as subject_id, expected.scope_key,
                   expected.transaction_id as row_id, 'bank_transaction'::text as row_type,
                   case
                       when expected.linked_case_count > 1 then 'shared_bank_member_multiple_cases'
                       when expected.linked_case_count = 1
                        and projected.transaction_id is null then 'linked_bank_missing_consumer_row'
                       when expected.linked_case_count = 1
                        and projected.relation_status <> 'linked' then 'linked_status_missing_consumer'
                       when expected.linked_case_count = 1
                        and projected.relation_case_id is distinct from expected.expected_case_id
                       then 'linked_case_mismatch'
                       when expected.linked_case_count = 1
                        and projected.oa_relation_tag
                            <> case when expected.expected_has_oa then '有oa' else '无oa' end
                       then 'linked_oa_tag_mismatch'
                       when expected.linked_case_count = 1
                        and projected.invoice_relation_tag
                            <> case when expected.expected_has_invoice then '有发票' else '无发票' end
                       then 'linked_invoice_tag_mismatch'
                       when expected.linked_case_count = 0
                        and (
                               projected.relation_status = 'linked'
                            or projected.oa_relation_tag = '有oa'
                            or projected.invoice_relation_tag = '有发票'
                        )
                       then 'consumer_linked_tag_not_shared'
                       else null
                   end as mismatch_kind,
                   expected.expected_case_id,
                   expected.linked_case_count,
                   expected.expected_has_oa,
                   expected.expected_has_invoice,
                   projected.relation_case_id as projected_case_id,
                   projected.relation_status as projected_relation_status,
                   projected.oa_relation_tag as projected_oa_relation_tag,
                   projected.invoice_relation_tag as projected_invoice_relation_tag
            from expected
            left join projected on projected.transaction_id = expected.transaction_id
        )
        select mismatch_kind, subject_id, scope_key, row_id, row_type,
               expected_case_id, linked_case_count,
               expected_has_oa, expected_has_invoice,
               projected_case_id, projected_relation_status,
               projected_oa_relation_tag, projected_invoice_relation_tag
        from mismatches
        where mismatch_kind is not null
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """,
        (tenant_id, tenant_id, limit),
    )


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
            select row.batch_id,
                   coalesce(
                       (
                           select array_agg(distinct member.row_id order by member.row_id)
                           from jsonb_array_elements_text(
                               case
                                   when jsonb_typeof(row.payload->'bank_transaction_ids') = 'array'
                                   then row.payload->'bank_transaction_ids'
                                   when jsonb_typeof(row.payload->'row_ids') = 'array'
                                   then row.payload->'row_ids'
                                   else '[]'::jsonb
                               end
                           ) member(row_id)
                           where nullif(member.row_id, '') is not null
                       ),
                       array[]::text[]
                   ) as projected_member_ids
            from read_model.bank_flow_rule_batch_rows row
            where row.cache_status = 'fresh'
        ),
        active_batch_relations as (
            select relation.case_id,
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
              and relation.relation_mode = 'bank_flow_rule_batch'
            group by relation.case_id
        ),
        batch_mismatches as (
            select batch.batch_id as subject_id, batch.scope_key,
                   batch.batch_id as row_id, 'bank_flow_rule_batch'::text as row_type,
                   case
                       when projected.batch_id is null then 'canonical_batch_missing_page_consumer'
                       when projected.projected_member_ids <> batch.canonical_member_ids
                       then 'page_consumer_member_set_mismatch'
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
                   relation.relation_member_ids
            from canonical_batches batch
            left join projected_batches projected on projected.batch_id = batch.batch_id
            left join active_batch_relations relation on relation.case_id = batch.batch_id
        ),
        relation_orphans as (
            select relation.case_id as subject_id, ''::text as scope_key,
                   relation.case_id as row_id, 'bank_flow_rule_batch'::text as row_type,
                   'active_relation_without_canonical_batch'::text as mismatch_kind,
                   null::text as canonical_status,
                   null::text[] as canonical_member_ids,
                   null::text[] as projected_member_ids,
                   relation.relation_member_ids
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
               canonical_status, canonical_member_ids, projected_member_ids, relation_member_ids
        from mismatches
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """,
        (limit,),
    )


def _batch_accounting_direct_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        /* check: consumer_relation_edge_equality */
        with canonical_cases as (
            select relation.case_id, relation.relation_mode, relation.special_metadata,
                   to_char(relation.month_scope, 'YYYY-MM') as scope_key
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.special_metadata->>'source' = 'batch_accounting'
        ),
        consumer_groups as (
            select group_row.group_id, group_row.scope_key,
                   group_row.payload->>'relation_mode' as projected_relation_mode,
                   group_row.payload->'special_metadata' as projected_special_metadata,
                   group_row.payload->'special_metadata'->>'source' as projected_source
            from read_model.workbench_relation_groups group_row
            where group_row.tenant_id = %s
              and group_row.relation_status = 'linked'
              and group_row.payload->'special_metadata'->>'source' = 'batch_accounting'
        ),
        canonical_mismatches as (
            select canonical.case_id as subject_id, canonical.scope_key,
                   canonical.case_id as row_id, 'batch_accounting_relation'::text as row_type,
                   case
                       when canonical.relation_mode <> 'batch_accounting'
                       then 'canonical_batch_accounting_relation_mode_mismatch'
                       when not exists (
                           select 1 from consumer_groups consumer
                           where consumer.group_id = canonical.case_id
                       )
                       then 'canonical_case_missing_direct_consumer'
                       when exists (
                           select 1 from consumer_groups consumer
                           where consumer.group_id = canonical.case_id
                             and (
                                    coalesce(consumer.projected_relation_mode, '') <> 'batch_accounting'
                                 or coalesce(consumer.projected_source, '') <> 'batch_accounting'
                                 or coalesce(consumer.projected_special_metadata, '{}'::jsonb)
                                    <> coalesce(canonical.special_metadata, '{}'::jsonb)
                             )
                       )
                       then 'direct_consumer_mode_or_metadata_mismatch'
                       else null
                   end as mismatch_kind,
                   canonical.relation_mode as canonical_relation_mode,
                   canonical.special_metadata as canonical_special_metadata
            from canonical_cases canonical
        ),
        consumer_orphans as (
            select consumer.group_id as subject_id, min(consumer.scope_key) as scope_key,
                   consumer.group_id as row_id, 'batch_accounting_relation'::text as row_type,
                   'direct_consumer_case_not_canonical'::text as mismatch_kind,
                   null::text as canonical_relation_mode,
                   null::jsonb as canonical_special_metadata
            from consumer_groups consumer
            left join canonical_cases canonical on canonical.case_id = consumer.group_id
            where canonical.case_id is null
            group by consumer.group_id
        ),
        mismatches as (
            select * from canonical_mismatches where mismatch_kind is not null
            union all
            select * from consumer_orphans
        )
        select mismatch_kind, subject_id, scope_key, row_id, row_type,
               canonical_relation_mode, canonical_special_metadata
        from mismatches
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """,
        (tenant_id, limit),
    )


def _turnover_ledger_sql(*, tenant_id: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        /* check: consumer_relation_edge_equality */
        with consumer_anchors as (
            select ledger.relation_id as anchor_id,
                   to_char(ledger.scope_month, 'YYYY-MM') as scope_key,
                   ledger.bank_row_ids as anchor_bank_row_ids,
                   ledger.payload as anchor_payload
            from read_model.turnover_ledger_rows ledger
            union all
            select ledger.relation_id || ':flow:' || flow.ordinality::text,
                   to_char(ledger.scope_month, 'YYYY-MM'),
                   array(
                       select distinct item.row_id
                       from (
                           select nullif(flow.value->>'source_bank_row_id', '') as row_id
                           union all
                           select nullif(flow.value->>'principal_bank_row_id', '')
                           union all
                           select value
                           from jsonb_array_elements_text(
                               case when jsonb_typeof(flow.value->'bank_row_ids') = 'array'
                                    then flow.value->'bank_row_ids' else '[]'::jsonb end
                           ) member(value)
                           union all
                           select value
                           from jsonb_array_elements_text(
                               case when jsonb_typeof(flow.value->'settlement_bank_row_ids') = 'array'
                                    then flow.value->'settlement_bank_row_ids' else '[]'::jsonb end
                           ) member(value)
                       ) item
                       where nullif(item.row_id, '') is not null
                       order by item.row_id
                   ),
                   flow.value
            from read_model.turnover_ledger_rows ledger
            join lateral jsonb_array_elements(
                case when jsonb_typeof(ledger.payload->'flow_rows') = 'array'
                     then ledger.payload->'flow_rows' else '[]'::jsonb end
            ) with ordinality flow(value, ordinality) on true
        ),
        relevant_groups as (
            select anchor.anchor_id,
                   anchor.scope_key as anchor_scope_key,
                   group_row.group_id,
                   group_row.oa_row_ids,
                   group_row.bank_transaction_ids,
                   group_row.input_invoice_ids,
                   group_row.output_invoice_ids
            from consumer_anchors anchor
            join read_model.workbench_relation_groups group_row
              on group_row.tenant_id = %s
             and group_row.relation_status = 'linked'
             and group_row.bank_transaction_ids && anchor.anchor_bank_row_ids
        ),
        expected_edge_rows as (
            select group_row.anchor_id, group_row.anchor_scope_key as scope_key,
                   group_row.group_id as case_id, member.row_id, 'oa'::text as row_type
            from relevant_groups group_row
            join lateral unnest(group_row.oa_row_ids) member(row_id) on true
            union all
            select group_row.anchor_id, group_row.anchor_scope_key,
                   group_row.group_id, member.row_id, 'bank_transaction'::text
            from relevant_groups group_row
            join lateral unnest(group_row.bank_transaction_ids) member(row_id) on true
            union all
            select group_row.anchor_id, group_row.anchor_scope_key,
                   group_row.group_id, member.row_id, 'invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.input_invoice_ids) member(row_id) on true
            union all
            select group_row.anchor_id, group_row.anchor_scope_key,
                   group_row.group_id, member.row_id, 'invoice'::text
            from relevant_groups group_row
            join lateral unnest(group_row.output_invoice_ids) member(row_id) on true
        ),
        expected_edges as (
            select anchor_id, case_id, row_id, row_type, min(scope_key) as scope_key
            from expected_edge_rows
            where nullif(case_id, '') is not null and nullif(row_id, '') is not null
            group by anchor_id, case_id, row_id, row_type
        ),
        consumer_edge_rows as (
            select anchor.anchor_id, anchor.scope_key,
                   relation.value->>'case_id' as case_id,
                   member.row_id,
                   case
                       when lower(coalesce(relation.value->'row_types'->>((member.ordinality - 1)::integer), '')) like '%%oa%%'
                         or lower(member.row_id) like 'oa%%' then 'oa'
                       when lower(coalesce(relation.value->'row_types'->>((member.ordinality - 1)::integer), '')) like '%%invoice%%'
                         or lower(member.row_id) like any(array['invoice%%', 'input_invoice%%', 'output_invoice%%', 'inv%%'])
                       then 'invoice'
                       else 'bank_transaction'
                   end as row_type
            from consumer_anchors anchor
            join lateral jsonb_array_elements(
                case when jsonb_typeof(anchor.anchor_payload->'workbench_relations') = 'array'
                     then anchor.anchor_payload->'workbench_relations' else '[]'::jsonb end
            ) relation(value) on true
            join lateral jsonb_array_elements_text(
                case when jsonb_typeof(relation.value->'row_ids') = 'array'
                     then relation.value->'row_ids' else '[]'::jsonb end
            ) with ordinality member(row_id, ordinality) on true
            where lower(coalesce(relation.value->>'relation_status', 'linked')) in ('linked', 'active')
        ),
        consumer_edges as (
            select anchor_id, case_id, row_id, row_type, min(scope_key) as scope_key
            from consumer_edge_rows
            where nullif(case_id, '') is not null and nullif(row_id, '') is not null
            group by anchor_id, case_id, row_id, row_type
        ),
        mismatches as (
            select 'shared_edge_missing_consumer' as mismatch_kind, expected.*
            from expected_edges expected
            where not exists (
                select 1 from consumer_edges consumer
                where consumer.anchor_id = expected.anchor_id
                  and consumer.case_id = expected.case_id
                  and consumer.row_id = expected.row_id
                  and consumer.row_type = expected.row_type
            )
            union all
            select 'consumer_edge_not_shared', consumer.*
            from consumer_edges consumer
            where not exists (
                select 1 from expected_edges expected
                where expected.anchor_id = consumer.anchor_id
                  and expected.case_id = consumer.case_id
                  and expected.row_id = consumer.row_id
                  and expected.row_type = consumer.row_type
            )
        )
        select mismatch_kind, anchor_id as subject_id, scope_key, row_id, row_type, case_id
        from mismatches
        order by mismatch_kind, subject_id, case_id, row_type, row_id
        limit %s
        """,
        (tenant_id, limit),
    )


def _text(value: object) -> str:
    return str(value or "").strip()
