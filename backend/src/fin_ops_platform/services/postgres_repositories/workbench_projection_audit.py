from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    COMPLETED_WORKFLOW_STATUS_SQL,
    OA_PROJECTION_SYNC_VERSION,
)
from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue
from fin_ops_platform.services.workbench_free_matching_engine import RULE_VERSION as WORKBENCH_FORMAL_RELATION_RULE_VERSION
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_MONTH_BUILDER = _sql_text(WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION)
_FORMAL_RELATION_RULE = _sql_text(WORKBENCH_FORMAL_RELATION_RULE_VERSION)
_OA_SYNC = _sql_text(OA_PROJECTION_SYNC_VERSION)
_ATTACHMENT_PARSER = _sql_text(attachment_invoice_cache_parser_version())


def workbench_projection_integrity_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    return _integrity_issues_for_queries(
        connection,
        tenant_id=tenant_id,
        limit=limit,
        queries=_PROOF_QUERIES,
    )


def workbench_etc_relation_integrity_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    return _integrity_issues_for_queries(
        connection,
        tenant_id=tenant_id,
        limit=limit,
        queries=_ETC_RELATION_PROOF_QUERIES,
    )


def _integrity_issues_for_queries(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    queries: tuple[tuple[str, str, str], ...],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for sql, code, message in queries:
        rows = connection.fetch_all(sql, (tenant_id, limit))
        issues.extend(
            AuditIssue(
                severity="error",
                code=code,
                message=message,
                subject_id=str(row.get("subject_id") or "") or None,
                scope_key=str(row.get("scope_key") or "") or None,
                details={
                    key: value
                    for key, value in row.items()
                    if key not in {"subject_id", "scope_key"}
                }
                or None,
            )
            for row in rows
        )
    return issues


_CANONICAL_CTES = r"""
with active_generations as (
    select distinct on (scope_key)
           generation_id, scope_key, row_count, group_count, summary_count
    from read_model.workbench_generations
    where tenant_id = %s
      and status = 'active'
      and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
    order by scope_key, activated_at desc nulls last, updated_at desc
),
active_relation_members as (
    select member.row_id
    from app.workbench_pair_relations relation
    join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
    where relation.status = 'active'
),
submitted_etc_invoice_ids as (
    select invoice_id
    from app.etc_batch_invoice_links
    where link_status = 'active'
),
canonical_oa as (
    select oa.row_id,
           to_char(coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date), 'YYYY-MM') as scope_key,
           'oa'::text as source_kind,
           oa.amount::numeric as amount,
           coalesce(oa.applicant, '') as counterparty_name,
           coalesce(oa.project_name, '') as project_name
    from app.oa_applications oa
    where oa.status <> 'deleted'
      and (
            oa.workflow_status is null or oa.workflow_status = ''
         or oa.workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
         or exists (
              select 1 from active_relation_members member
              where member.row_id = oa.row_id
         )
      )
      and coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date) is not null
    union all
    select admission.oa_id,
           admission.scope_key,
           'oa'::text,
           admission.amount::numeric,
           coalesce(admission.applicant, ''),
           coalesce(admission.project_name_display, admission.project_name, '')
    from app.oa_pending_payment_admissions admission
    where admission.tenant_id = 'default'
      and admission.workflow_status = 'in_progress'
),
canonical_bank as (
    select coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
           to_char(bank.txn_month, 'YYYY-MM') as scope_key,
           'bank'::text as source_kind,
           abs(coalesce(bank.amount, 0))::numeric as amount,
           coalesce(bank.counterparty_name_raw, '') as counterparty_name,
           ''::text as project_name
    from app.bank_transactions bank
    where bank.status <> 'deleted'
      and bank.txn_month is not null
),
canonical_invoice as (
    select coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
           to_char(invoice.invoice_month, 'YYYY-MM') as scope_key,
           case when exists (
                select 1
                from jsonb_array_elements(
                    case when jsonb_typeof(invoice.source_links) = 'array'
                         then invoice.source_links else '[]'::jsonb end
                ) link(value)
                where link.value->>'source_type' = 'oa_attachment_invoice'
           ) then 'oa_attachment_invoice' else 'invoice' end as source_kind,
           abs(coalesce(invoice.total_with_tax, invoice.amount, 0))::numeric as amount,
           coalesce(invoice.counterparty_name, invoice.seller_name, invoice.buyer_name, '') as counterparty_name,
           ''::text as project_name
    from app.invoices invoice
    where invoice.status <> 'deleted'
      and invoice.invoice_month is not null
      and coalesce(invoice.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
      and coalesce(invoice.raw_payload->'normalized_payload'->>'workbench_visibility', 'visible')
          <> 'hidden_after_etc_submission'
      and coalesce(invoice.raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
      and not exists (
          select 1 from submitted_etc_invoice_ids submitted where submitted.invoice_id = invoice.id
      )
      and not exists (
          select 1
          from app.etc_invoices etc_invoice
          left join app.etc_business_batches business_batch
            on business_batch.business_batch_id = etc_invoice.business_batch_id
          where (
                  (
                      nullif(coalesce(invoice.digital_invoice_no, invoice.invoice_no), '') is not null
                  and etc_invoice.invoice_no = coalesce(invoice.digital_invoice_no, invoice.invoice_no)
                  )
               or (
                      nullif(invoice.invoice_code, '') is not null
                  and nullif(invoice.invoice_no, '') is not null
                  and etc_invoice.invoice_code = invoice.invoice_code
                  and etc_invoice.invoice_no = invoice.invoice_no
                  )
          )
            and (
                  business_batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
               or (
                      etc_invoice.status = 'submitted'
                  and coalesce(business_batch.status, '') <> 'deleted'
                  )
            )
      )
),
canonical_rows as (
    select * from canonical_oa
    union all select * from canonical_bank
    union all select * from canonical_invoice
),
attachment_scope_owners as (
    select distinct
           regexp_replace(
               coalesce(
                   nullif(link.value->>'derived_from_oa_id', ''),
                   nullif(link.value->>'source_expense_item_id', '')
               ),
               ':item:.*$',
               ''
           ) as oa_row_id,
           to_char(invoice.invoice_month, 'YYYY-MM') as scope_key
    from app.invoices invoice
    join lateral jsonb_array_elements(
        case when jsonb_typeof(invoice.source_links) = 'array'
             then invoice.source_links else '[]'::jsonb end
    ) link(value) on true
    where invoice.status <> 'deleted'
      and invoice.invoice_month is not null
      and link.value->>'source_type' = 'oa_attachment_invoice'
      and nullif(
          coalesce(
              link.value->>'derived_from_oa_id',
              link.value->>'source_expense_item_id'
          ),
          ''
      ) is not null
),
canonical_expected_scopes as (
    select canonical.row_id, canonical.scope_key as source_scope_key,
           canonical.scope_key as expected_scope_key, canonical.source_kind,
           canonical.amount, canonical.counterparty_name, canonical.project_name
    from canonical_rows canonical
    union
    select canonical.row_id, canonical.scope_key,
           related.scope_key, canonical.source_kind,
           canonical.amount, canonical.counterparty_name, canonical.project_name
    from canonical_rows canonical
    join app.workbench_pair_relations relation
      on relation.status = 'active'
     and canonical.row_id = any(relation.row_ids)
    join lateral unnest(relation.row_ids) related_member(row_id) on true
    join canonical_rows related on related.row_id = related_member.row_id
    union
    select canonical.row_id, canonical.scope_key,
           attachment.scope_key, canonical.source_kind,
           canonical.amount, canonical.counterparty_name, canonical.project_name
    from canonical_rows canonical
    join attachment_scope_owners attachment
      on canonical.source_kind = 'oa'
     and attachment.oa_row_id = canonical.row_id
),
projected_primary_rows as (
    select generation.scope_key as generation_scope,
           row.row_id, row.source_kind,
           row.amount, coalesce(row.counterparty_name, '') as counterparty_name,
           coalesce(row.project_name, '') as project_name,
           row.payload
    from active_generations generation
    join read_model.workbench_rows row
     on row.generation_id = generation.generation_id
     and row.scope_key = generation.scope_key
),
projected_alias_rows as (
    select primary_row.generation_scope,
           coalesce(nullif(alias.value->>'id', ''), nullif(alias.value->>'row_id', '')) as row_id,
           coalesce(nullif(alias.value->>'source_kind', ''), alias_bucket.key) as source_kind,
           case
               when coalesce(replace(alias.value->>'amount_value', ',', ''), '') ~ '^-?[0-9]+([.][0-9]+)?$'
               then replace(alias.value->>'amount_value', ',', '')::numeric
               when coalesce(replace(alias.value->>'amount', ',', ''), '') ~ '^-?[0-9]+([.][0-9]+)?$'
               then replace(alias.value->>'amount', ',', '')::numeric
           end as amount,
           coalesce(alias.value->>'counterparty_name', alias.value->>'counterparty_name_raw', '') as counterparty_name,
           coalesce(alias.value->>'project_name', '') as project_name,
           alias.value as payload
    from projected_primary_rows primary_row
    join lateral jsonb_each(
        case when jsonb_typeof(primary_row.payload->'identity_alias_rows') = 'object'
             then primary_row.payload->'identity_alias_rows' else '{}'::jsonb end
    ) alias_bucket(key, value) on true
    join lateral jsonb_array_elements(
        case when jsonb_typeof(alias_bucket.value) = 'array' then alias_bucket.value else '[]'::jsonb end
    ) alias(value) on true
),
projected_rows as (
    select * from projected_primary_rows
    union all
    select * from projected_alias_rows
)
"""


_ETC_RELATION_PROOF_QUERIES: tuple[tuple[str, str, str], ...] = (
    (
        r"""
        /* check: workbench_etc_relation_expected_owner */
        with submitted_batches as (
            select batch.business_batch_id,
                   coalesce(
                       nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                       batch.business_batch_id
                   ) as external_batch_id
            from app.etc_business_batches batch
            where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
        ),
        unique_batches as (
            select external_batch_id, min(business_batch_id) as business_batch_id
            from submitted_batches
            group by external_batch_id
            having count(*) = 1
        ),
        exact_oa as (
            select oa.row_id, oa.normalized_payload->>'etc_batch_id' as external_batch_id,
                   count(*) over (partition by oa.normalized_payload->>'etc_batch_id') as oa_owner_count
            from app.oa_applications oa
            where oa.status <> 'deleted'
              and nullif(oa.normalized_payload->>'etc_batch_id', '') is not null
              and """
        + COMPLETED_WORKFLOW_STATUS_SQL
        + r"""
        ),
        expected as (
            select oa.row_id as oa_row_id, oa.external_batch_id, batch.business_batch_id,
                   relation.case_id,
                   coalesce(
                       nullif(relation.amount_check->>'external_etc_batch_id', ''),
                       nullif(relation.amount_check->>'etc_batch_id', ''),
                       nullif(relation.special_metadata->>'external_etc_batch_id', ''),
                       nullif(relation.special_metadata->>'etc_batch_id', ''),
                       nullif(relation.special_metadata->'etc_batch_link'->>'external_etc_batch_id', ''),
                       nullif(relation.special_metadata->'historical_etc_business_batch_migration'->>'external_etc_batch_id', '')
                   ) as relation_external_batch_id
            from exact_oa oa
            join unique_batches batch on batch.external_batch_id = oa.external_batch_id
            join app.workbench_pair_relations relation
              on relation.status = 'active'
             and exists (
                    select 1
                    from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
                    where member.row_id = oa.row_id and member.row_type = 'oa'
                 )
            where oa.oa_owner_count = 1
        )
        select expected.case_id as subject_id, 'all'::text as scope_key,
               expected.oa_row_id, expected.business_batch_id,
               expected.external_batch_id as expected_external_batch_id,
               expected.relation_external_batch_id
        from expected
        cross join (select %s::text as tenant_id) tenant
        where expected.relation_external_batch_id is distinct from expected.external_batch_id
        order by expected.case_id
        limit %s
        """,
        "workbench_etc_relation_expected_owner_mismatch",
        "A uniquely identified submitted ETC batch is missing from, or disagrees with, its OA-owned formal relation.",
    ),
    (
        r"""
        /* check: workbench_etc_relation_unique_owner */
        with relation_markers as (
            select relation.case_id, marker.external_batch_id
            from app.workbench_pair_relations relation
            cross join lateral (
                values
                    (nullif(relation.amount_check->>'external_etc_batch_id', '')),
                    (nullif(relation.amount_check->>'etc_batch_id', '')),
                    (nullif(relation.special_metadata->>'external_etc_batch_id', '')),
                    (nullif(relation.special_metadata->>'etc_batch_id', '')),
                    (nullif(relation.special_metadata->'etc_batch_link'->>'external_etc_batch_id', '')),
                    (nullif(relation.special_metadata->'historical_etc_business_batch_migration'->>'external_etc_batch_id', ''))
            ) marker(external_batch_id)
            where relation.status = 'active'
              and marker.external_batch_id is not null
        ),
        relation_conflicts as (
            select case_id as subject_id, 'relation_marker_conflict'::text as mismatch_kind,
                   string_agg(distinct external_batch_id, ',' order by external_batch_id) as external_batch_ids
            from relation_markers
            group by case_id
            having count(distinct external_batch_id) > 1
        ),
        owner_conflicts as (
            select min(case_id) as subject_id, 'external_batch_owner_conflict'::text as mismatch_kind,
                   external_batch_id as external_batch_ids
            from relation_markers
            group by external_batch_id
            having count(distinct case_id) > 1
        )
        select conflict.subject_id, 'all'::text as scope_key,
               conflict.mismatch_kind, conflict.external_batch_ids
        from (
            select * from relation_conflicts
            union all
            select * from owner_conflicts
        ) conflict
        cross join (select %s::text as tenant_id) tenant
        order by conflict.mismatch_kind, conflict.subject_id
        limit %s
        """,
        "workbench_etc_relation_unique_owner_mismatch",
        "An active Workbench relation has conflicting ETC markers or an ETC batch has multiple active relation owners.",
    ),
)


_PROOF_QUERIES: tuple[tuple[str, str, str], ...] = (
    (
        _CANONICAL_CTES
        + r"""
        /* check: workbench_canonical_object_set */
        , mismatches as (
            select 'canonical_missing_projection'::text as mismatch_kind,
                   canonical.row_id as subject_id, canonical.expected_scope_key as scope_key,
                   canonical.source_kind as canonical_source_kind,
                   projected.source_kind as projected_source_kind
            from canonical_expected_scopes canonical
            left join projected_rows projected
              on projected.generation_scope = canonical.expected_scope_key
             and projected.row_id = canonical.row_id
             and projected.source_kind = canonical.source_kind
            where projected.row_id is null
            union all
            select 'projection_not_canonical', projected.row_id, projected.generation_scope,
                   canonical.source_kind, projected.source_kind
            from projected_rows projected
            left join canonical_expected_scopes canonical
              on canonical.expected_scope_key = projected.generation_scope
             and canonical.row_id = projected.row_id
             and canonical.source_kind = projected.source_kind
            where projected.generation_scope <> 'all'
              and projected.source_kind not in (
                  'etc_invoice_summary',
                  'etc_invoice',
                  'bank_flow_rule_batch_summary'
              )
              and canonical.row_id is null
        )
        select * from mismatches
        order by mismatch_kind, scope_key, subject_id
        limit %s
        """,
        "workbench_canonical_object_set_mismatch",
        "Workbench canonical OA, bank, or invoice objects do not equal active month-generation rows.",
    ),
    (
        r"""
        /* check: workbench_override_exception_fields */
        with active_relation_members as (
            select distinct member.row_id
            from app.workbench_pair_relations relation
            join lateral unnest(relation.row_ids) member(row_id) on true
            where relation.status = 'active'
        ),
        active_months as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        projected_representations as (
            select row.row_id, generation.scope_key, row.payload, 0 as representation_rank
            from active_months generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
            union all
            select coalesce(nullif(alias.value->>'id', ''), nullif(alias.value->>'row_id', '')),
                   generation.scope_key, alias.value, 1
            from active_months generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
            join lateral jsonb_each(
                case when jsonb_typeof(row.payload->'identity_alias_rows') = 'object'
                     then row.payload->'identity_alias_rows' else '{}'::jsonb end
            ) alias_bucket(key, value) on true
            join lateral jsonb_array_elements(
                case when jsonb_typeof(alias_bucket.value) = 'array'
                     then alias_bucket.value else '[]'::jsonb end
            ) alias(value) on true
        ),
        projected as (
            select distinct on (row_id) row_id, scope_key, payload
            from projected_representations
            where nullif(row_id, '') is not null
            order by row_id, representation_rank, scope_key desc
        ),
        override_mismatch as (
            select override.row_id as subject_id, coalesce(projected.scope_key, 'all') as scope_key,
                   'override'::text as mismatch_kind,
                   field.key as field_name, field.value as canonical_value,
                   projected.payload->field.key as projected_value
            from app.workbench_row_overrides override
            join lateral jsonb_each(
                case when jsonb_typeof(override.override_payload) = 'object'
                     then override.override_payload else '{}'::jsonb end
            ) field(key, value) on field.key in (
                'ignored', 'case_id', 'exception_case_id', 'handled_exception',
                'auto_close_suppressed', 'projection_version', 'projection_kind',
                'case_status', 'relation_status', 'relation_mode', 'scenario',
                'resolution', 'amount_summary', 'display_tags', 'oa_exemption'
            )
            left join projected on projected.row_id = override.row_id
            where override.status = 'active'
              and coalesce(override.override_payload->>'projection_kind', '') <> 'exception_case'
              and override.override_payload->'handled_exception' is distinct from 'true'::jsonb
              and override.override_payload->'ignored' is distinct from 'true'::jsonb
              and not (override.override_payload ? 'exception_case_id')
              and coalesce(override.override_payload#>>'{relation,tone}', '') <> 'danger'
              and jsonb_typeof(override.override_payload->'processed_exception_summary') is distinct from 'object'
              and not exists (
                  select 1
                  from active_relation_members relation_member
                  where relation_member.row_id = override.row_id
              )
              and projected.payload is not null
              and not (
                    field.value = 'null'::jsonb
                and projected.payload is not null
                and projected.payload->field.key is null
              )
              and projected.payload->field.key is distinct from field.value
        ),
        mismatches as (
            select * from override_mismatch
        )
        select * from mismatches
        order by mismatch_kind, subject_id, field_name
        limit %s
        """,
        "workbench_override_exception_fields_mismatch",
        "Workbench non-exception row-override fields do not equal canonical control facts.",
    ),
    (
        f"""
        /* check: workbench_generation_source_versions */
        with active_generations as (
            select distinct on (scope_key) generation_id, scope_key, source_versions
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        current_settings as (
            select case
                       when coalesce(settings_payload->'bank_transaction_tags'->>'version', '') ~ '^[0-9]+$'
                       then (settings_payload->'bank_transaction_tags'->>'version')::integer
                       else 1
                   end as bank_auto_tag_rules_version
            from app.app_settings
            where settings_key = 'app_settings'
            order by updated_at desc
            limit 1
        )
        select generation.generation_id as subject_id, generation.scope_key,
               generation.source_versions,
               {_MONTH_BUILDER} as expected_builder,
               {_FORMAL_RELATION_RULE} as expected_formal_relation_rule,
               {_OA_SYNC} as expected_oa_projection_sync,
               {_ATTACHMENT_PARSER} as expected_attachment_parser
        from active_generations generation
        left join current_settings settings on true
        where coalesce(generation.source_versions->>'builder', '') <> {_MONTH_BUILDER}
           or coalesce(generation.source_versions->>'workbench_formal_relation_rule_version', '') <> {_FORMAL_RELATION_RULE}
           or coalesce(generation.source_versions->>'oa_projection_sync_version', '') <> {_OA_SYNC}
           or coalesce(generation.source_versions->>'oa_attachment_invoice_parser_version', '')
              <> {_ATTACHMENT_PARSER}
           or case
                  when coalesce(generation.source_versions->>'bank_auto_tag_rules_version', '') ~ '^[0-9]+$'
                  then (generation.source_versions->>'bank_auto_tag_rules_version')::integer
                  else -1
              end
              <> coalesce(settings.bank_auto_tag_rules_version, 1)
        order by generation.scope_key
        limit %s
        """,
        "workbench_generation_source_versions_mismatch",
        "Workbench active generation source versions do not match current projection dependencies.",
    ),
    (
        r"""
        /* check: workbench_key_display_fields */
        with active_generations as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        projected as (
            select generation.scope_key, row.row_id, row.source_kind, row.amount,
                   row.counterparty_name, row.project_name, row.payload,
                   coalesce(
                       case
                           when row.source_kind in ('invoice', 'oa_attachment_invoice')
                            and coalesce(replace(row.payload->>'total_with_tax', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'total_with_tax', ',', '')::numeric
                       end,
                       row.amount,
                       case
                           when coalesce(replace(row.payload->>'amount_value', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'amount_value', ',', '')::numeric
                       end,
                       case
                           when coalesce(replace(row.payload->>'debit_amount', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'debit_amount', ',', '')::numeric
                       end,
                       case
                           when coalesce(replace(row.payload->>'credit_amount', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'credit_amount', ',', '')::numeric
                       end,
                       case
                           when coalesce(replace(row.payload->>'total_with_tax', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'total_with_tax', ',', '')::numeric
                       end,
                       case
                           when coalesce(replace(row.payload->>'amount', ',', ''), '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(row.payload->>'amount', ',', '')::numeric
                       end
                   ) as display_amount
            from active_generations generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
        ),
        oa_mismatch as (
            select oa.row_id as subject_id, projected.scope_key,
                   'oa'::text as object_type,
                   oa.amount::text as canonical_amount,
                   projected.display_amount::text as projected_amount,
                   oa.applicant as canonical_party, projected.payload->>'applicant' as projected_party,
                   oa.project_name as canonical_project, projected.project_name as projected_project
            from app.oa_applications oa
            join projected on projected.row_id = oa.row_id and projected.source_kind = 'oa'
            where abs(coalesce(oa.amount, 0) - coalesce(projected.display_amount, 0)) > 0.01
               or coalesce(oa.applicant, '') <> coalesce(projected.payload->>'applicant', '')
               or coalesce(oa.project_name, '') <> coalesce(projected.project_name, '')
        ),
        bank_mismatch as (
            select coalesce(bank.legacy_mongo_id, bank.id::text) as subject_id,
                   projected.scope_key, 'bank'::text as object_type,
                   abs(coalesce(bank.amount, 0))::text as canonical_amount,
                   projected.display_amount::text as projected_amount,
                   bank.counterparty_name_raw as canonical_party,
                   projected.counterparty_name as projected_party,
                   ''::text as canonical_project, projected.project_name as projected_project
            from app.bank_transactions bank
            join projected
              on projected.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
             and projected.source_kind = 'bank'
            where abs(
                    abs(coalesce(bank.amount, 0))
                    - coalesce(projected.display_amount, 0)
                  ) > 0.01
               or coalesce(bank.counterparty_name_raw, '') <> coalesce(projected.counterparty_name, '')
               or (
                    lower(coalesce(bank.txn_direction, '')) ~ '(out|debit|支出|付款)'
                    and case
                            when coalesce(replace(projected.payload->>'debit_amount', ',', ''), '')
                                 ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(projected.payload->>'debit_amount', ',', '')::numeric
                            else 0
                        end <= 0
                  )
               or (
                    lower(coalesce(bank.txn_direction, '')) ~ '(in|credit|收入|收款)'
                    and case
                            when coalesce(replace(projected.payload->>'credit_amount', ',', ''), '')
                                 ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(projected.payload->>'credit_amount', ',', '')::numeric
                            else 0
                        end <= 0
                  )
        ),
        invoice_mismatch as (
            select coalesce(invoice.legacy_mongo_id, invoice.id::text) as subject_id,
                   projected.scope_key, 'invoice'::text as object_type,
                   coalesce(invoice.total_with_tax, invoice.amount, 0)::text as canonical_amount,
                   projected.display_amount::text as projected_amount,
                   coalesce(invoice.counterparty_name, invoice.seller_name, invoice.buyer_name) as canonical_party,
                   projected.counterparty_name as projected_party,
                   ''::text as canonical_project, projected.project_name as projected_project
            from app.invoices invoice
            join projected
              on projected.row_id = coalesce(invoice.legacy_mongo_id, invoice.id::text)
             and projected.source_kind in ('invoice', 'oa_attachment_invoice')
            where abs(
                    coalesce(invoice.total_with_tax, invoice.amount, 0)
                    - coalesce(projected.display_amount, 0)
                  ) > 0.01
               or coalesce(invoice.invoice_type, '') <> coalesce(projected.payload->>'invoice_type', '')
               or coalesce(invoice.invoice_no, '')
                  <> coalesce(nullif(projected.payload->>'invoice_no', '—'), '')
               or coalesce(invoice.invoice_code, '')
                  <> coalesce(nullif(projected.payload->>'invoice_code', '—'), '')
               or coalesce(invoice.digital_invoice_no, '')
                  <> coalesce(nullif(projected.payload->>'digital_invoice_no', '—'), '')
               or coalesce(to_char(invoice.invoice_date, 'YYYY-MM-DD'), '')
                  <> left(coalesce(nullif(projected.payload->>'issue_date', '—'), ''), 10)
        ),
        mismatches as (
            select * from oa_mismatch
            union all select * from bank_mismatch
            union all select * from invoice_mismatch
        )
        select * from mismatches
        order by object_type, scope_key, subject_id
        limit %s
        """,
        "workbench_key_display_fields_mismatch",
        "Workbench critical OA, bank, or invoice display fields do not equal canonical facts.",
    ),
    (
        r"""
        /* check: workbench_etc_summary_details */
        with active_months as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        linked_invoice_sources as (
            select coalesce(
                       nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                       link.business_batch_id
                   ) as external_batch_id,
                   coalesce(
                       nullif(invoice.digital_invoice_no, ''),
                       nullif(invoice.invoice_no, ''),
                       coalesce(invoice.legacy_mongo_id, invoice.id::text)
                   ) as invoice_row_id,
                   abs(coalesce(invoice.total_with_tax, invoice.amount, 0))::numeric as amount
            from app.etc_batch_invoice_links link
            join app.invoices invoice on invoice.id = link.invoice_id and invoice.status <> 'deleted'
            left join app.etc_business_batches batch on batch.business_batch_id = link.business_batch_id
            where link.link_status = 'active'
        ),
        submitted_invoice_sources as (
            select coalesce(
                       nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                       submission.submission_batch_id
                   ) as external_batch_id,
                   coalesce(
                       nullif(invoice.digital_invoice_no, ''),
                       nullif(invoice.invoice_no, ''),
                       coalesce(invoice.legacy_mongo_id, invoice.id::text)
                   ) as invoice_row_id,
                   abs(coalesce(invoice.total_with_tax, invoice.amount, 0))::numeric as amount
            from app.etc_submission_batches submission
            join app.invoices invoice
              on coalesce(invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id', '')
                 in (
                    submission.submission_batch_id,
                    coalesce(nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                             submission.submission_batch_id)
                 )
             and invoice.status <> 'deleted'
            where submission.status in ('submitted_confirmed', 'submitted', 'closed')
        ),
        business_invoice_sources as (
            select coalesce(
                       nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                       batch.business_batch_id
                   ) as external_batch_id,
                   coalesce(
                       nullif(invoice.invoice_no, ''),
                       coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text)
                   ) as invoice_row_id,
                   abs(coalesce(invoice.total_with_tax, invoice.amount, 0))::numeric as amount
            from app.etc_business_batches batch
            join lateral jsonb_array_elements_text(
                case when jsonb_typeof(batch.raw_payload->'normalized_payload'->'invoice_ids') = 'array'
                     then batch.raw_payload->'normalized_payload'->'invoice_ids' else '[]'::jsonb end
            ) member(invoice_id) on true
            join app.etc_invoices invoice
              on invoice.etc_invoice_id = member.invoice_id
              or coalesce(invoice.legacy_mongo_id, '') = member.invoice_id
            where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
              and invoice.status <> 'deleted'
        ),
        canonical_detail as (
            select external_batch_id, invoice_row_id, max(amount) as amount
            from (
                select * from linked_invoice_sources
                union all select * from submitted_invoice_sources
                union all select * from business_invoice_sources
            ) source
            where nullif(external_batch_id, '') is not null
            group by external_batch_id, invoice_row_id
        ),
        canonical_summary as (
            select external_batch_id,
                   'etc-summary-' || coalesce(
                       nullif(trim(both '-' from regexp_replace(external_batch_id, '[^A-Za-z0-9_-]+', '-', 'g')), ''),
                       'unknown'
                   ) as summary_row_id,
                   count(*)::integer as invoice_count,
                   sum(amount)::numeric as total_amount
            from canonical_detail
            group by external_batch_id
        ),
        projected_summary as (
            select distinct on (row.row_id)
                   row.row_id as summary_row_id, generation.scope_key, row.payload
            from active_months generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
            where row.source_kind = 'etc_invoice_summary'
            order by row.row_id, generation.scope_key desc
        ),
        projected_detail_rows as (
            select distinct summary_member.row_id as summary_row_id,
                   coalesce(
                       nullif(detail_row.payload->>'digital_invoice_no', ''),
                       nullif(detail_row.payload->>'invoice_no', ''),
                       detail.row_id
                   ) as invoice_row_id,
                   coalesce(
                       case when coalesce(replace(detail_row.payload->>'total_with_tax', ',', ''), '')
                                      ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(detail_row.payload->>'total_with_tax', ',', '')::numeric end,
                       case when coalesce(replace(detail_row.payload->>'amount_value', ',', ''), '')
                                      ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(detail_row.payload->>'amount_value', ',', '')::numeric end,
                       detail_row.amount,
                       0
                   ) as amount
            from active_months generation
            join read_model.workbench_group_rows summary_member
              on summary_member.generation_id = generation.generation_id
             and summary_member.scope_key = generation.scope_key
             and summary_member.source_kind = 'etc_invoice_summary'
             and summary_member.row_role <> 'collapsed'
            join read_model.workbench_group_rows detail
              on detail.generation_id = summary_member.generation_id
             and detail.scope_key = summary_member.scope_key
             and detail.group_id = summary_member.group_id
             and detail.pane = 'invoice'
             and detail.row_role = 'collapsed'
             and detail.source_kind = 'etc_invoice'
            join read_model.workbench_rows detail_row
              on detail_row.generation_id = detail.generation_id
             and detail_row.scope_key = detail.scope_key
             and detail_row.row_id = detail.row_id
        ),
        projected_detail as (
            select summary_row_id, invoice_row_id, count(*)::integer as projected_count,
                   max(amount)::numeric as amount
            from projected_detail_rows
            group by summary_row_id, invoice_row_id
        ),
        summary_mismatch as (
            select coalesce(canonical.summary_row_id, projected.summary_row_id) as subject_id,
                   coalesce(projected.scope_key, 'all') as scope_key, 'summary'::text as mismatch_kind,
                   canonical.invoice_count as canonical_count,
                   case when coalesce(projected.payload->>'etc_invoice_count', '') ~ '^[0-9]+$'
                        then (projected.payload->>'etc_invoice_count')::integer else -1 end as projected_count,
                   canonical.total_amount::text as canonical_amount,
                   projected.payload->>'amount_value' as projected_amount
            from canonical_summary canonical
            full join projected_summary projected using (summary_row_id)
            where canonical.summary_row_id is null
               or projected.summary_row_id is null
               or canonical.invoice_count <> case
                    when coalesce(projected.payload->>'etc_invoice_count', '') ~ '^[0-9]+$'
                    then (projected.payload->>'etc_invoice_count')::integer else -1 end
               or abs(
                    coalesce(canonical.total_amount, 0)
                    - case
                        when coalesce(replace(projected.payload->>'amount_value', ',', ''), '')
                             ~ '^-?[0-9]+([.][0-9]+)?$'
                        then replace(projected.payload->>'amount_value', ',', '')::numeric
                        else 0
                      end
                  ) > 0.01
        ),
        detail_mismatch as (
            select coalesce(canonical_summary.summary_row_id, projected.summary_row_id) as subject_id,
                   coalesce(projected_summary.scope_key, 'all') as scope_key, 'detail'::text as mismatch_kind,
                   case when canonical.invoice_row_id is null then 0 else 1 end as canonical_count,
                   coalesce(projected.projected_count, 0) as projected_count,
                   canonical.amount::text as canonical_amount, projected.amount::text as projected_amount
            from canonical_detail canonical
            join canonical_summary using (external_batch_id)
            full join projected_detail projected
              on projected.summary_row_id = canonical_summary.summary_row_id
             and projected.invoice_row_id = canonical.invoice_row_id
            left join projected_summary on projected_summary.summary_row_id = coalesce(
                canonical_summary.summary_row_id,
                projected.summary_row_id
            )
            where canonical.invoice_row_id is null
               or projected.invoice_row_id is null
               or projected.projected_count <> 1
               or abs(coalesce(canonical.amount, 0) - coalesce(projected.amount, 0)) > 0.01
        ),
        mismatches as (
            select * from summary_mismatch
            union all select * from detail_mismatch
        )
        select * from mismatches
        order by mismatch_kind, subject_id
        limit %s
        """,
        "workbench_etc_summary_details_mismatch",
        "Workbench ETC summary rows or their detail members do not equal canonical ETC batch invoices.",
    ),
    (
        r"""
        /* check: workbench_summary_counts */
        with active_generations as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        recalculated as (
            select generation.generation_id, generation.scope_key,
                   count(distinct group_row.group_id) filter (where group_row.zone = 'paired')::integer as paired_count,
                   count(distinct group_row.group_id) filter (where group_row.zone = 'unpaired')::integer as unpaired_count,
                   count(distinct (member.pane, member.row_id)) filter (
                       where member.row_role <> 'summary' and member.pane = 'oa'
                   )::integer as oa_count,
                   count(distinct (member.pane, member.row_id)) filter (
                       where member.row_role <> 'summary' and member.pane = 'bank'
                   )::integer as bank_count,
                   count(distinct (member.pane, member.row_id)) filter (
                       where member.row_role <> 'summary' and member.pane = 'invoice'
                   )::integer as invoice_count
            from active_generations generation
            left join read_model.workbench_groups group_row
              on group_row.generation_id = generation.generation_id
             and group_row.scope_key = generation.scope_key
            left join read_model.workbench_group_rows member
              on member.generation_id = group_row.generation_id
             and member.scope_key = group_row.scope_key
             and member.zone = group_row.zone
             and member.group_id = group_row.group_id
            group by generation.generation_id, generation.scope_key
        )
        select recalculated.generation_id as subject_id, recalculated.scope_key,
               summary.summary as stored_summary,
               recalculated.paired_count, recalculated.unpaired_count,
               recalculated.oa_count, recalculated.bank_count, recalculated.invoice_count
        from recalculated
        left join read_model.workbench_summary summary
          on summary.generation_id = recalculated.generation_id
         and summary.scope_key = recalculated.scope_key
        where summary.generation_id is null
           or case when coalesce(summary.summary->>'paired_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'paired_count')::integer else -1 end <> recalculated.paired_count
           or case when coalesce(summary.summary->>'unpaired_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'unpaired_count')::integer else -1 end <> recalculated.unpaired_count
           or case when coalesce(summary.summary->>'oa_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'oa_count')::integer else -1 end <> recalculated.oa_count
           or case when coalesce(summary.summary->>'bank_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'bank_count')::integer else -1 end <> recalculated.bank_count
           or case when coalesce(summary.summary->>'invoice_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'invoice_count')::integer else -1 end <> recalculated.invoice_count
        order by recalculated.scope_key
        limit %s
        """,
        "workbench_summary_count_mismatch",
        "Workbench summary counts do not equal active generation groups and members.",
    ),
    (
        r"""
        /* check: workbench_generation_counts */
        with active_generations as (
            select distinct on (scope_key)
                   generation_id, scope_key, row_count, group_count, summary_count
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        )
        select generation.generation_id as subject_id, generation.scope_key,
               generation.row_count as stored_row_count,
               (select count(*) from read_model.workbench_rows row
                where row.generation_id = generation.generation_id
                  and row.scope_key = generation.scope_key) as actual_row_count,
               generation.group_count as stored_group_count,
               (select count(*) from read_model.workbench_groups group_row
                where group_row.generation_id = generation.generation_id
                  and group_row.scope_key = generation.scope_key) as actual_group_count,
               generation.summary_count as stored_summary_count,
               (select count(*) from read_model.workbench_summary summary
                where summary.generation_id = generation.generation_id
                  and summary.scope_key = generation.scope_key) as actual_summary_count
        from active_generations generation
        where generation.row_count <> (
                  select count(*) from read_model.workbench_rows row
                  where row.generation_id = generation.generation_id
                    and row.scope_key = generation.scope_key
              )
           or generation.group_count <> (
                  select count(*) from read_model.workbench_groups group_row
                  where group_row.generation_id = generation.generation_id
                    and group_row.scope_key = generation.scope_key
              )
           or generation.summary_count <> (
                  select count(*) from read_model.workbench_summary summary
                  where summary.generation_id = generation.generation_id
                    and summary.scope_key = generation.scope_key
              )
        order by generation.scope_key
        limit %s
        """,
        "workbench_generation_count_mismatch",
        "Workbench active generation counts do not equal their stored rows, groups, and summary.",
    ),
)
