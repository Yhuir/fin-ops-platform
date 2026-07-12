from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_MONTH_BUILDER = _sql_text(WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION)
_MATCHING_RULES = _sql_text(WORKBENCH_MATCHING_RULES_VERSION)
_OA_SYNC = _sql_text(OA_PROJECTION_SYNC_VERSION)
_ATTACHMENT_PARSER = _sql_text(attachment_invoice_cache_parser_version())


def workbench_projection_integrity_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for sql, code, message in _PROOF_QUERIES:
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
    select member.row_id, relation.row_types[member.ordinality] as row_type
    from app.workbench_pair_relations relation
    join lateral unnest(relation.row_ids) with ordinality member(row_id, ordinality) on true
    where relation.status = 'active'
),
claimed_bank as (
    select bank_transaction_id as row_id
    from app.bank_transaction_relation_claims
    where status = 'active'
      and owner_type = 'oa_pending_payment_relation'
),
submitted_etc_invoice_ids as (
    select invoice_id
    from app.etc_batch_invoice_links
    where link_status = 'active'
),
canonical_oa as (
    select oa.row_id,
           to_char(oa.scope_month, 'YYYY-MM') as scope_key,
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
              where member.row_id = oa.row_id and member.row_type = 'oa'
         )
      )
      and oa.scope_month is not null
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
      and (
            not exists (
                select 1 from claimed_bank claim
                where claim.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
            )
         or exists (
                select 1 from active_relation_members member
                where member.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
                  and member.row_type in ('bank', 'bank_transaction')
            )
      )
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
projected_rows as (
    select generation.scope_key as generation_scope,
           row.row_id, row.source_kind,
           row.amount, coalesce(row.counterparty_name, '') as counterparty_name,
           coalesce(row.project_name, '') as project_name,
           row.payload
    from active_generations generation
    join read_model.workbench_rows row
      on row.generation_id = generation.generation_id
     and row.scope_key = generation.scope_key
)
"""


_PROOF_QUERIES: tuple[tuple[str, str, str], ...] = (
    (
        _CANONICAL_CTES
        + r"""
        /* check: workbench_canonical_object_set */
        , mismatches as (
            select 'canonical_missing_projection'::text as mismatch_kind,
                   canonical.row_id as subject_id, canonical.scope_key,
                   canonical.source_kind as canonical_source_kind,
                   projected.source_kind as projected_source_kind
            from canonical_rows canonical
            left join projected_rows projected
              on projected.generation_scope = canonical.scope_key
             and projected.row_id = canonical.row_id
             and projected.source_kind = canonical.source_kind
            where projected.row_id is null
            union all
            select 'projection_not_canonical', projected.row_id, projected.generation_scope,
                   canonical.source_kind, projected.source_kind
            from projected_rows projected
            left join canonical_rows canonical
              on canonical.scope_key = projected.generation_scope
             and canonical.row_id = projected.row_id
             and canonical.source_kind = projected.source_kind
            where projected.generation_scope <> 'all'
              and projected.source_kind <> 'etc_invoice_summary'
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
        with active_months as (
            select distinct on (scope_key) generation_id, scope_key
            from read_model.workbench_generations
            where tenant_id = %s
              and status = 'active'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, activated_at desc nulls last, updated_at desc
        ),
        projected as (
            select distinct on (row.row_id) row.row_id, generation.scope_key, row.payload
            from active_months generation
            join read_model.workbench_rows row
              on row.generation_id = generation.generation_id
             and row.scope_key = generation.scope_key
            order by row.row_id, generation.scope_key desc
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
              and projected.payload->field.key is distinct from field.value
        ),
        exception_members as (
            select exception.case_id, exception.status,
                   member.row_id
            from app.workbench_exception_cases exception
            join lateral unnest(exception.row_ids) member(row_id) on true
            where exception.status in ('open', 'ignored', 'reopened', 'legacy_confirmed', 'confirmed')
              and not exists (
                  select 1 from app.workbench_row_overrides override
                  where override.row_id = member.row_id and override.status = 'active'
              )
        ),
        exception_mismatch as (
            select member.row_id as subject_id, coalesce(projected.scope_key, 'all') as scope_key,
                   'exception'::text as mismatch_kind,
                   'case/status'::text as field_name,
                   jsonb_build_object('case_id', member.case_id, 'status', member.status) as canonical_value,
                   projected.payload as projected_value
            from exception_members member
            left join projected on projected.row_id = member.row_id
            where projected.row_id is null
               or coalesce(projected.payload->>'case_id', '') <> member.case_id
               or coalesce(projected.payload->>'exception_case_id', '') <> member.case_id
               or coalesce(projected.payload->>'case_status', '') <> member.status
               or coalesce(projected.payload->'ignored' = 'true'::jsonb, false) <> (member.status = 'ignored')
               or coalesce(projected.payload->'handled_exception' = 'true'::jsonb, false)
                  <> (member.status <> 'ignored')
        ),
        mismatches as (
            select * from override_mismatch
            union all select * from exception_mismatch
        )
        select * from mismatches
        order by mismatch_kind, subject_id, field_name
        limit %s
        """,
        "workbench_override_exception_fields_mismatch",
        "Workbench ignored, handled-exception, or row-override fields do not equal canonical control facts.",
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
               {_MATCHING_RULES} as expected_matching_rules,
               {_OA_SYNC} as expected_oa_projection_sync,
               {_ATTACHMENT_PARSER} as expected_attachment_parser
        from active_generations generation
        left join current_settings settings on true
        where coalesce(generation.source_versions->>'builder', '') <> {_MONTH_BUILDER}
           or coalesce(generation.source_versions->>'workbench_matching_rules_version', '') <> {_MATCHING_RULES}
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
                   abs(coalesce(invoice.total_with_tax, invoice.amount, 0))::text as canonical_amount,
                   projected.display_amount::text as projected_amount,
                   coalesce(invoice.counterparty_name, invoice.seller_name, invoice.buyer_name) as canonical_party,
                   projected.counterparty_name as projected_party,
                   ''::text as canonical_project, projected.project_name as projected_project
            from app.invoices invoice
            join projected
              on projected.row_id = coalesce(invoice.legacy_mongo_id, invoice.id::text)
             and projected.source_kind in ('invoice', 'oa_attachment_invoice')
            where abs(
                    abs(coalesce(invoice.total_with_tax, invoice.amount, 0))
                    - coalesce(projected.display_amount, 0)
                  ) > 0.01
               or coalesce(invoice.invoice_type, '') <> coalesce(projected.payload->>'invoice_type', '')
               or coalesce(invoice.invoice_no, '') <> coalesce(projected.payload->>'invoice_no', '')
               or coalesce(invoice.invoice_code, '') <> coalesce(projected.payload->>'invoice_code', '')
               or coalesce(invoice.digital_invoice_no, '') <> coalesce(projected.payload->>'digital_invoice_no', '')
               or coalesce(to_char(invoice.invoice_date, 'YYYY-MM-DD'), '')
                  <> left(coalesce(projected.payload->>'issue_date', ''), 10)
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
                   coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_row_id,
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
                   coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_row_id,
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
                   coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text) as invoice_row_id,
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
            select summary.summary_row_id,
                   coalesce(nullif(detail.value->>'id', ''), nullif(detail.value->>'row_id', '')) as invoice_row_id,
                   coalesce(
                       case when coalesce(replace(detail.value->>'amount_value', ',', ''), '')
                                      ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(detail.value->>'amount_value', ',', '')::numeric end,
                       case when coalesce(replace(detail.value->>'total_with_tax', ',', ''), '')
                                      ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(detail.value->>'total_with_tax', ',', '')::numeric end,
                       case when coalesce(replace(detail.value->>'amount', ',', ''), '')
                                      ~ '^-?[0-9]+([.][0-9]+)?$'
                            then replace(detail.value->>'amount', ',', '')::numeric end,
                       0
                   ) as amount
            from projected_summary summary
            join lateral jsonb_array_elements(
                case when jsonb_typeof(summary.payload->'etc_invoice_detail_rows') = 'array'
                     then summary.payload->'etc_invoice_detail_rows' else '[]'::jsonb end
            ) detail(value) on true
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
                   count(distinct group_row.group_id) filter (where group_row.zone = 'open')::integer as open_count,
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
               recalculated.paired_count, recalculated.open_count,
               recalculated.oa_count, recalculated.bank_count, recalculated.invoice_count
        from recalculated
        left join read_model.workbench_summary summary
          on summary.generation_id = recalculated.generation_id
         and summary.scope_key = recalculated.scope_key
        where summary.generation_id is null
           or case when coalesce(summary.summary->>'paired_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'paired_count')::integer else -1 end <> recalculated.paired_count
           or case when coalesce(summary.summary->>'open_count', '') ~ '^[0-9]+$'
                   then (summary.summary->>'open_count')::integer else -1 end <> recalculated.open_count
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
