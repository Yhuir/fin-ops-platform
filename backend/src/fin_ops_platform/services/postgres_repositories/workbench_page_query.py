from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar

from fin_ops_platform.services.postgres_repositories.common import (
    int_value,
    month_start,
    text,
    text_list,
)
from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_hydration import (
    PostgresWorkbenchPageHydrationRepository,
    pending_oa_application_date_sql,
    pending_oa_application_time_sql,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    OA_EXTERNAL_SOURCE_ID_FIELD_NAMES,
)
from fin_ops_platform.services.workbench_filter_options import (
    WORKBENCH_FILTER_MISSING_VALUE,
    WORKBENCH_FILTER_PLACEHOLDERS,
    normalize_workbench_column_filters,
    normalize_workbench_filter_option_target,
    normalize_workbench_scope_key,
    normalize_workbench_time_filters,
    workbench_time_range,
)
from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
    is_workbench_data_integrity_query_error,
    is_transient_postgres_query_error,
)
from fin_ops_platform.services.workbench_anomaly_contract import (
    AMOUNT_EXCEPTION_CODES,
    EXCEPTION_VIEWS,
)
from fin_ops_platform.services.workbench_page_cursor import (
    WorkbenchPageCursor,
    WorkbenchPageCursorError,
    decode_workbench_page_cursor,
    encode_workbench_page_cursor,
    workbench_query_hash,
)


T = TypeVar("T")
WORKBENCH_DIRECT_QUERY_TIMEOUT_SECONDS = 5
WORKBENCH_GROUP_PAGE_SIZE = 10
WORKBENCH_GROUP_PAGE_SIZE_MAX = 200
WORKBENCH_FILTER_OPTION_PAGE_SIZE = 100
WORKBENCH_SEARCH_QUERY_MAX_LENGTH = 200
WORKBENCH_SOURCE_KINDS = frozenset(
    {
        "oa",
        "bank",
        "bank_transaction",
        "invoice",
        "manual_invoice_import",
        "oa_attachment_invoice",
        "etc_invoice_summary",
    }
)

_AMOUNT_EXCEPTION_COUNT_COLUMNS_SQL = ",\n                    ".join(
    "count(*) filter (where anomaly.exception_code = "
    f"'{code}')::bigint as exception_count_{code}"
    for code in AMOUNT_EXCEPTION_CODES
)
_DEFAULT_AMOUNT_EXCEPTION_CODE_SQL = "\n".join(
    f"when counts.exception_count_{code} > 0 then '{code}'"
    for code in AMOUNT_EXCEPTION_CODES
)

_COMPOSITE_FILTER_OPTION_GROUPS = {
    ("bank", "amount"): (("direction", "收支方向"), ("account", "银行账户"), ("bankTag", "流水标签")),
    ("oa", "applicant"): (("oaType", "OA 类型"), ("workflow", "流程状态"), ("applicant", "申请人")),
    ("oa", "projectName"): (("expenseType", "OA 费用类型"), ("project", "项目名称")),
}


def _grouped_filter_values(values: list[str], prefix: str) -> list[str]:
    marker = f"{prefix}:"
    return [value[len(marker) :] for value in values if value.startswith(marker)]


def _grouped_filter_token(prefix: str, value: object) -> str:
    return f"{prefix}:{str(value or '').strip()}"


def _literal_ilike_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _anomaly_oa_external_alias_values_sql(source_payload: str) -> str:
    return ",\n                ".join(
        "nullif(btrim("
        f"{source_payload}{path}->>'{field_name}'"
        "), '')"
        for path in ("", "->'detail_fields'", "->'summary_fields'", "->'metadata'")
        for field_name in OA_EXTERNAL_SOURCE_ID_FIELD_NAMES
    )


def _anomaly_invoice_source_links_sql(invoice_alias: str) -> str:
    return f"""
        case
            when jsonb_typeof({invoice_alias}.source_links) = 'array'
                then {invoice_alias}.source_links
            when jsonb_typeof({invoice_alias}.raw_payload->'source_links') = 'array'
                then {invoice_alias}.raw_payload->'source_links'
            when jsonb_typeof(
                {invoice_alias}.raw_payload->'normalized_payload'->'source_links'
            ) = 'array'
                then {invoice_alias}.raw_payload->'normalized_payload'->'source_links'
            else '[]'::jsonb
        end
    """


_COMPLETED_OA_SQL = """
(
    oa.workflow_status is null
    or oa.workflow_status = ''
    or oa.workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
)
"""

_VISIBLE_INVOICE_SQL = """
invoice.status <> 'deleted'
and coalesce(invoice.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
and coalesce(invoice.raw_payload->'normalized_payload'->>'workbench_visibility', 'visible')
    <> 'hidden_after_etc_submission'
and coalesce(invoice.raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
and not exists (
    select 1
    from app.etc_batch_invoice_links link
    where link.link_status = 'active'
      and link.invoice_id = invoice.id
)
and not exists (
    select 1
    from app.etc_invoices etc_invoice
    left join app.etc_business_batches batch
      on batch.business_batch_id = etc_invoice.business_batch_id
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
            batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
            or (
                etc_invoice.status = 'submitted'
                and coalesce(batch.status, '') <> 'deleted'
            )
          )
)
"""


def _visible_invoice_sql(invoice_alias: str) -> str:
    protected = _VISIBLE_INVOICE_SQL.replace("etc_invoice.", "__ETC_INVOICE__.")
    return protected.replace("invoice.", f"{invoice_alias}.").replace(
        "__ETC_INVOICE__.", "etc_invoice."
    )

_RELATION_EXTERNAL_BATCH_SQL = """
coalesce(
    nullif(relation.amount_check->>'external_etc_batch_id', ''),
    nullif(relation.amount_check->>'etc_batch_id', ''),
    nullif(relation.special_metadata->>'external_etc_batch_id', ''),
    nullif(relation.special_metadata->>'etc_batch_id', ''),
    nullif(relation.special_metadata#>>'{etc_batch_link,external_etc_batch_id}', ''),
    nullif(relation.special_metadata#>>'{etc_batch_link,etc_batch_id}', ''),
    nullif(relation.special_metadata#>>'{historical_etc_business_batch_migration,external_etc_batch_id}', ''),
    nullif(relation.special_metadata#>>'{historical_etc_business_batch_migration,etc_batch_id}', '')
)
"""


# Keep submitted ETC summary identity resolution shared by the bounded page
# query and the bounded singleton-detail lookup.  A detail key must resolve to
# the exact same authoritative batch id, month, and summary row as the list.
_ETC_SUMMARY_IDENTITY_CTES = """
etc_summary_source_keys as materialized (
    select
        coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            batch.business_batch_id
        ) as external_batch_id,
        batch.scope_month,
        batch.updated_at
    from app.etc_business_batches batch
    where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
      and exists (
          select 1
          from app.etc_invoices invoice
          where invoice.business_batch_id = batch.business_batch_id
            and invoice.status <> 'deleted'
      )
    union all
    select
        coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            link.business_batch_id
        ),
        coalesce(batch.scope_month, invoice.invoice_month),
        greatest(link.updated_at, batch.updated_at, invoice.updated_at)
    from app.etc_batch_invoice_links link
    join app.invoices invoice on invoice.id = link.invoice_id
    left join app.etc_business_batches batch
      on batch.business_batch_id = link.business_batch_id
    where link.link_status = 'active'
      and invoice.status <> 'deleted'
    union all
    select
        coalesce(
            nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
            submission.submission_batch_id
        ),
        coalesce(submission.scope_month, invoice.invoice_month),
        greatest(submission.updated_at, invoice.updated_at)
    from app.etc_submission_batches submission
    join app.invoices invoice
      on submission.submission_batch_id = coalesce(
          invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id', ''
      )
      or coalesce(
          nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
          submission.submission_batch_id
      ) = coalesce(
          invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id', ''
      )
    where submission.status in ('submitted_confirmed', 'submitted', 'closed')
      and invoice.status <> 'deleted'
      and (
          invoice.workbench_visibility = 'hidden_after_etc_submission'
          or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
              = 'hidden_after_etc_submission'
          or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
              = 'submitted'
      )
),
etc_summary_keys as materialized (
    select distinct on (source.external_batch_id)
        'etc-summary-' || regexp_replace(
            source.external_batch_id,
            '[^A-Za-z0-9_-]+',
            '-',
            'g'
        ) as row_id,
        source.external_batch_id,
        source.scope_month,
        source.updated_at
    from etc_summary_source_keys source
    where nullif(source.external_batch_id, '') is not null
      and source.scope_month is not null
    order by source.external_batch_id, source.updated_at desc nulls last
),
etc_summary_identity_conflicts as materialized (
    select summary.row_id
    from etc_summary_keys summary
    group by summary.row_id
    having count(distinct summary.external_batch_id) > 1
),
etc_summary_identity_guard as materialized (
    select 1 / case when count(*) = 0 then 1 else 0 end as guard
    from etc_summary_identity_conflicts
)
"""


# The page query deliberately starts with the requested source scope.  Active
# relations are admitted only when their own month or one typed member belongs
# to that scope.  Only then are the other members of those relations admitted.
# This avoids the old all-history canonical CTE and, importantly, never matches
# a relation member on row_id without row_type.
_SCOPED_CANONICAL_GROUPS_CTE = f"""
requested_scope as (
    select
        %s::text as scope_key,
        case when %s::text = 'all' then null else %s::date end as scope_month,
        %s::text as tenant_id
),
requested_settings as materialized (
    select coalesce((
        select settings.settings_payload
        from app.app_settings settings
        where settings.settings_key = 'app_settings'
        limit 1
    ), '{{}}'::jsonb) as settings_payload
),
visible_invoice_facts as materialized (
    select
        coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
        case when exists (
            select 1
            from jsonb_array_elements(
                case when jsonb_typeof(invoice.source_links) = 'array'
                     then invoice.source_links else '[]'::jsonb end
            ) source_link
            where coalesce(
                source_link->>'source_type', source_link->>'type', source_link->>'source'
            ) = 'oa_attachment_invoice'
        ) then 'oa_attachment_invoice'
        when exists (
            select 1
            from jsonb_array_elements(
                case
                    when jsonb_typeof(invoice.source_links) = 'array'
                        then invoice.source_links
                    when jsonb_typeof(invoice.raw_payload->'source_links') = 'array'
                        then invoice.raw_payload->'source_links'
                    else '[]'::jsonb
                end
            ) source_link
            where coalesce(
                source_link->>'source_type', source_link->>'type', source_link->>'source'
            ) = 'manual_invoice_import'
        ) then 'manual_invoice_import'
        else 'invoice' end as source_kind,
        invoice.invoice_month,
        invoice.invoice_date,
        invoice.updated_at,
        invoice.seller_name,
        invoice.buyer_name,
        invoice.invoice_type,
        invoice.amount,
        invoice.total_with_tax,
        case
            when lower(replace(replace(coalesce(invoice.invoice_type, ''), '-', '_'), ' ', '_')) in
                 ('output', 'output_invoice', 'out_invoice', 'sales', 'sale', 'sales_invoice', 'receivable')
                 or coalesce(invoice.invoice_type, '') like '%%销项%%'
                then 'receipt'
            when lower(replace(replace(coalesce(invoice.invoice_type, ''), '-', '_'), ' ', '_')) in
                 ('input', 'input_invoice', 'in_invoice', 'purchase', 'purchase_invoice', 'payable')
                 or coalesce(invoice.invoice_type, '') like '%%进项%%'
                 or exists (
                    select 1
                    from jsonb_array_elements(
                        case when jsonb_typeof(invoice.source_links) = 'array'
                             then invoice.source_links else '[]'::jsonb end
                    ) source_link(value)
                    where coalesce(
                        source_link.value->>'source_type',
                        source_link.value->>'type',
                        source_link.value->>'source'
                    ) = 'oa_attachment_invoice'
                 )
                then 'payment'
            else null
        end as invoice_direction,
        {_anomaly_invoice_source_links_sql('invoice')} as invoice_source_links,
        case
            when nullif(invoice.digital_invoice_no, '') is not null
                then 'digital:' || invoice.digital_invoice_no
            when nullif(invoice.invoice_code, '') is not null
             and nullif(invoice.invoice_no, '') is not null
                then 'code-no:' || invoice.invoice_code || ':' || invoice.invoice_no
            else 'row:' || coalesce(invoice.legacy_mongo_id, invoice.id::text)
        end as hard_identity
    from app.invoices invoice
    where {_VISIBLE_INVOICE_SQL}
),
{_ETC_SUMMARY_IDENTITY_CTES},
scoped_source_keys as materialized (
    select 'oa'::text as row_type, oa.row_id
    from requested_scope scope
    join app.oa_applications oa
      on scope.scope_key = 'all'
      or coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date) = scope.scope_month
    where oa.status <> 'deleted'
      and {_COMPLETED_OA_SQL}
    union
    select 'oa'::text, admission.oa_id
    from requested_scope scope
    join app.oa_pending_payment_admissions admission
      on scope.scope_key = 'all' or admission.scope_key = scope.scope_key
    where admission.tenant_id = scope.tenant_id
      and admission.workflow_status = 'in_progress'
    union
    select 'bank'::text, coalesce(bank.legacy_mongo_id, bank.id::text)
    from requested_scope scope
    join app.bank_transactions bank
      on scope.scope_key = 'all' or bank.txn_month = scope.scope_month
    where bank.status <> 'deleted'
    union
    select 'invoice'::text, invoice.row_id
    from requested_scope scope
    join visible_invoice_facts invoice
      on scope.scope_key = 'all' or invoice.invoice_month = scope.scope_month
    union
    select 'invoice'::text, summary.row_id
    from requested_scope scope
    join etc_summary_keys summary
      on scope.scope_key = 'all' or summary.scope_month = scope.scope_month
    cross join etc_summary_identity_guard summary_guard
    where summary_guard.guard = 1
),
all_active_relations as materialized (
    select
        relation.id,
        relation.case_id,
        relation.relation_mode,
        relation.month_scope,
        relation.row_ids,
        relation.row_types,
        relation.amount_check,
        relation.special_metadata,
        relation.raw_payload,
        relation.updated_at,
        {_RELATION_EXTERNAL_BATCH_SQL} as external_etc_batch_id
    from app.workbench_pair_relations relation
    cross join requested_scope scope
    where relation.status = 'active'
      and (
          scope.scope_key = 'all'
          or relation.month_scope = scope.scope_month
          or relation.row_ids && array(
              select source_key.row_id
              from scoped_source_keys source_key
          )::text[]
      )
),
invalid_relation_shapes as materialized (
    select relation.id
    from all_active_relations relation
    where coalesce(cardinality(relation.row_ids), -1) = 0
       or coalesce(cardinality(relation.row_ids), -1)
            <> coalesce(cardinality(relation.row_types), -2)
       or exists (
            select 1
            from unnest(relation.row_ids, relation.row_types)
                as member(row_id, row_type)
            where nullif(btrim(member.row_id), '') is null
               or case lower(nullif(btrim(member.row_type), ''))
                    when 'oa' then 'oa'
                    when 'oa_application' then 'oa'
                    when 'bank' then 'bank'
                    when 'bank_transaction' then 'bank'
                    when 'invoice' then 'invoice'
                    when 'invoice_record' then 'invoice'
                    when 'formal_invoice' then 'invoice'
                    when 'input' then 'invoice'
                    when 'input_invoice' then 'invoice'
                    when 'output' then 'invoice'
                    when 'output_invoice' then 'invoice'
                    when 'etc_summary' then 'invoice'
                    else null
                  end is null
       )
       or exists (
            select 1
            from unnest(relation.row_ids, relation.row_types)
                as member(row_id, row_type)
            group by
                member.row_id,
                case lower(member.row_type)
                    when 'oa_application' then 'oa'
                    when 'bank_transaction' then 'bank'
                    when 'invoice_record' then 'invoice'
                    when 'formal_invoice' then 'invoice'
                    when 'input' then 'invoice'
                    when 'input_invoice' then 'invoice'
                    when 'output' then 'invoice'
                    when 'output_invoice' then 'invoice'
                    when 'etc_summary' then 'invoice'
                    else lower(member.row_type)
                end
            having count(*) > 1
       )
),
relation_shape_guard as materialized (
    select 1 / case when count(*) = 0 then 1 else 0 end as guard
    from invalid_relation_shapes
),
all_active_relation_members as materialized (
    select
        relation.id as relation_id,
        relation.case_id,
        member.ordinality,
        member.row_id,
        case lower(member.row_type)
            when 'oa_application' then 'oa'
            when 'bank_transaction' then 'bank'
            when 'invoice_record' then 'invoice'
            when 'formal_invoice' then 'invoice'
            when 'input' then 'invoice'
            when 'input_invoice' then 'invoice'
            when 'output' then 'invoice'
            when 'output_invoice' then 'invoice'
            when 'etc_summary' then 'invoice'
            else lower(member.row_type)
        end as row_type
    from all_active_relations relation
    cross join relation_shape_guard
    cross join lateral unnest(relation.row_ids, relation.row_types)
      with ordinality as member(row_id, row_type, ordinality)
    where relation_shape_guard.guard = 1
),
all_active_relation_member_rollups as materialized (
    select
        member.relation_id,
        array_agg(member.row_type order by member.ordinality)::text[]
            as normalized_row_types
    from all_active_relation_members member
    group by member.relation_id
),
scoped_relation_ids as materialized (
    select relation.id
    from all_active_relations relation
    cross join requested_scope scope
    where scope.scope_key = 'all'
       or relation.month_scope = scope.scope_month
       or exists (
            select 1
            from all_active_relation_members member
            join scoped_source_keys source_key
              on source_key.row_type = member.row_type
             and source_key.row_id = member.row_id
            where member.relation_id = relation.id
       )
),
scoped_relations as materialized (
    select
        relation.*,
        member_rollup.normalized_row_types
    from all_active_relations relation
    join scoped_relation_ids selected on selected.id = relation.id
    join all_active_relation_member_rollups member_rollup
      on member_rollup.relation_id = relation.id
),
needed_keys as materialized (
    select row_type, row_id from scoped_source_keys
    union
    select member.row_type, member.row_id
    from all_active_relation_members member
    join scoped_relation_ids selected on selected.id = member.relation_id
),
oa_candidate_facts as materialized (
    select
        oa.row_id,
        'oa'::text as pane,
        'oa'::text as source_kind,
        coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date) as scope_month,
        oa.application_date as sort_date,
        oa.updated_at,
        'completed'::text as workflow_status,
        jsonb_strip_nulls(jsonb_build_object(
            'applicant', oa.applicant,
            'applicationTime', oa.application_date::text,
            'projectName', oa.project_name,
            'applicationType', case lower(coalesce(
                oa.normalized_payload->>'apply_type',
                oa.normalized_payload#>>'{{detail_fields,申请类型}}',
                ''
            ))
                when 'payment_request' then '支付申请'
                when '供应商付款申请' then '支付申请'
                when 'expense_claim' then '日常报销'
                else coalesce(
                    oa.normalized_payload->>'apply_type',
                    oa.normalized_payload#>>'{{detail_fields,申请类型}}'
                )
            end,
            'expenseType', nullif(btrim(oa.normalized_payload->>'expense_type'), ''),
            'counterparty', coalesce(
                oa.normalized_payload->>'counterparty_name',
                oa.normalized_payload#>>'{{detail_fields,往来单位}}'
            ),
            'reconciliationStatus', '待关联',
            'workflowStatus', 'completed'
        )) as column_values,
        null::text as external_etc_batch_id,
        case when jsonb_typeof(oa.normalized_payload->'expense_items') = 'array'
             then oa.normalized_payload->'expense_items'
             else '[]'::jsonb end as oa_expense_items,
        case when jsonb_typeof(oa.normalized_payload->'source_aliases') = 'array'
             then oa.normalized_payload->'source_aliases'
             else '[]'::jsonb end as oa_source_aliases,
        array_remove(array[
            oa.row_id,
            oa.normalized_payload->>'oa_row_id',
            oa.normalized_payload->>'oa_id',
            oa.normalized_payload->>'source_oa_row_id',
            oa.normalized_payload->>'object_identity_key'
        ]::text[], null) as oa_exact_identity_aliases,
        array_remove(array[
            {_anomaly_oa_external_alias_values_sql('oa.normalized_payload')}
        ]::text[], null) as oa_external_identity_aliases,
        coalesce(
            oa.normalized_payload->>'apply_type',
            oa.normalized_payload->>'application_type',
            oa.normalized_payload->>'form_type'
        ) as oa_apply_type,
        oa.amount as oa_amount,
        null::numeric as bank_amount,
        null::text as bank_direction,
        null::numeric as invoice_amount,
        null::numeric as invoice_total_with_tax,
        null::text as invoice_direction,
        '[]'::jsonb as invoice_source_links
    from app.oa_applications oa
    join needed_keys needed on needed.row_type = 'oa' and needed.row_id = oa.row_id
    where oa.status <> 'deleted'
      and {_COMPLETED_OA_SQL}
    union all
    select
        admission.oa_id,
        'oa'::text,
        'oa'::text,
        (admission.scope_key || '-01')::date,
        coalesce(
            {pending_oa_application_date_sql('admission')},
            (admission.scope_key || '-01')::date
        ),
        admission.updated_at,
        'in_progress'::text,
        jsonb_strip_nulls(jsonb_build_object(
            'applicant', admission.applicant,
            'applicationTime', {pending_oa_application_time_sql('admission')},
            'projectName', coalesce(admission.project_name_display, admission.project_name),
            'applicationType', case lower(coalesce(
                admission.source_payload->>'apply_type',
                admission.source_payload->>'application_type',
                admission.source_payload->>'form_type',
                ''
            ))
                when 'payment_request' then '支付申请'
                when '供应商付款申请' then '支付申请'
                when 'expense_claim' then '日常报销'
                else coalesce(
                    admission.source_payload->>'apply_type',
                    admission.source_payload->>'application_type',
                    admission.source_payload->>'form_type'
                )
            end,
            'expenseType', nullif(btrim(admission.source_payload->>'expense_type'), ''),
            'counterparty', admission.source_payload->>'counterparty_name',
            'reconciliationStatus', '待关联',
            'workflowStatus', 'in_progress'
        )),
        null::text,
        case when jsonb_typeof(admission.source_payload->'expense_items') = 'array'
             then admission.source_payload->'expense_items'
             else '[]'::jsonb end,
        case when jsonb_typeof(admission.source_payload->'source_aliases') = 'array'
             then admission.source_payload->'source_aliases'
             else '[]'::jsonb end,
        array_remove(array[
            admission.oa_id,
            admission.source_payload->>'oa_row_id',
            admission.source_payload->>'oa_id',
            admission.source_payload->>'source_oa_row_id',
            admission.source_payload->>'object_identity_key'
        ]::text[], null),
        array_remove(array[
            {_anomaly_oa_external_alias_values_sql('admission.source_payload')}
        ]::text[], null),
        coalesce(
            admission.source_payload->>'apply_type',
            admission.source_payload->>'application_type',
            admission.source_payload->>'form_type'
        ),
        admission.amount,
        null::numeric,
        null::text,
        null::numeric,
        null::numeric,
        null::text,
        '[]'::jsonb
    from app.oa_pending_payment_admissions admission
    join needed_keys needed on needed.row_type = 'oa' and needed.row_id = admission.oa_id
    where admission.tenant_id = (select tenant_id from requested_scope)
      and admission.workflow_status = 'in_progress'
),
oa_duplicate_ids as materialized (
    select candidate.row_id
    from oa_candidate_facts candidate
    group by candidate.row_id
    having count(*) > 1
),
oa_integrity_guard as materialized (
    select 1 / case when count(*) = 0 then 1 else 0 end as guard
    from oa_duplicate_ids
),
oa_candidates as materialized (
    select candidate.*
    from oa_candidate_facts candidate
    cross join oa_integrity_guard
    where oa_integrity_guard.guard = 1
),
bank_candidates as materialized (
    select
        coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
        'bank'::text as pane,
        'bank_transaction'::text as source_kind,
        bank.txn_month as scope_month,
        coalesce(bank.trade_time::date, bank.txn_date) as sort_date,
        bank.updated_at,
        null::text as workflow_status,
        jsonb_strip_nulls(jsonb_build_object(
            'transactionTime', coalesce(bank.trade_time::date, bank.txn_date)::text,
            'direction', case
                when lower(coalesce(bank.txn_direction, '')) in
                     ('out', 'outflow', 'debit', 'expense', '支出')
                     or coalesce(bank.signed_amount, 0) < 0
                    then '支出'
                else '收入'
            end,
            'counterparty', bank.counterparty_name_raw,
            'accountLast4', right(bank.account_no, 4),
            'paymentAccount', concat_ws(
                ' ',
                coalesce(account_mapping.bank_name, case
                    when bank.account_no like '6225%%' then '招商银行'
                    when bank.account_no like '6222%%' then '工商银行'
                    when bank.account_no like '6217%%' then '建设银行'
                    when bank.account_no like '6228%%' then '农业银行'
                    when bank.account_no like '6214%%' then '中国银行'
                    else '未识别银行'
                end),
                case
                    when bank.account_name like '%%基本%%' then '基本户'
                    when bank.account_name like '%%一般%%' then '一般户'
                    when bank.account_name like '%%专户%%' then '专户'
                    else '账户'
                end,
                right(bank.account_no, 4)
            ),
            'invoiceRelationStatus', '待关联发票',
            'loanRepaymentDate', bank.raw_payload->>'repayment_date'
        )) as column_values,
        null::text as external_etc_batch_id,
        '[]'::jsonb as oa_expense_items,
        '[]'::jsonb as oa_source_aliases,
        array[]::text[] as oa_exact_identity_aliases,
        array[]::text[] as oa_external_identity_aliases,
        null::text as oa_apply_type,
        null::numeric as oa_amount,
        bank.amount as bank_amount,
        case
            when lower(coalesce(bank.txn_direction, '')) in
                 ('out', 'outflow', 'debit', 'expense', 'payment', 'pay', '支出', '付款')
                 or coalesce(bank.signed_amount, 0) < 0
                then 'payment'
            when lower(coalesce(bank.txn_direction, '')) in
                 ('in', 'inflow', 'credit', 'income', 'receipt', 'receive', '收入', '收款')
                 or coalesce(bank.signed_amount, 0) > 0
                then 'receipt'
            else null
        end as bank_direction,
        null::numeric as invoice_amount,
        null::numeric as invoice_total_with_tax,
        null::text as invoice_direction,
        '[]'::jsonb as invoice_source_links
    from app.bank_transactions bank
    join needed_keys needed
      on needed.row_type = 'bank'
     and needed.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
    cross join requested_settings settings
    left join lateral (
        select coalesce(
            nullif(btrim(mapping.value->>'bank_name'), ''),
            nullif(btrim(mapping.value->>'bankName'), '')
        ) as bank_name
        from jsonb_array_elements(
            case
                when jsonb_typeof(settings.settings_payload->'bank_account_mappings') = 'array'
                    then settings.settings_payload->'bank_account_mappings'
                else '[]'::jsonb
            end
        ) mapping(value)
        where nullif(btrim(mapping.value->>'last4'), '') = right(bank.account_no, 4)
        limit 1
    ) account_mapping on true
    where bank.status <> 'deleted'
),
requested_invoice_hard_identities as materialized (
    select distinct invoice.hard_identity
    from visible_invoice_facts invoice
    join needed_keys needed
      on needed.row_type = 'invoice'
     and needed.row_id = invoice.row_id
),
invoice_candidates as materialized (
    select
        invoice.row_id,
        'invoice'::text as pane,
        invoice.source_kind,
        invoice.invoice_month as scope_month,
        invoice.invoice_date as sort_date,
        invoice.updated_at,
        null::text as workflow_status,
        jsonb_strip_nulls(jsonb_build_object(
            'sellerName', invoice.seller_name,
            'buyerName', invoice.buyer_name,
            'invoiceType', invoice.invoice_type,
            'issueDate', invoice.invoice_date::text
        )) as column_values,
        invoice.hard_identity,
        exists (
            select 1
            from app.workbench_pair_relations owner_relation
            where owner_relation.status = 'active'
              and cardinality(owner_relation.row_ids) = cardinality(owner_relation.row_types)
              and owner_relation.row_ids @> array[invoice.row_id]::text[]
              and exists (
                  select 1
                  from unnest(owner_relation.row_ids, owner_relation.row_types)
                       as owner_member(row_id, row_type)
                  where owner_member.row_id = invoice.row_id
                    and case lower(owner_member.row_type)
                            when 'invoice_record' then 'invoice'
                            when 'formal_invoice' then 'invoice'
                            when 'input' then 'invoice'
                            when 'input_invoice' then 'invoice'
                            when 'output' then 'invoice'
                            when 'output_invoice' then 'invoice'
                            when 'etc_summary' then 'invoice'
                            when 'etc_invoice_summary' then 'invoice'
                            else lower(owner_member.row_type)
                        end = 'invoice'
              )
        ) as active_relation_member,
        null::text as external_etc_batch_id,
        '[]'::jsonb as oa_expense_items,
        '[]'::jsonb as oa_source_aliases,
        array[]::text[] as oa_exact_identity_aliases,
        array[]::text[] as oa_external_identity_aliases,
        null::text as oa_apply_type,
        null::numeric as oa_amount,
        null::numeric as bank_amount,
        null::text as bank_direction,
        invoice.amount as invoice_amount,
        invoice.total_with_tax as invoice_total_with_tax,
        invoice.invoice_direction,
        invoice.invoice_source_links
    from visible_invoice_facts invoice
    join requested_invoice_hard_identities requested
      on requested.hard_identity = invoice.hard_identity
),
ranked_invoices as materialized (
    select candidate.*,
           row_number() over (
               partition by candidate.hard_identity
               order by candidate.active_relation_member desc,
                        case when candidate.source_kind = 'invoice' then 0 else 1 end,
                        candidate.row_id
           ) as identity_rank
    from invoice_candidates candidate
),
invoice_relation_identity_conflicts as materialized (
    select candidate.hard_identity
    from invoice_candidates candidate
    group by candidate.hard_identity
    having count(*) filter (where candidate.active_relation_member) > 1
),
invoice_identity_guard as materialized (
    select 1 / case when count(*) = 0 then 1 else 0 end as guard
    from invoice_relation_identity_conflicts
),
etc_summary_candidates as materialized (
    select
        summary.row_id,
        'invoice'::text as pane,
        'etc_invoice_summary'::text as source_kind,
        summary.scope_month,
        summary.scope_month as sort_date,
        summary.updated_at,
        null::text as workflow_status,
        jsonb_build_object(
            'sellerName', 'ETC批次',
            'buyerName', summary.external_batch_id,
            'invoiceType', '进项发票',
            'issueDate', summary.scope_month::text
        ) as column_values,
        summary.external_batch_id as external_etc_batch_id,
        '[]'::jsonb as oa_expense_items,
        '[]'::jsonb as oa_source_aliases,
        array[]::text[] as oa_exact_identity_aliases,
        array[]::text[] as oa_external_identity_aliases,
        null::text as oa_apply_type,
        null::numeric as oa_amount,
        null::numeric as bank_amount,
        null::text as bank_direction,
        null::numeric as invoice_amount,
        null::numeric as invoice_total_with_tax,
        'payment'::text as invoice_direction,
        '[]'::jsonb as invoice_source_links
    from etc_summary_keys summary
    join needed_keys needed
      on needed.row_type = 'invoice' and needed.row_id = summary.row_id
),
canonical_rows as materialized (
    select row_id, pane, source_kind, scope_month, sort_date, updated_at,
           workflow_status, column_values, external_etc_batch_id,
           oa_expense_items, oa_source_aliases,
           oa_exact_identity_aliases, oa_external_identity_aliases,
           oa_apply_type, oa_amount,
           bank_amount, bank_direction,
           invoice_amount, invoice_total_with_tax, invoice_direction,
           invoice_source_links
    from oa_candidates
    union all
    select row_id, pane, source_kind, scope_month, sort_date, updated_at,
           workflow_status, column_values, external_etc_batch_id,
           oa_expense_items, oa_source_aliases,
           oa_exact_identity_aliases, oa_external_identity_aliases,
           oa_apply_type, oa_amount,
           bank_amount, bank_direction,
           invoice_amount, invoice_total_with_tax, invoice_direction,
           invoice_source_links
    from bank_candidates
    union all
    select row_id, pane, source_kind, scope_month, sort_date, updated_at,
           workflow_status, column_values, external_etc_batch_id,
           oa_expense_items, oa_source_aliases,
           oa_exact_identity_aliases, oa_external_identity_aliases,
           oa_apply_type, oa_amount,
           bank_amount, bank_direction,
           invoice_amount, invoice_total_with_tax, invoice_direction,
           invoice_source_links
    from ranked_invoices
    cross join invoice_identity_guard
    where identity_rank = 1
      and invoice_identity_guard.guard = 1
    union all
    select row_id, pane, source_kind, scope_month, sort_date, updated_at,
           workflow_status, column_values, external_etc_batch_id,
           oa_expense_items, oa_source_aliases,
           oa_exact_identity_aliases, oa_external_identity_aliases,
           oa_apply_type, oa_amount,
           bank_amount, bank_direction,
           invoice_amount, invoice_total_with_tax, invoice_direction,
           invoice_source_links
    from etc_summary_candidates
),
in_progress_oa_relation_ids as materialized (
    select distinct membership.relation_id
    from all_active_relation_members membership
    join canonical_rows member
      on member.pane = membership.row_type
     and member.row_id = membership.row_id
    where membership.row_type = 'oa'
      and member.workflow_status = 'in_progress'
),
missing_relation_members as materialized (
    select member.relation_id, member.row_type, member.row_id
    from all_active_relation_members member
    join scoped_relation_ids selected on selected.id = member.relation_id
    left join canonical_rows row
      on row.pane = member.row_type
     and row.row_id = member.row_id
    where row.row_id is null
),
relation_member_guard as materialized (
    select 1 / case when count(*) = 0 then 1 else 0 end as guard
    from missing_relation_members
),
relation_groups as materialized (
    select
        'case:' || relation.case_id as internal_key,
        relation.case_id as detail_key,
        'relation'::text as group_kind,
        case
            when in_progress_oa.relation_id is not null then 'unpaired'
            when coalesce(relation.special_metadata->>'source', '') = 'batch_accounting'
                then 'paired'
            when 'oa' = any(relation.normalized_row_types)
                 and not ('bank' = any(relation.normalized_row_types)) then 'unpaired'
            when 'bank' = any(relation.normalized_row_types)
                 and coalesce(
                     (relation.special_metadata->>'requires_oa')::boolean,
                     (relation.special_metadata->>'paired_requires_oa')::boolean,
                     true
                 ) and not ('oa' = any(relation.normalized_row_types)) then 'unpaired'
            when 'bank' = any(relation.normalized_row_types)
                 and coalesce(
                     (relation.special_metadata->>'requires_invoice')::boolean,
                     (relation.special_metadata->>'paired_requires_invoice')::boolean,
                     true
                 ) and not ('invoice' = any(relation.normalized_row_types)) then 'unpaired'
            else 'paired'
        end as zone,
        relation.row_ids as member_ids,
        relation.normalized_row_types as member_types,
        relation.month_scope as scope_month,
        relation.updated_at,
        relation.external_etc_batch_id,
        array_remove(array[
            case when 'oa' = any(relation.normalized_row_types)
                       and not ('bank' = any(relation.normalized_row_types))
                 then 'bank' end,
            case when 'bank' = any(relation.normalized_row_types)
                       and coalesce(
                           (relation.special_metadata->>'requires_oa')::boolean,
                           (relation.special_metadata->>'paired_requires_oa')::boolean,
                           true
                       )
                       and not ('oa' = any(relation.normalized_row_types))
                       and coalesce(relation.special_metadata->>'source', '') <> 'batch_accounting'
                 then 'oa' end,
            case when 'bank' = any(relation.normalized_row_types)
                       and coalesce(
                           (relation.special_metadata->>'requires_invoice')::boolean,
                           (relation.special_metadata->>'paired_requires_invoice')::boolean,
                           true
                       )
                       and not ('invoice' = any(relation.normalized_row_types))
                       and coalesce(relation.special_metadata->>'source', '') <> 'batch_accounting'
                 then 'invoice' end
        ], null)::text[] as missing_row_types
    from scoped_relations relation
    left join in_progress_oa_relation_ids in_progress_oa
      on in_progress_oa.relation_id = relation.id
    cross join relation_member_guard
    where relation_member_guard.guard = 1
),
unpaired_groups as materialized (
    select
        'row:' || row.pane || ':' || row.row_id as internal_key,
        'v1:' || to_char(row.scope_month, 'YYYY-MM') || ':' || row.pane || ':' ||
            encode(convert_to(row.row_id, 'UTF8'), 'hex') as detail_key,
        'unpaired'::text as group_kind,
        'unpaired'::text as zone,
        array[row.row_id]::text[] as member_ids,
        array[row.pane]::text[] as member_types,
        row.scope_month,
        row.updated_at,
        row.external_etc_batch_id,
        array[]::text[] as missing_row_types
    from canonical_rows row
    cross join requested_scope scope
    where (scope.scope_key = 'all' or row.scope_month = scope.scope_month)
      and not exists (
          select 1
          from all_active_relation_members member
          where member.row_type = row.pane
            and member.row_id = row.row_id
      )
      and not exists (
          select 1
          from app.workbench_row_overrides override
          where override.status = 'active'
            and override.row_type = row.pane
            and override.row_id = row.row_id
            and coalesce(
                (override.override_payload->>'ignored')::boolean,
                override.override_payload->>'status' = 'ignored',
                false
            )
      )
),
canonical_groups as materialized (
    select * from relation_groups
    union all
    select * from unpaired_groups
),
canonical_group_members as materialized (
    select
        groups.internal_key,
        member.ordinality,
        member.row_id,
        member.row_type,
        row.source_kind,
        row.scope_month,
        row.sort_date,
        row.column_values,
        row.external_etc_batch_id,
        row.oa_expense_items,
        row.oa_source_aliases,
        row.oa_exact_identity_aliases,
        row.oa_external_identity_aliases,
        row.oa_apply_type,
        row.oa_amount,
        row.bank_amount,
        row.bank_direction,
        row.invoice_amount,
        row.invoice_total_with_tax,
        row.invoice_direction,
        row.invoice_source_links
    from canonical_groups groups
    cross join lateral unnest(groups.member_ids, groups.member_types)
      with ordinality as member(row_id, row_type, ordinality)
    join canonical_rows row
      on row.pane = member.row_type
     and row.row_id = member.row_id
)
"""


# These CTEs consume the already-built canonical group spine and keep anomaly
# evaluation in PostgreSQL.  They emit one compact state row per anomalous
# relation; no all-scope member JSON is copied into the application process.
_ANOMALY_STATE_CTES = f"""
latest_anomaly_decisions as materialized (
    select group_id, fingerprint, resolution as decision, updated_at
    from (
        select
            exception.raw_payload#>>'{{normalized_payload,group_id}}' as group_id,
            exception.raw_payload#>>'{{normalized_payload,fingerprint}}' as fingerprint,
            exception.resolution,
            exception.updated_at,
            row_number() over (
                partition by exception.raw_payload#>>'{{normalized_payload,group_id}}'
                order by exception.updated_at desc,
                         exception.version desc,
                         exception.case_id desc
            ) as decision_rank
        from app.workbench_exception_cases exception
        cross join requested_scope scope
        where exception.scenario = 'workbench_anomaly_review'
          and (scope.scope_key = 'all' or exception.scope_month = scope.scope_month)
    ) ranked_decisions
    where decision_rank = 1
      and resolution in ('accept_paired', 'keep_unpaired')
      and nullif(group_id, '') is not null
      and nullif(fingerprint, '') is not null
),
relation_anomaly_etc_requests as materialized (
    select distinct summary.external_batch_id
    from canonical_groups groups
    join canonical_group_members member
      on member.internal_key = groups.internal_key
    join etc_summary_keys summary on summary.row_id = member.row_id
    where groups.group_kind = 'relation'
      and member.row_type = 'invoice'
),
relation_anomaly_etc_source_rows as materialized (
    select
        1 as source_rank,
        requested.external_batch_id,
        coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
        coalesce(
            nullif(invoice.digital_invoice_no, ''),
            nullif(invoice.invoice_no, ''),
            coalesce(invoice.legacy_mongo_id, invoice.id::text)
        ) as invoice_identity,
        coalesce(invoice.total_with_tax, invoice.amount) as invoice_amount
    from relation_anomaly_etc_requests requested
    join app.etc_batch_invoice_links link on link.link_status = 'active'
    join app.invoices invoice
      on invoice.id = link.invoice_id and invoice.status <> 'deleted'
    left join app.etc_business_batches batch
      on batch.business_batch_id = link.business_batch_id
    where requested.external_batch_id = coalesce(
        nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
        link.business_batch_id
    )
    union all
    select
        2,
        requested.external_batch_id,
        coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text),
        coalesce(
            nullif(invoice.invoice_no, ''),
            coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text)
        ),
        coalesce(invoice.total_with_tax, invoice.amount)
    from relation_anomaly_etc_requests requested
    join app.etc_business_batches batch
      on batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
     and requested.external_batch_id = coalesce(
        nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
        nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
        batch.business_batch_id
     )
    join app.etc_invoices invoice
      on invoice.business_batch_id = batch.business_batch_id
     and invoice.status <> 'deleted'
    union all
    select
        3,
        requested.external_batch_id,
        coalesce(invoice.legacy_mongo_id, invoice.id::text),
        coalesce(
            nullif(invoice.digital_invoice_no, ''),
            nullif(invoice.invoice_no, ''),
            coalesce(invoice.legacy_mongo_id, invoice.id::text)
        ),
        coalesce(invoice.total_with_tax, invoice.amount)
    from relation_anomaly_etc_requests requested
    join app.etc_submission_batches submission
      on submission.status in ('submitted_confirmed', 'submitted', 'closed')
     and requested.external_batch_id = coalesce(
        nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
        submission.submission_batch_id
     )
    join app.invoices invoice
      on invoice.status <> 'deleted'
     and (
            submission.submission_batch_id = coalesce(
                invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
                ''
            )
         or requested.external_batch_id = coalesce(
                invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
                ''
            )
     )
     and (
            invoice.workbench_visibility = 'hidden_after_etc_submission'
         or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
                = 'hidden_after_etc_submission'
         or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
                = 'submitted'
     )
),
relation_anomaly_preferred_etc_rows as materialized (
    select source.*,
           case when source.source_rank in (1, 2) then 1 else 2 end
               as source_tier,
           row_number() over (
               partition by source.external_batch_id, source.invoice_identity
               order by source.source_rank, source.row_id
           ) as identity_rank,
           min(case when source.source_rank in (1, 2) then 1 else 2 end) over (
               partition by source.external_batch_id
           ) as preferred_source_tier
    from relation_anomaly_etc_source_rows source
),
relation_anomaly_etc_totals as materialized (
    select
        preferred.external_batch_id,
        round(sum(preferred.invoice_amount), 2) as invoice_total
    from relation_anomaly_preferred_etc_rows preferred
    where preferred.source_tier = preferred.preferred_source_tier
      and preferred.identity_rank = 1
    group by preferred.external_batch_id
),
relation_anomaly_members as materialized (
    select
        groups.internal_key,
        groups.detail_key as case_id,
        relation.relation_mode,
        member.row_type,
        member.row_id,
        member.oa_expense_items,
        member.oa_source_aliases,
        member.oa_exact_identity_aliases,
        member.oa_external_identity_aliases,
        member.oa_apply_type,
        member.oa_amount,
        member.bank_amount,
        member.bank_direction,
        coalesce(member.invoice_amount, etc_total.invoice_total) as invoice_amount,
        coalesce(
            member.invoice_total_with_tax,
            member.invoice_amount,
            etc_total.invoice_total
        ) as invoice_total_with_tax,
        member.invoice_direction,
        member.invoice_source_links
    from canonical_groups groups
    join scoped_relations relation
      on relation.case_id = groups.detail_key
    join canonical_group_members member
      on member.internal_key = groups.internal_key
    left join etc_summary_keys etc_key
      on member.row_type = 'invoice'
     and etc_key.row_id = member.row_id
    left join relation_anomaly_etc_totals etc_total
      on etc_total.external_batch_id = etc_key.external_batch_id
    where groups.group_kind = 'relation'
      and member.row_type in ('oa', 'bank', 'invoice')
),
oa_exact_identity_aliases as materialized (
    select distinct
        member.internal_key,
        member.row_id as oa_row_id,
        alias.value
    from relation_anomaly_members member
    cross join lateral unnest(member.oa_exact_identity_aliases) alias(value)
    where member.row_type = 'oa'
      and nullif(btrim(alias.value), '') is not null
),
oa_source_identity_aliases as materialized (
    select distinct
        member.internal_key,
        member.row_id as oa_row_id,
        alias.value
    from relation_anomaly_members member
    cross join lateral jsonb_array_elements_text(member.oa_source_aliases) alias(value)
    where member.row_type = 'oa'
      and nullif(btrim(alias.value), '') is not null
),
oa_external_identity_aliases as materialized (
    select distinct
        member.internal_key,
        member.row_id as oa_row_id,
        alias.value
    from relation_anomaly_members member
    cross join lateral unnest(member.oa_external_identity_aliases) alias(value)
    where member.row_type = 'oa'
      and nullif(btrim(alias.value), '') is not null
),
oa_identity_aliases as materialized (
    select internal_key, oa_row_id, value
    from oa_exact_identity_aliases
    union
    select internal_key, oa_row_id, value
    from oa_source_identity_aliases
    union
    select internal_key, oa_row_id, regexp_replace(value, '^oa-(exp|pay)-', '')
    from oa_source_identity_aliases
    union
    select internal_key, oa_row_id, value
    from oa_external_identity_aliases
    union
    select internal_key, oa_row_id, 'oa-exp-' || value
    from oa_external_identity_aliases
    union
    select internal_key, oa_row_id, 'oa-pay-' || value
    from oa_external_identity_aliases
),
oa_expense_items as materialized (
    select
        member.internal_key,
        member.case_id,
        member.row_id as oa_row_id,
        coalesce(item.value->>'id', item.value->>'expense_item_id') as item_id,
        item.value->>'row_index' as row_index,
        case
            when replace(coalesce(
                item.value->>'amount',
                item.value->>'settlement_amount',
                item.value->>'total_with_tax'
            ), ',', '') ~ '^[+-]?[0-9]+([.][0-9]+)?$'
                then round(replace(coalesce(
                    item.value->>'amount',
                    item.value->>'settlement_amount',
                    item.value->>'total_with_tax'
                ), ',', '')::numeric, 2)
            else null
        end as item_amount,
        case
            when coalesce(item.value->>'attachment_file_count', '') ~ '^[0-9]+$'
                then greatest(0, (item.value->>'attachment_file_count')::integer)
            else 0
        end as attachment_file_count
    from relation_anomaly_members member
    cross join lateral jsonb_array_elements(member.oa_expense_items) item(value)
    where member.row_type = 'oa'
      and nullif(btrim(coalesce(
          item.value->>'id', item.value->>'expense_item_id'
      )), '') is not null
),
invoice_anomaly_facts as materialized (
    select distinct
        member.internal_key,
        member.case_id,
        member.row_id as invoice_row_id,
        coalesce(member.invoice_total_with_tax, member.invoice_amount) as invoice_amount,
        source_link.source_expense_item_id,
        coalesce(
            source_link.source_expense_row_index,
            nullif(split_part(
                split_part(source_link.source_expense_item_id, ':item:', 2),
                ':',
                1
            ), '')
        ) as source_expense_row_index,
        coalesce(
            nullif(source_link.derived_from_oa_id, ''),
            nullif(split_part(source_link.source_expense_item_id, ':item:', 1), '')
        ) as source_parent_oa_id
    from relation_anomaly_members member
    left join lateral (
        select
            link.value->>'source_expense_item_id' as source_expense_item_id,
            link.value->>'source_expense_row_index' as source_expense_row_index,
            link.value->>'derived_from_oa_id' as derived_from_oa_id
        from jsonb_array_elements(
            case when jsonb_typeof(member.invoice_source_links) = 'array'
                 then member.invoice_source_links
                 else '[]'::jsonb end
        ) with ordinality link(value, ordinality)
        where coalesce(
            link.value->>'source_type',
            link.value->>'type',
            link.value->>'source'
        ) in ('oa_attachment_invoice', 'oa_expense_item_invoice')
    ) source_link on true
    where member.row_type = 'invoice'
),
invoice_item_candidates as materialized (
    select
        invoice.internal_key,
        invoice.invoice_row_id,
        invoice.source_expense_item_id,
        invoice.source_expense_row_index,
        expense.item_id,
        count(*) over (
            partition by
                invoice.internal_key,
                invoice.invoice_row_id,
                invoice.source_expense_item_id,
                invoice.source_expense_row_index
        ) as candidate_count
    from invoice_anomaly_facts invoice
    join oa_expense_items expense
      on expense.internal_key = invoice.internal_key
     and nullif(invoice.source_expense_item_id, '') is not null
     and invoice.source_expense_row_index = expense.row_index
     and exists (
         select 1
         from oa_identity_aliases alias
         where alias.internal_key = expense.internal_key
           and alias.oa_row_id = expense.oa_row_id
           and alias.value = split_part(
               invoice.source_expense_item_id,
               ':item:',
               1
           )
     )
),
normalized_invoice_anomaly_facts as materialized (
    select
        invoice.*,
        coalesce(
            (
                select candidate.item_id
                from invoice_item_candidates candidate
                where candidate.internal_key = invoice.internal_key
                  and candidate.invoice_row_id = invoice.invoice_row_id
                  and candidate.source_expense_item_id is not distinct from invoice.source_expense_item_id
                  and candidate.source_expense_row_index is not distinct from invoice.source_expense_row_index
                  and candidate.candidate_count = 1
                limit 1
            ),
            invoice.source_expense_item_id
        ) as canonical_expense_item_id
    from invoice_anomaly_facts invoice
),
normalized_invoice_item_links as materialized (
    select distinct
        invoice.internal_key,
        invoice.case_id,
        invoice.invoice_row_id,
        invoice.invoice_amount,
        invoice.canonical_expense_item_id
    from normalized_invoice_anomaly_facts invoice
    join oa_expense_items expense
      on expense.internal_key = invoice.internal_key
     and expense.item_id = invoice.canonical_expense_item_id
),
unassigned_invoice_rows as materialized (
    select distinct
        expense.internal_key,
        expense.item_id,
        invoice.invoice_row_id
    from oa_expense_items expense
    join normalized_invoice_anomaly_facts invoice
      on invoice.internal_key = expense.internal_key
     and invoice.source_parent_oa_id is not null
     and exists (
         select 1
         from oa_identity_aliases alias
         where alias.internal_key = expense.internal_key
           and alias.oa_row_id = expense.oa_row_id
           and alias.value = invoice.source_parent_oa_id
     )
    where not exists (
        select 1
        from normalized_invoice_item_links linked
        where linked.internal_key = invoice.internal_key
          and linked.invoice_row_id = invoice.invoice_row_id
    )
),
unlinked_expense_items as materialized (
    select
        expense.internal_key,
        expense.case_id,
        expense.item_id,
        expense.item_amount,
        expense.attachment_file_count,
        count(unassigned.invoice_row_id)::bigint as unassigned_invoice_count,
        string_agg(
            encode(convert_to(unassigned.invoice_row_id, 'UTF8'), 'hex'),
            '00' order by unassigned.invoice_row_id
        ) as invoice_row_ids_hex
    from oa_expense_items expense
    left join normalized_invoice_item_links linked
      on linked.internal_key = expense.internal_key
     and linked.canonical_expense_item_id = expense.item_id
    left join unassigned_invoice_rows unassigned
      on unassigned.internal_key = expense.internal_key
     and unassigned.item_id = expense.item_id
    where linked.invoice_row_id is null
    group by
        expense.internal_key,
        expense.case_id,
        expense.item_id,
        expense.item_amount,
        expense.attachment_file_count
),
unlinked_expense_anomaly_items as materialized (
    select
        totals.internal_key,
        totals.case_id,
        encode(digest(
            convert_to(totals.case_id, 'UTF8') || decode('00', 'hex') ||
            convert_to(
                case when totals.unassigned_invoice_count > 0
                     then 'oa_invoice_attachment_unassigned'
                     when totals.attachment_file_count = 0
                     then 'oa_invoice_attachment_absent'
                     else 'oa_invoice_attachment_unparsed' end,
                'UTF8'
            ) || decode('00', 'hex') ||
            convert_to(totals.item_id, 'UTF8') || decode('00', 'hex') ||
            convert_to(coalesce(to_char(
                totals.item_amount,
                'FM999999999999999999990.00'
            ), ''), 'UTF8') || decode('00', 'hex') ||
            decode('00', 'hex') ||
            decode('00', 'hex') ||
            convert_to(totals.attachment_file_count::text, 'UTF8') ||
            case when totals.unassigned_invoice_count > 0
                 then decode('00', 'hex') || decode(totals.invoice_row_ids_hex, 'hex')
                 else ''::bytea end,
            'sha256'
        ), 'hex') as item_fingerprint
    from unlinked_expense_items totals
),
expense_anomaly_items as materialized (
    select
        item.internal_key,
        item.case_id,
        item.item_fingerprint,
        null::text as exception_code,
        true as has_document_anomaly
    from unlinked_expense_anomaly_items item
),
relation_directions as materialized (
    select
        member.internal_key,
        case
            when count(distinct direction.value) = 1 then min(direction.value)
            else null
        end as direction
    from relation_anomaly_members member
    left join lateral (
        select case
            when member.row_type = 'oa'
             and coalesce(member.oa_apply_type, '') like '%%收%%'
             and coalesce(member.oa_apply_type, '') not like '%%付%%'
                then 'receipt'
            when member.row_type = 'oa' then 'payment'
            when member.row_type = 'invoice' then member.invoice_direction
            else null
        end as value
    ) direction on true
    group by member.internal_key
),
relation_pane_totals as materialized (
    select
        member.internal_key,
        min(member.case_id) as case_id,
        min(member.relation_mode) as relation_mode,
        direction.direction,
        count(*) filter (where member.row_type = 'oa')::bigint as oa_count,
        count(*) filter (
            where member.row_type = 'oa'
              and member.oa_amount is null
        )::bigint as invalid_oa_amount_count,
        round(sum(member.oa_amount) filter (where member.row_type = 'oa'), 2) as oa_total,
        count(*) filter (where member.row_type = 'bank')::bigint as bank_count,
        count(*) filter (
            where member.row_type = 'bank' and member.bank_amount is null
        )::bigint as invalid_bank_amount_count,
        count(*) filter (
            where member.row_type = 'bank' and member.bank_direction is null
        )::bigint as invalid_bank_direction_count,
        round(case
            when direction.direction is null then
                sum(member.bank_amount) filter (where member.row_type = 'bank')
            when count(*) filter (
                where member.row_type = 'bank' and member.bank_direction is not null
            ) = 0 then
                sum(member.bank_amount) filter (where member.row_type = 'bank')
            else coalesce(sum(member.bank_amount) filter (
                where member.row_type = 'bank'
                  and member.bank_direction = direction.direction
            ), 0)
        end, 2) as bank_gross_total,
        round(case
            when direction.direction is null then 0
            when count(*) filter (
                where member.row_type = 'bank' and member.bank_direction is not null
            ) = 0 then 0
            else coalesce(sum(member.bank_amount) filter (
                where member.row_type = 'bank'
                  and member.bank_direction in ('payment', 'receipt')
                  and member.bank_direction <> direction.direction
            ), 0)
        end, 2) as bank_contra_total,
        count(*) filter (where member.row_type = 'invoice')::bigint as invoice_count,
        count(*) filter (
            where member.row_type = 'invoice'
              and coalesce(member.invoice_total_with_tax, member.invoice_amount) is null
        )::bigint as invalid_invoice_amount_count,
        count(*) filter (
            where member.row_type = 'invoice' and member.invoice_direction is null
        )::bigint as invalid_invoice_direction_count,
        round(case
            when direction.direction is null then sum(coalesce(
                member.invoice_total_with_tax,
                member.invoice_amount
            )) filter (where member.row_type = 'invoice')
            when count(*) filter (
                where member.row_type = 'invoice' and member.invoice_direction is not null
            ) = 0 then sum(coalesce(
                member.invoice_total_with_tax,
                member.invoice_amount
            )) filter (where member.row_type = 'invoice')
            else coalesce(sum(coalesce(
                member.invoice_total_with_tax,
                member.invoice_amount
            )) filter (
                where member.row_type = 'invoice'
                  and member.invoice_direction = direction.direction
            ), 0)
        end, 2) as invoice_total,
        string_agg(
            encode(convert_to(member.row_id, 'UTF8'), 'hex'),
            '00' order by member.row_id
        ) filter (where member.row_type = 'invoice') as invoice_row_ids_hex
    from relation_anomaly_members member
    join relation_directions direction on direction.internal_key = member.internal_key
    group by member.internal_key, direction.direction
),
relation_comparison_totals as materialized (
    select
        totals.*,
        case
            when totals.relation_mode = 'turnover_manual_closure'
             and totals.bank_gross_total > 0
             and totals.bank_gross_total = totals.bank_contra_total
                then totals.bank_gross_total
            else totals.bank_gross_total - totals.bank_contra_total
        end as bank_total
    from relation_pane_totals totals
),
relation_amount_classifications as materialized (
    select
        totals.*,
        case
            when totals.oa_total = totals.bank_total then
                case when totals.invoice_total > totals.oa_total
                     then 'oa_bank_equal_invoice_more'
                     else 'oa_bank_equal_invoice_less' end
            when totals.oa_total = totals.invoice_total then
                case when totals.bank_total > totals.oa_total
                     then 'oa_invoice_equal_bank_more'
                     else 'oa_invoice_equal_bank_less' end
            when totals.bank_total = totals.invoice_total then
                case when totals.oa_total < totals.bank_total
                     then 'bank_invoice_equal_oa_less'
                     else 'bank_invoice_equal_oa_more' end
            else 'all_amounts_different'
        end as code
    from relation_comparison_totals totals
    where totals.direction is not null
      and totals.oa_count > 0 and totals.bank_count > 0 and totals.invoice_count > 0
      and totals.invalid_oa_amount_count = 0
      and totals.invalid_bank_amount_count = 0
      and totals.invalid_bank_direction_count = 0
      and totals.invalid_invoice_amount_count = 0
      and totals.invalid_invoice_direction_count = 0
      and totals.oa_total is not null
      and totals.bank_total is not null
      and totals.invoice_total is not null
      and not (
          totals.oa_total = totals.bank_total
          and totals.bank_total = totals.invoice_total
      )
),
relation_amount_anomaly_items as materialized (
    select
        totals.internal_key,
        totals.case_id,
        encode(digest(
            convert_to(totals.case_id, 'UTF8') || decode('00', 'hex') ||
            convert_to(totals.code, 'UTF8') || decode('00', 'hex') ||
            convert_to(totals.case_id, 'UTF8') || decode('00', 'hex') ||
            convert_to(coalesce(to_char(totals.oa_total,
                'FM999999999999999999990.00'), ''), 'UTF8') || decode('00', 'hex') ||
            convert_to(coalesce(to_char(totals.bank_total,
                'FM999999999999999999990.00'), ''), 'UTF8') || decode('00', 'hex') ||
            convert_to(coalesce(to_char(totals.invoice_total,
                'FM999999999999999999990.00'), ''), 'UTF8') || decode('00', 'hex') ||
            convert_to('0', 'UTF8') ||
            case when totals.invoice_row_ids_hex is not null
                 then decode('00', 'hex') || decode(totals.invoice_row_ids_hex, 'hex')
                 else ''::bytea end,
            'sha256'
        ), 'hex') as item_fingerprint,
        totals.code as exception_code,
        false as has_document_anomaly
    from relation_amount_classifications totals
),
all_anomaly_items as materialized (
    select
        item.internal_key,
        item.case_id,
        item.item_fingerprint,
        item.exception_code,
        item.has_document_anomaly
    from expense_anomaly_items item
    union all
    select
        item.internal_key,
        item.case_id,
        item.item_fingerprint,
        item.exception_code,
        item.has_document_anomaly
    from relation_amount_anomaly_items item
),
anomaly_fingerprints as materialized (
    select
        item.internal_key,
        min(item.case_id) as case_id,
        max(item.exception_code) as exception_code,
        bool_or(item.has_document_anomaly) as has_document_anomaly,
        encode(digest(
            convert_to(min(item.case_id), 'UTF8') || decode('00', 'hex') ||
            decode(string_agg(
                encode(convert_to(item.item_fingerprint, 'UTF8'), 'hex'),
                '00' order by item.item_fingerprint
            ), 'hex'),
            'sha256'
        ), 'hex') as fingerprint
    from all_anomaly_items item
    group by item.internal_key
),
anomaly_states as materialized (
    select
        anomaly.internal_key,
        anomaly.case_id,
        anomaly.fingerprint,
        anomaly.exception_code,
        anomaly.has_document_anomaly,
        case
            when decision.fingerprint = anomaly.fingerprint
             and decision.updated_at >= groups.updated_at
                then decision.decision
            else 'pending'
        end as decision
    from anomaly_fingerprints anomaly
    join canonical_groups groups on groups.internal_key = anomaly.internal_key
    left join latest_anomaly_decisions decision
      on decision.group_id = anomaly.internal_key
)
"""

# A filter option can only be emitted by a group containing the target pane.
# Keep the effective-group contract unchanged, while avoiding anomaly work for
# groups that cannot contribute any option to the current request.
_FILTER_OPTION_ANOMALY_STATE_CTES = f"""
filter_option_anomaly_groups as materialized (
    select groups.*
    from canonical_groups groups
    where exists (
        select 1
        from canonical_group_members target_member
        where target_member.internal_key = groups.internal_key
          and target_member.row_type = %s
    )
),
{_ANOMALY_STATE_CTES.replace("canonical_groups groups", "filter_option_anomaly_groups groups")}
"""

_EFFECTIVE_GROUPS_CTES = """
effective_groups as materialized (
    select
        groups.internal_key,
        groups.detail_key,
        groups.group_kind,
        case
            when anomaly.internal_key is not null
             and anomaly.decision <> 'accept_paired'
                then 'unpaired'
            else groups.zone
        end as zone,
        groups.member_ids,
        groups.member_types,
        groups.scope_month,
        groups.updated_at,
        groups.external_etc_batch_id,
        groups.missing_row_types
    from canonical_groups groups
    left join anomaly_states anomaly
      on anomaly.internal_key = groups.internal_key
)
"""


class PostgresWorkbenchPageQueryRepository:
    """Direct Workbench page reads from canonical PostgreSQL facts."""

    def __init__(self, connection: Any, *, tenant_id: str) -> None:
        self._connection = connection
        self._tenant_id = str(tenant_id or "").strip()
        if not self._tenant_id:
            raise ValueError("tenant_id is required for Workbench direct queries.")

    def get_workbench_initial_page(
        self,
        *,
        scope_key: str,
        paired_query: dict[str, Any] | None = None,
        unpaired_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._in_snapshot(
            lambda repository: repository._initial_page(
                scope_key=scope_key,
                paired_query=paired_query,
                unpaired_query=unpaired_query,
            )
        )

    def get_workbench_groups_page(self, **kwargs: Any) -> dict[str, Any]:
        return self._in_snapshot(lambda repository: repository._groups_page(**kwargs))

    def get_workbench_filter_options(self, **kwargs: Any) -> dict[str, Any]:
        return self._in_snapshot(lambda repository: repository._filter_options(**kwargs))

    def get_workbench_group_detail(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._in_snapshot(lambda repository: repository._group_detail(**kwargs))

    def get_workbench_row_detail(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._in_snapshot(lambda repository: repository._row_detail(**kwargs))

    def _in_snapshot(self, operation: Callable[["PostgresWorkbenchPageQueryRepository"], T]) -> T:
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            raise RuntimeError("Workbench direct queries require PostgreSQL transaction support.")
        try:
            with transaction_factory() as transaction:
                transaction.execute("set transaction isolation level repeatable read read only")
                transaction.execute(
                    f"set local statement_timeout = '{WORKBENCH_DIRECT_QUERY_TIMEOUT_SECONDS}s'"
                )
                # This query is dominated by bounded JSON/array expansion and hash
                # joins.  PostgreSQL's JIT compilation cost is paid on every page
                # request and exceeds the execution savings for the current data
                # shape, so keep it disabled inside this read-only snapshot only.
                transaction.execute("set local jit = off")
                # The canonical page spine intentionally materializes bounded fact sets
                # before it computes exact totals.  PostgreSQL materially overestimates
                # several CTE cardinalities and otherwise chooses correlated nested
                # loops over the relation/member arrays.  Production EXPLAIN and
                # pg_stat_statements evidence show the hash/merge plan is both stable
                # and an order of magnitude faster for this repository's query shape.
                transaction.execute("set local enable_nestloop = off")
                # The all-scope spine is already set based. Let concurrent HTTP
                # requests share database CPU instead of starting parallel workers
                # for each identical page read.
                transaction.execute("set local max_parallel_workers_per_gather = 0")
                return operation(
                    PostgresWorkbenchPageQueryRepository(
                        transaction,
                        tenant_id=self._tenant_id,
                    )
                )
        except Exception as error:
            if is_transient_postgres_query_error(
                error
            ) or is_workbench_data_integrity_query_error(error):
                raise WorkbenchDirectQueryUnavailable(
                    "Workbench canonical PostgreSQL query is temporarily unavailable."
                ) from error
            raise

    def _initial_page(
        self,
        *,
        scope_key: str,
        paired_query: dict[str, Any] | None,
        unpaired_query: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        paired_plan = self._initial_zone_plan(
            scope_key=normalized_scope,
            zone="paired",
            query=paired_query,
        )
        unpaired_plan = self._initial_zone_plan(
            scope_key=normalized_scope,
            zone="unpaired",
            query=unpaired_query,
        )
        if paired_plan["exception_bucket"] or unpaired_plan["exception_bucket"]:
            raise ValueError("Initial Workbench query does not accept exception_bucket.")
        rows = self._connection.fetch_all(
            f"""
            with recursive {_SCOPED_CANONICAL_GROUPS_CTE},
            {_ANOMALY_STATE_CTES},
            {_EFFECTIVE_GROUPS_CTES},
            overall_group_summary as materialized (
                select
                    count(*) filter (where groups.zone = 'paired')::bigint
                        as summary_paired_count,
                    count(*) filter (where groups.zone = 'unpaired')::bigint
                        as summary_unpaired_count,
                    count(*) filter (
                        where groups.zone = 'unpaired'
                          and groups.group_kind = 'relation'
                    )::bigint as incomplete_group_count,
                    count(*) filter (where 'oa' = any(groups.missing_row_types))::bigint
                        as missing_oa_group_count,
                    count(*) filter (where 'bank' = any(groups.missing_row_types))::bigint
                        as missing_bank_group_count,
                    count(*) filter (where 'invoice' = any(groups.missing_row_types))::bigint
                        as missing_invoice_group_count
                from effective_groups groups
            ),
            overall_unique_members as materialized (
                select
                    member.row_type,
                    member.row_id,
                    bool_or(groups.zone = 'paired') as in_paired,
                    bool_or(groups.zone = 'unpaired') as in_unpaired,
                    bool_or(member.column_values->>'direction' = '支出') as is_expense,
                    bool_or(member.column_values->>'direction' = '收入') as is_income,
                    bool_or(
                        lower(coalesce(member.column_values->>'invoiceType', ''))
                            like any(array['%%进%%', '%%input%%', '%%purchase%%'])
                    ) as is_input_invoice,
                    bool_or(
                        lower(coalesce(member.column_values->>'invoiceType', ''))
                            like any(array['%%销%%', '%%output%%', '%%sale%%'])
                    ) as is_output_invoice
                from effective_groups groups
                join canonical_group_members member
                  on member.internal_key = groups.internal_key
                group by member.row_type, member.row_id
            ),
            overall_member_summary as materialized (
                select
                    count(*) filter (where member.row_type = 'oa')::bigint
                        as summary_oa_count,
                    count(*) filter (where member.row_type = 'bank')::bigint
                        as summary_bank_count,
                    count(*)
                        filter (where member.row_type = 'invoice')::bigint
                        as summary_invoice_count,
                    count(*) filter (
                        where member.row_type = 'bank' and member.is_expense
                    )::bigint as expense_transaction_count,
                    count(*) filter (
                        where member.row_type = 'bank' and member.is_income
                    )::bigint as income_transaction_count,
                    count(*) filter (
                        where member.row_type = 'invoice' and member.is_input_invoice
                    )::bigint as input_invoice_count,
                    count(*) filter (
                        where member.row_type = 'invoice' and member.is_output_invoice
                    )::bigint as output_invoice_count,
                    count(*) filter (
                        where member.in_paired and member.row_type = 'oa'
                    )::bigint as paired_oa_count,
                    count(*) filter (
                        where member.in_paired and member.row_type = 'bank'
                    )::bigint as paired_bank_count,
                    count(*) filter (
                        where member.in_paired and member.row_type = 'invoice'
                    )::bigint as paired_invoice_count
                from overall_unique_members member
            ),
            overall_summary as materialized (
                select *
                from overall_group_summary
                cross join overall_member_summary
            ),
            {self._initial_zone_ctes('paired', paired_plan)},
            {self._initial_zone_ctes('unpaired', unpaired_plan)},
            invoice_inventory as materialized (
                select
                    count(*)::bigint as inventory_system_total,
                    count(*) filter (where exists (
                        select 1
                        from jsonb_array_elements(
                            case when jsonb_typeof(invoice.source_links) = 'array'
                                 then invoice.source_links else '[]'::jsonb end
                        ) source_link
                        where coalesce(
                            source_link->>'source_type',
                            source_link->>'type',
                            source_link->>'source'
                        ) = 'manual_invoice_import'
                    ))::bigint as inventory_manual_import_total,
                    count(*) filter (
                        where coalesce(invoice.workbench_visibility, 'visible')
                            <> 'hidden_after_etc_submission'
                    )::bigint as inventory_workbench_visible_total,
                    count(*) filter (
                        where invoice.workbench_visibility = 'hidden_after_etc_submission'
                    )::bigint as inventory_hidden_submitted_etc_total,
                    count(*) filter (
                        where nullif(invoice.etc_invoice_id, '') is not null
                           or invoice.tags && array['ETC', 'etc', 'etc_invoice']::text[]
                    )::bigint as inventory_extra_etc_total,
                    count(*) filter (where exists (
                        select 1
                        from jsonb_array_elements(
                            case when jsonb_typeof(invoice.source_links) = 'array'
                                 then invoice.source_links else '[]'::jsonb end
                        ) source_link
                        where coalesce(
                            source_link->>'source_type',
                            source_link->>'type',
                            source_link->>'source'
                        ) = 'oa_attachment_invoice'
                    ))::bigint as inventory_oa_attachment_total
                from app.invoices invoice
                cross join requested_scope scope
                where invoice.status <> 'deleted'
                  and (scope.scope_key = 'all' or invoice.invoice_month = scope.scope_month)
            ),
            batch_inventory as materialized (
                select count(distinct coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                ))::bigint as inventory_etc_summary_batch_count
                from app.etc_business_batches batch
                cross join requested_scope scope
                where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                  and (scope.scope_key = 'all' or batch.scope_month = scope.scope_month)
            ),
            anomaly_counts as materialized (
                select
                    count(*) filter (
                        where groups.zone = 'unpaired'
                    )::bigint as unpaired_exception_count,
                    count(*) filter (
                        where groups.zone = 'paired'
                    )::bigint as paired_exception_count
                from anomaly_states anomaly
                join effective_groups groups
                  on groups.internal_key = anomaly.internal_key
            ),
            page_metadata as materialized (
                select *
                from overall_summary
                cross join invoice_inventory
                cross join batch_inventory
                cross join anomaly_counts
            )
            select
                'metadata'::text as record_zone,
                null::text as internal_key,
                null::text as detail_key,
                null::text as group_kind,
                null::text as zone,
                null::text[] as member_ids,
                null::text[] as member_types,
                null::date as scope_month,
                null::timestamptz as updated_at,
                null::text as external_etc_batch_id,
                null::text[] as missing_row_types,
                null::boolean as sort_missing,
                null::text as sort_value,
                null::bigint as page_position,
                null::bigint as total_count,
                null::bigint as oa_count,
                null::bigint as bank_count,
                null::bigint as invoice_count,
                page_metadata.*
            from page_metadata
            union all
            {self._initial_zone_output_sql('paired')}
            union all
            {self._initial_zone_output_sql('unpaired')}
            order by record_zone, page_position nulls last
            """,
            tuple(
                [
                    *self._scope_params(normalized_scope),
                    *paired_plan["search_params"],
                    *paired_plan["where_params"],
                    WORKBENCH_GROUP_PAGE_SIZE + 1,
                    *unpaired_plan["search_params"],
                    *unpaired_plan["where_params"],
                    WORKBENCH_GROUP_PAGE_SIZE + 1,
                ]
            ),
        )
        metadata_rows = [
            row for row in rows if str(row.get("record_zone") or "") == "metadata"
        ]
        if len(metadata_rows) != 1:
            raise RuntimeError("Workbench initial query must return exactly one metadata row.")
        metadata = metadata_rows[0]
        rows_by_zone = {
            zone: [row for row in rows if str(row.get("record_zone") or "") == zone]
            for zone in ("paired", "unpaired")
        }
        visible_descriptors_by_zone = {
            zone: [
                row
                for row in rows_by_zone[zone]
                if str(row.get("internal_key") or "").strip()
            ][:WORKBENCH_GROUP_PAGE_SIZE]
            for zone in ("paired", "unpaired")
        }
        combined_descriptors = [
            *visible_descriptors_by_zone["paired"],
            *visible_descriptors_by_zone["unpaired"],
        ]
        hydrated_groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=combined_descriptors,
            detail_level="summary",
        )
        if len(hydrated_groups) != len(combined_descriptors):
            raise RuntimeError("Workbench initial page hydration returned an incomplete batch.")
        paired_group_count = len(visible_descriptors_by_zone["paired"])
        paired_groups = hydrated_groups[:paired_group_count]
        unpaired_groups = hydrated_groups[paired_group_count:]
        paired = self._initial_zone_payload(
            scope_key=normalized_scope,
            plan=paired_plan,
            rows=rows_by_zone["paired"],
            visible_descriptors=visible_descriptors_by_zone["paired"],
            groups=paired_groups,
        )
        unpaired = self._initial_zone_payload(
            scope_key=normalized_scope,
            plan=unpaired_plan,
            rows=rows_by_zone["unpaired"],
            visible_descriptors=visible_descriptors_by_zone["unpaired"],
            groups=unpaired_groups,
        )
        summary_payload = self._summary_payload(
            metadata=metadata,
            paired=paired,
            unpaired=unpaired,
        )
        return {
            "month": normalized_scope,
            "scope_key": normalized_scope,
            **summary_payload,
            "paired": paired,
            "unpaired": unpaired,
        }

    def _initial_zone_plan(
        self,
        *,
        scope_key: str,
        zone: str,
        query: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = self._page_query(query)
        normalized_sort, direction, sort_expression = self._group_sort(payload.get("sort"))
        normalized_status = self._status(payload.get("status"))
        normalized_source_kind = self._source_kind(payload.get("source_kind"))
        normalized_search = self._search(payload.get("search"))
        normalized_columns = normalize_workbench_column_filters(payload.get("column_filters"))
        normalized_times = normalize_workbench_time_filters(payload.get("time_filters"))
        exception_bucket = text(payload.get("exception_bucket"))
        if exception_bucket not in {None, "unpaired", "paired"}:
            raise ValueError("exception_bucket must be unpaired or paired.")
        search_ctes, search_params, search_hit_name = self._source_search_hit_ctes(
            prefix=zone,
            search=normalized_search,
        )
        bank_tag_row_ids = self._resolve_bank_tag_filter_row_ids(
            scope_key=scope_key,
            zone=zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=exception_bucket,
        )
        where_sql, where_params = self._group_filters(
            zone=zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            search_hit_name=search_hit_name,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=exception_bucket,
            bank_tag_row_ids=bank_tag_row_ids,
        )
        normalized_query = {
            "scope_key": scope_key,
            "zone": zone,
            "status": normalized_status,
            "source_kind": normalized_source_kind,
            "search": normalized_search,
            "sort": normalized_sort,
            "column_filters": normalized_columns,
            "time_filters": normalized_times,
            "exception_bucket": exception_bucket,
        }
        return {
            "zone": zone,
            "where_sql": where_sql,
            "where_params": where_params,
            "sort": normalized_sort,
            "sort_expression": sort_expression,
            "order_sql": self._group_order_sql(direction),
            "query_hash": workbench_query_hash(normalized_query),
            "search_ctes": search_ctes,
            "search_params": search_params,
            "exception_bucket": exception_bucket,
            "uses_unfiltered_zone_counts": not any(
                (
                    normalized_status,
                    normalized_source_kind,
                    normalized_search,
                    normalized_columns,
                    normalized_times,
                    exception_bucket,
                )
            ),
        }

    @staticmethod
    def _filtered_groups_select_sql(
        *,
        where_sql: str,
        normalized_sort: str,
    ) -> str:
        if normalized_sort == "default:desc":
            return f"""
                select
                    groups.*,
                    null::date as oa_sort_min,
                    null::date as oa_sort_max,
                    null::date as bank_sort_min,
                    null::date as bank_sort_max,
                    null::date as invoice_sort_min,
                    null::date as invoice_sort_max
                from effective_groups groups
                where {where_sql}
            """
        return f"""
            select
                groups.*,
                min(member.sort_date) filter (where member.row_type = 'oa') as oa_sort_min,
                max(member.sort_date) filter (where member.row_type = 'oa') as oa_sort_max,
                min(member.sort_date) filter (where member.row_type = 'bank') as bank_sort_min,
                max(member.sort_date) filter (where member.row_type = 'bank') as bank_sort_max,
                min(member.sort_date) filter (where member.row_type = 'invoice')
                    as invoice_sort_min,
                max(member.sort_date) filter (where member.row_type = 'invoice')
                    as invoice_sort_max
            from effective_groups groups
            left join canonical_group_members member
              on member.internal_key = groups.internal_key
            where {where_sql}
            group by
                groups.internal_key, groups.detail_key, groups.group_kind,
                groups.zone, groups.member_ids, groups.member_types,
                groups.scope_month, groups.updated_at,
                groups.external_etc_batch_id, groups.missing_row_types
        """

    @staticmethod
    def _initial_zone_ctes(prefix: str, plan: dict[str, Any]) -> str:
        if plan["uses_unfiltered_zone_counts"]:
            exact_totals_sql = f"""
                select summary_{prefix}_count::bigint as total_count
                from overall_group_summary
            """
            exact_row_counts_sql = f"""
                select
                    count(*) filter (
                        where member.in_{prefix} and member.row_type = 'oa'
                    )::bigint as oa_count,
                    count(*) filter (
                        where member.in_{prefix} and member.row_type = 'bank'
                    )::bigint as bank_count,
                    count(*) filter (
                        where member.in_{prefix} and member.row_type = 'invoice'
                    )::bigint as invoice_count
                from overall_unique_members member
            """
        else:
            exact_totals_sql = f"""
                select count(*)::bigint as total_count
                from {prefix}_keyed_groups
            """
            exact_row_counts_sql = f"""
                select
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'oa')::bigint as oa_count,
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'bank')::bigint as bank_count,
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'invoice')::bigint as invoice_count
                from {prefix}_keyed_groups groups
                left join canonical_group_members member
                  on member.internal_key = groups.internal_key
            """
        filtered_groups_select_sql = (
            PostgresWorkbenchPageQueryRepository._filtered_groups_select_sql(
                where_sql=str(plan["where_sql"]),
                normalized_sort=str(plan["sort"]),
            )
        )
        return f"""
            {plan['search_ctes']}
            {prefix}_filtered_groups as materialized (
                {filtered_groups_select_sql}
            ),
            {prefix}_keyed_groups as materialized (
                select filtered.*,
                       ({plan['sort_expression']}) is null as sort_missing,
                       coalesce(({plan['sort_expression']})::text, '') as sort_value
                from {prefix}_filtered_groups filtered
            ),
            {prefix}_page_groups as materialized (
                select keyed.*,
                       row_number() over (order by {plan['order_sql']}) as page_position
                from {prefix}_keyed_groups keyed
                order by {plan['order_sql']}
                limit %s
            ),
            {prefix}_exact_totals as materialized (
                {exact_totals_sql}
            ),
            {prefix}_exact_row_counts as materialized (
                {exact_row_counts_sql}
            )
        """

    @staticmethod
    def _initial_zone_output_sql(prefix: str) -> str:
        return f"""
            select
                '{prefix}'::text as record_zone,
                page.internal_key,
                page.detail_key,
                page.group_kind,
                page.zone,
                page.member_ids,
                page.member_types,
                page.scope_month,
                page.updated_at,
                page.external_etc_batch_id,
                page.missing_row_types,
                page.sort_missing,
                page.sort_value,
                page.page_position,
                totals.total_count,
                row_counts.oa_count,
                row_counts.bank_count,
                row_counts.invoice_count,
                null::bigint as summary_oa_count,
                null::bigint as summary_bank_count,
                null::bigint as summary_invoice_count,
                null::bigint as summary_paired_count,
                null::bigint as summary_unpaired_count,
                null::bigint as incomplete_group_count,
                null::bigint as missing_oa_group_count,
                null::bigint as missing_bank_group_count,
                null::bigint as missing_invoice_group_count,
                null::bigint as expense_transaction_count,
                null::bigint as income_transaction_count,
                null::bigint as input_invoice_count,
                null::bigint as output_invoice_count,
                null::bigint as paired_oa_count,
                null::bigint as paired_bank_count,
                null::bigint as paired_invoice_count,
                null::bigint as inventory_system_total,
                null::bigint as inventory_manual_import_total,
                null::bigint as inventory_workbench_visible_total,
                null::bigint as inventory_hidden_submitted_etc_total,
                null::bigint as inventory_extra_etc_total,
                null::bigint as inventory_oa_attachment_total,
                null::bigint as inventory_etc_summary_batch_count,
                null::bigint as unpaired_exception_count,
                null::bigint as paired_exception_count
            from {prefix}_exact_totals totals
            cross join {prefix}_exact_row_counts row_counts
            left join {prefix}_page_groups page on true
        """

    def _initial_zone_payload(
        self,
        *,
        scope_key: str,
        plan: dict[str, Any],
        rows: list[dict[str, Any]],
        visible_descriptors: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = (rows[0] if rows else {}) or {}
        has_more = sum(
            1 for row in rows if str(row.get("internal_key") or "").strip()
        ) > WORKBENCH_GROUP_PAGE_SIZE
        next_cursor = None
        if has_more and visible_descriptors:
            last = visible_descriptors[-1]
            next_cursor = encode_workbench_page_cursor(
                WorkbenchPageCursor(
                    query_hash=str(plan["query_hash"]),
                    sort=str(plan["sort"]),
                    missing=bool(last.get("sort_missing")),
                    value=str(last.get("sort_value") or ""),
                    group_key=str(last.get("internal_key") or ""),
                )
            )
        oa_count = int_value(metadata.get("oa_count"), 0)
        bank_count = int_value(metadata.get("bank_count"), 0)
        invoice_count = int_value(metadata.get("invoice_count"), 0)
        return {
            "month": scope_key,
            "scope_key": scope_key,
            "zone": str(plan["zone"]),
            "page_size": WORKBENCH_GROUP_PAGE_SIZE,
            "total": int_value(metadata.get("total_count"), 0),
            "row_counts": {
                "oa": oa_count,
                "bank": bank_count,
                "invoice": invoice_count,
                "rows": oa_count + bank_count + invoice_count,
            },
            "has_more": has_more,
            "next_cursor": next_cursor,
            "groups": groups,
        }

    def _groups_page(
        self,
        *,
        scope_key: str,
        zone: str,
        cursor: str | None = None,
        page_size: int | str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: Any = None,
        time_filters: Any = None,
        exception_bucket: str | None = None,
        exception_view: str | None = None,
        exception_code: str | None = None,
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        normalized_zone = str(zone or "").strip()
        if normalized_zone not in {"paired", "unpaired"}:
            raise ValueError("zone must be paired or unpaired.")
        normalized_page_size = self._page_size(
            page_size,
            default=WORKBENCH_GROUP_PAGE_SIZE,
        )
        normalized_detail_level = self._detail_level(detail_level)
        normalized_status = self._status(status)
        normalized_source_kind = self._source_kind(source_kind)
        normalized_search = self._search(search)
        normalized_sort, direction, sort_expression = self._group_sort(sort)
        normalized_columns = normalize_workbench_column_filters(column_filters)
        normalized_times = normalize_workbench_time_filters(time_filters)
        normalized_exception_bucket = text(exception_bucket)
        if normalized_exception_bucket not in {None, "unpaired", "paired"}:
            raise ValueError("exception_bucket must be unpaired or paired.")
        if (
            normalized_exception_bucket is not None
            and normalized_exception_bucket != normalized_zone
        ):
            raise ValueError("exception_bucket must match zone.")
        normalized_exception_view = text(exception_view)
        if normalized_exception_view not in {None, *EXCEPTION_VIEWS}:
            raise ValueError("exception_view must be amount or document_only.")
        normalized_exception_code = text(exception_code)
        if normalized_exception_code not in {None, *AMOUNT_EXCEPTION_CODES}:
            raise ValueError("exception_code must be a supported amount exception code.")
        if normalized_exception_view is not None and normalized_exception_bucket is None:
            raise ValueError("exception_view requires exception_bucket.")
        if normalized_exception_code is not None and normalized_exception_view != "amount":
            raise ValueError("exception_code requires exception_view=amount.")
        normalized_query = {
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "status": normalized_status,
            "source_kind": normalized_source_kind,
            "search": normalized_search,
            "sort": normalized_sort,
            "column_filters": normalized_columns,
            "time_filters": normalized_times,
            "exception_bucket": normalized_exception_bucket,
        }
        if normalized_exception_view is not None:
            normalized_query["exception_view"] = normalized_exception_view
        if normalized_exception_code is not None:
            normalized_query["exception_code"] = normalized_exception_code
        query_hash = workbench_query_hash(normalized_query)
        decoded_cursor = decode_workbench_page_cursor(
            cursor,
            expected_query_hash=query_hash,
            expected_sort=normalized_sort,
        )
        cursor_exception_code = text(decoded_cursor.partition) if decoded_cursor else None
        if cursor_exception_code is not None and (
            normalized_exception_view != "amount"
            or normalized_exception_code is not None
            or cursor_exception_code not in AMOUNT_EXCEPTION_CODES
        ):
            raise WorkbenchPageCursorError("cursor exception partition is invalid.")
        search_ctes, search_params, search_hit_name = self._source_search_hit_ctes(
            prefix="groups",
            search=normalized_search,
        )
        bank_tag_row_ids = self._resolve_bank_tag_filter_row_ids(
            scope_key=normalized_scope,
            zone=normalized_zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=normalized_exception_bucket,
        )
        where_sql, where_params = self._group_filters(
            zone=normalized_zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            search_hit_name=search_hit_name,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=normalized_exception_bucket,
            bank_tag_row_ids=bank_tag_row_ids,
        )
        cursor_sql, cursor_params = self._group_cursor_filter(
            decoded_cursor,
            direction=direction,
        )
        order_sql = self._group_order_sql(direction)
        filtered_group_cte_name = "filtered_groups"
        exception_query_cte_sql = ""
        exception_filter_ctes_sql = ""
        exception_select_sql = ""
        exception_join_sql = ""
        exception_params: list[Any] = []
        if normalized_exception_bucket is not None:
            filtered_group_cte_name = "base_filtered_groups"
            exception_query_cte_sql = """
            exception_query as materialized (
                select
                    nullif(%s::text, '') as exception_view,
                    nullif(%s::text, '') as requested_exception_code,
                    nullif(%s::text, '') as cursor_exception_code
            ),
            """
            exception_filter_ctes_sql = f"""
            exception_counts as materialized (
                select
                    count(anomaly.internal_key)::bigint as exception_total,
                    count(*) filter (
                        where anomaly.exception_code is not null
                    )::bigint as amount_exception_total,
                    count(*) filter (
                        where anomaly.exception_code is null
                          and anomaly.has_document_anomaly
                    )::bigint as document_only_exception_total,
                    {_AMOUNT_EXCEPTION_COUNT_COLUMNS_SQL}
                from base_filtered_groups groups
                left join anomaly_states anomaly
                  on anomaly.internal_key = groups.internal_key
            ),
            selected_exception as materialized (
                select case
                    when query.exception_view is distinct from 'amount' then null
                    when query.requested_exception_code is not null
                        then query.requested_exception_code
                    when query.cursor_exception_code is not null
                        then query.cursor_exception_code
                    {_DEFAULT_AMOUNT_EXCEPTION_CODE_SQL}
                    else null
                end as exception_code
                from exception_counts counts
                cross join exception_query query
            ),
            filtered_groups as materialized (
                select groups.*
                from base_filtered_groups groups
                cross join exception_query query
                cross join selected_exception selected
                left join anomaly_states anomaly
                  on anomaly.internal_key = groups.internal_key
                where query.exception_view is null
                   or (
                        query.exception_view = 'amount'
                        and selected.exception_code is not null
                        and anomaly.exception_code = selected.exception_code
                   )
                   or (
                        query.exception_view = 'document_only'
                        and anomaly.exception_code is null
                        and anomaly.has_document_anomaly
                   )
            ),
            """
            exception_select_sql = """,
                   exception_counts.*,
                   selected_exception.exception_code as selected_exception_code"""
            exception_join_sql = """
            cross join exception_counts
            cross join selected_exception
            """
            exception_params = [
                normalized_exception_view,
                normalized_exception_code,
                cursor_exception_code,
            ]
        filtered_groups_select_sql = self._filtered_groups_select_sql(
            where_sql=where_sql,
            normalized_sort=normalized_sort,
        )
        rows = self._connection.fetch_all(
            f"""
            with recursive {_SCOPED_CANONICAL_GROUPS_CTE},
            {search_ctes}
            {_ANOMALY_STATE_CTES},
            {_EFFECTIVE_GROUPS_CTES},
            {exception_query_cte_sql}
            {filtered_group_cte_name} as materialized (
                {filtered_groups_select_sql}
            ),
            {exception_filter_ctes_sql}
            keyed_groups as materialized (
                select filtered_groups.*,
                       ({sort_expression}) is null as sort_missing,
                       coalesce(({sort_expression})::text, '') as sort_value
                from filtered_groups
            ),
            page_groups as materialized (
                select keyed_groups.*,
                       row_number() over (order by {order_sql}) as page_position
                from keyed_groups
                where true {cursor_sql}
                order by {order_sql}
                limit %s
            ),
            exact_totals as (
                select count(*)::bigint as total_count
                from keyed_groups
            ),
            exact_row_counts as (
                select
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'oa')::bigint as oa_count,
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'bank')::bigint as bank_count,
                    count(distinct (member.row_type, member.row_id))
                        filter (where member.row_type = 'invoice')::bigint as invoice_count
                from keyed_groups groups
                left join canonical_group_members member
                  on member.internal_key = groups.internal_key
            )
            select page_groups.*,
                   exact_totals.total_count,
                   exact_row_counts.oa_count,
                   exact_row_counts.bank_count,
                   exact_row_counts.invoice_count
                   {exception_select_sql}
            from exact_totals
            cross join exact_row_counts
            {exception_join_sql}
            left join page_groups on true
            order by page_groups.page_position nulls last
            """,
            tuple(
                [
                    *self._scope_params(normalized_scope),
                    *search_params,
                    *exception_params,
                    *where_params,
                    *cursor_params,
                    normalized_page_size + 1,
                ]
            ),
        )
        metadata = rows[0] if rows else {}
        resolved_exception_code = text(metadata.get("selected_exception_code"))
        if resolved_exception_code not in AMOUNT_EXCEPTION_CODES:
            resolved_exception_code = None
        descriptor_rows = [
            row for row in rows if str(row.get("internal_key") or "").strip()
        ]
        visible_descriptors = descriptor_rows[:normalized_page_size]
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=visible_descriptors,
            detail_level=normalized_detail_level,
        )
        has_more = len(descriptor_rows) > normalized_page_size
        next_cursor = None
        if has_more and visible_descriptors:
            last = visible_descriptors[-1]
            next_cursor = encode_workbench_page_cursor(
                WorkbenchPageCursor(
                    query_hash=query_hash,
                    sort=normalized_sort,
                    missing=bool(last.get("sort_missing")),
                    value=str(last.get("sort_value") or ""),
                    group_key=str(last.get("internal_key") or ""),
                    partition=(
                        resolved_exception_code
                        if normalized_exception_view == "amount"
                        and normalized_exception_code is None
                        else None
                    ),
                )
            )
        oa_count = int_value(metadata.get("oa_count"), 0)
        bank_count = int_value(metadata.get("bank_count"), 0)
        invoice_count = int_value(metadata.get("invoice_count"), 0)
        exception_payload: dict[str, Any] = {}
        if normalized_exception_bucket is not None:
            exception_payload = {
                "selected_exception_code": resolved_exception_code,
                "exception_counts": {
                    "total": int_value(metadata.get("exception_total"), 0),
                    "amount_total": int_value(
                        metadata.get("amount_exception_total"),
                        0,
                    ),
                    "document_only": int_value(
                        metadata.get("document_only_exception_total"),
                        0,
                    ),
                    "by_code": {
                        code: int_value(metadata.get(f"exception_count_{code}"), 0)
                        for code in AMOUNT_EXCEPTION_CODES
                    },
                },
            }
        return {
            "month": normalized_scope,
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "page_size": normalized_page_size,
            "total": int_value(metadata.get("total_count"), 0),
            "row_counts": {
                "oa": oa_count,
                "bank": bank_count,
                "invoice": invoice_count,
                "rows": oa_count + bank_count + invoice_count,
            },
            "has_more": has_more,
            "next_cursor": next_cursor,
            "groups": groups,
            **exception_payload,
        }

    def _group_detail(
        self,
        *,
        scope_key: str,
        zone: str,
        group_id: str,
        detail_key: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope = self._scope_key(scope_key)
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        normalized_detail_key = str(detail_key or "").strip()
        if normalized_zone not in {"paired", "unpaired"} or not normalized_group_id:
            return None
        relation_case_id = (
            normalized_group_id.removeprefix("case:")
            if normalized_group_id.startswith("case:")
            else ""
        )
        if relation_case_id:
            rows = self._relation_descriptor_for_case(
                scope_key=normalized_scope,
                case_id=relation_case_id,
            )
        elif normalized_detail_key:
            detail_scope, detail_row_type, detail_row_id = self._parse_singleton_detail_key(
                normalized_detail_key
            )
            if normalized_scope != "all" and detail_scope != normalized_scope:
                return None
            rows = self._row_group_descriptors(
                scope_key=normalized_scope,
                row_id=detail_row_id,
                row_type=detail_row_type,
            )
        else:
            # A singleton display id is a digest, not a source key.  Requiring
            # detail_key keeps this lookup bounded and prevents a zone scan.
            return None
        if len(rows) != 1:
            return None
        descriptor = rows[0]
        if not relation_case_id:
            descriptor_scope = str(descriptor.get("scope_month") or "")[:7]
            if (
                str(descriptor.get("detail_key") or "") != normalized_detail_key
                or descriptor_scope != detail_scope
                or text_list(descriptor.get("member_ids")) != [detail_row_id]
                or text_list(descriptor.get("member_types")) != [detail_row_type]
            ):
                return None
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=rows,
            detail_level="full",
        )
        group = next(
            (
                payload
                for payload in groups
                if str(payload.get("group_id") or "") == normalized_group_id
                and str(payload.get("zone") or "") == normalized_zone
            ),
            None,
        )
        if not isinstance(group, dict):
            return None
        source_scope_key = str(descriptor.get("scope_month") or "")[:7]
        if source_scope_key:
            group["source_scope_key"] = source_scope_key
        return {
            "month": normalized_scope,
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "group_id": normalized_group_id,
            "source_scope_key": source_scope_key,
            "group": group,
        }

    def _row_detail(
        self,
        *,
        scope_key: str,
        row_id: str,
        row_type: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope = self._scope_key(scope_key)
        normalized_row_id = str(row_id or "").strip()
        normalized_row_type = str(row_type or "").strip().lower()
        if not normalized_row_id:
            return None
        if normalized_row_type not in {"oa", "bank", "invoice"}:
            raise ValueError("row_type must be oa, bank or invoice.")
        descriptors = self._row_group_descriptors(
            scope_key=normalized_scope,
            row_id=normalized_row_id,
            row_type=normalized_row_type,
        )
        if not descriptors:
            return None
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=[descriptors[0]],
            detail_level="full",
        )
        for group in groups:
            for row in self._group_rows(group):
                if str(row.get("id") or "") != normalized_row_id:
                    continue
                if normalized_row_type and str(row.get("type") or "") != normalized_row_type:
                    continue
                return {
                    "month": normalized_scope,
                    "scope_key": normalized_scope,
                    "row_id": normalized_row_id,
                    "row": row,
                }
        return None

    def _relation_descriptor_for_case(
        self,
        *,
        scope_key: str,
        case_id: str,
    ) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            f"""
            with requested_scope as (
                select
                    %s::text as scope_key,
                    case when %s::text = 'all' then null else %s::date end as scope_month,
                    %s::text as tenant_id
            ),
            selected_relation as materialized (
                select relation.*
                from app.workbench_pair_relations relation
                cross join requested_scope scope
                where relation.status = 'active'
                  and relation.case_id = %s
                  and (
                      scope.scope_key = 'all'
                      or relation.month_scope = scope.scope_month
                      or {self._relation_has_scoped_member_sql('relation')}
                  )
                limit 2
            )
            select
                'case:' || relation.case_id as internal_key,
                relation.case_id as detail_key,
                'relation'::text as group_kind,
                null::text as zone,
                relation.row_ids as member_ids,
                array(
                    select {self._normalized_member_type_sql('member.row_type')}
                    from unnest(relation.row_types) with ordinality
                        as member(row_type, ordinality)
                    order by member.ordinality
                )::text[] as member_types,
                relation.month_scope as scope_month,
                relation.updated_at,
                {_RELATION_EXTERNAL_BATCH_SQL} as external_etc_batch_id,
                array[]::text[] as missing_row_types
            from selected_relation relation
            order by relation.case_id
            """,
            tuple([*self._scope_params(scope_key), case_id]),
        )

    def _row_group_descriptors(
        self,
        *,
        scope_key: str,
        row_id: str,
        row_type: str | None,
    ) -> list[dict[str, Any]]:
        normalized_type = str(row_type or "").strip().lower()
        type_clause = "and target.row_type = %s" if normalized_type else ""
        params: list[Any] = [
            *self._scope_params(scope_key),
            row_id,
            row_id,
            row_id,
            row_id,
            row_id,
        ]
        if normalized_type:
            params.append(normalized_type)
        return self._connection.fetch_all(
            f"""
            with requested_scope as (
                select
                    %s::text as scope_key,
                    case when %s::text = 'all' then null else %s::date end as scope_month,
                    %s::text as tenant_id
            ),
            {_ETC_SUMMARY_IDENTITY_CTES},
            target_source_candidates as materialized (
                select
                    'oa'::text as row_type,
                    oa.row_id,
                    coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date)
                        as scope_month,
                    oa.updated_at,
                    null::text as external_etc_batch_id
                from app.oa_applications oa
                where oa.row_id = %s
                  and oa.status <> 'deleted'
                  and {_COMPLETED_OA_SQL}
                union all
                select
                    'oa'::text,
                    admission.oa_id,
                    (admission.scope_key || '-01')::date,
                    admission.updated_at,
                    null::text
                from app.oa_pending_payment_admissions admission
                where admission.tenant_id = (select tenant_id from requested_scope)
                  and admission.workflow_status = 'in_progress'
                  and admission.oa_id = %s
                union all
                select
                    'bank'::text,
                    coalesce(bank.legacy_mongo_id, bank.id::text),
                    bank.txn_month,
                    bank.updated_at,
                    null::text
                from app.bank_transactions bank
                where coalesce(bank.legacy_mongo_id, bank.id::text) = %s
                  and bank.status <> 'deleted'
                union all
                select
                    'invoice'::text,
                    coalesce(invoice.legacy_mongo_id, invoice.id::text),
                    invoice.invoice_month,
                    invoice.updated_at,
                    null::text
                from app.invoices invoice
                where coalesce(invoice.legacy_mongo_id, invoice.id::text) = %s
                  and {_VISIBLE_INVOICE_SQL}
                union all
                select
                    'invoice'::text,
                    summary.row_id,
                    summary.scope_month,
                    summary.updated_at,
                    summary.external_batch_id
                from etc_summary_keys summary
                cross join etc_summary_identity_guard guard
                where summary.row_id = %s
                  and guard.guard = 1
            ),
            target_oa_duplicate_ids as materialized (
                select target.row_id
                from target_source_candidates target
                where target.row_type = 'oa'
                group by target.row_id
                having count(*) > 1
            ),
            target_integrity_guard as materialized (
                select 1 / case when count(*) = 0 then 1 else 0 end as guard
                from target_oa_duplicate_ids
            ),
            target_sources as materialized (
                select target.*
                from target_source_candidates target
                cross join target_integrity_guard guard
                where guard.guard = 1
                  {type_clause}
            ),
            target_relations as materialized (
                select distinct relation.*
                from app.workbench_pair_relations relation
                cross join requested_scope scope
                join target_sources target on exists (
                    select 1
                    from unnest(relation.row_ids, relation.row_types)
                        with ordinality as member(member_id, member_type, ordinality)
                    where member.member_id = target.row_id
                      and {self._normalized_member_type_sql('member.member_type')}
                          = target.row_type
                )
                where relation.status = 'active'
                  and (
                      scope.scope_key = 'all'
                      or relation.month_scope = scope.scope_month
                      or {self._relation_has_scoped_member_sql('relation')}
                  )
            ),
            relation_descriptors as (
                select
                    'case:' || relation.case_id as internal_key,
                    relation.case_id as detail_key,
                    'relation'::text as group_kind,
                    null::text as zone,
                    relation.row_ids as member_ids,
                    array(
                        select {self._normalized_member_type_sql('member.row_type')}
                        from unnest(relation.row_types) with ordinality
                            as member(row_type, ordinality)
                        order by member.ordinality
                    )::text[] as member_types,
                    relation.month_scope as scope_month,
                    relation.updated_at,
                    {_RELATION_EXTERNAL_BATCH_SQL} as external_etc_batch_id,
                    array[]::text[] as missing_row_types
                from target_relations relation
            ),
            singleton_descriptors as (
                select
                    'row:' || target.row_type || ':' || target.row_id as internal_key,
                    'v1:' || to_char(target.scope_month, 'YYYY-MM') || ':' ||
                        target.row_type || ':' ||
                        encode(convert_to(target.row_id, 'UTF8'), 'hex') as detail_key,
                    'unpaired'::text as group_kind,
                    'unpaired'::text as zone,
                    array[target.row_id]::text[] as member_ids,
                    array[target.row_type]::text[] as member_types,
                    target.scope_month,
                    target.updated_at,
                    target.external_etc_batch_id,
                    array[]::text[] as missing_row_types
                from target_sources target
                cross join requested_scope scope
                where (scope.scope_key = 'all' or target.scope_month = scope.scope_month)
                  and not exists (select 1 from target_relations)
                  and not exists (
                      select 1
                      from app.workbench_row_overrides override
                      where override.status = 'active'
                        and override.row_type = target.row_type
                        and override.row_id = target.row_id
                        and coalesce(
                            (override.override_payload->>'ignored')::boolean,
                            override.override_payload->>'status' = 'ignored',
                            false
                        )
                  )
            )
            select * from relation_descriptors
            union all
            select * from singleton_descriptors
            order by group_kind, internal_key
            limit 4
            """,
            tuple(params),
        )

    @staticmethod
    def _parse_singleton_detail_key(detail_key: str) -> tuple[str, str, str]:
        parts = str(detail_key or "").split(":", 3)
        if len(parts) != 4 or parts[0] != "v1":
            raise ValueError("detail_key is not a valid Workbench singleton identity.")
        scope_key, row_type, encoded_row_id = parts[1:]
        if normalize_workbench_scope_key(scope_key) == "all":
            raise ValueError("detail_key must contain a concrete source month.")
        if row_type not in {"oa", "bank", "invoice"}:
            raise ValueError("detail_key contains an unsupported row type.")
        if not encoded_row_id or len(encoded_row_id) % 2:
            raise ValueError("detail_key contains an invalid row identity.")
        try:
            row_id = bytes.fromhex(encoded_row_id).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("detail_key contains an invalid row identity.") from error
        if not row_id or row_id.strip() != row_id:
            raise ValueError("detail_key contains an invalid row identity.")
        return scope_key, row_type, row_id

    def _filter_options(
        self,
        *,
        scope_key: str,
        zone: str,
        pane: str,
        facet: str = "column",
        column: str | None = None,
        option_search: str | None = None,
        cursor: str | None = None,
        page_size: int | str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        column_filters: Any = None,
        time_filters: Any = None,
        exception_bucket: str | None = None,
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        normalized_zone = str(zone or "").strip()
        if normalized_zone not in {"paired", "unpaired"}:
            raise ValueError("zone must be paired or unpaired.")
        normalized_pane, normalized_facet, normalized_column = (
            normalize_workbench_filter_option_target(
                pane=pane,
                facet=facet,
                column=column,
            )
        )
        normalized_page_size = self._page_size(
            page_size,
            default=WORKBENCH_FILTER_OPTION_PAGE_SIZE,
        )
        normalized_status = self._status(status)
        normalized_source_kind = self._source_kind(source_kind)
        normalized_search = self._search(search)
        normalized_columns = normalize_workbench_column_filters(column_filters)
        normalized_times = normalize_workbench_time_filters(time_filters)
        normalized_exception_bucket = text(exception_bucket)
        if normalized_exception_bucket not in {None, "unpaired", "paired"}:
            raise ValueError("exception_bucket must be unpaired or paired.")
        if normalized_facet == "column" and normalized_column is not None:
            pane_filters = dict(normalized_columns.get(normalized_pane, {}))
            pane_filters.pop(normalized_column, None)
            normalized_columns = dict(normalized_columns)
            if pane_filters:
                normalized_columns[normalized_pane] = pane_filters
            else:
                normalized_columns.pop(normalized_pane, None)
        else:
            normalized_times = dict(normalized_times)
            normalized_times.pop(normalized_pane, None)
        normalized_option_search = str(option_search or "").strip()
        if len(normalized_option_search) > 100:
            raise ValueError("option_search must not exceed 100 characters.")
        normalized_query = {
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "pane": normalized_pane,
            "facet": normalized_facet,
            "column": normalized_column,
            "option_search": normalized_option_search,
            "status": normalized_status,
            "source_kind": normalized_source_kind,
            "search": normalized_search,
            "column_filters": normalized_columns,
            "time_filters": normalized_times,
            "exception_bucket": normalized_exception_bucket,
        }
        cursor_sort = "filter-option:asc"
        query_hash = workbench_query_hash(normalized_query)
        decoded_cursor = decode_workbench_page_cursor(
            cursor,
            expected_query_hash=query_hash,
            expected_sort=cursor_sort,
        )
        search_ctes, search_params, search_hit_name = self._source_search_hit_ctes(
            prefix="options",
            search=normalized_search,
        )
        bank_tag_row_ids = self._resolve_bank_tag_filter_row_ids(
            scope_key=normalized_scope,
            zone=normalized_zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=normalized_exception_bucket,
        )
        where_sql, where_params = self._group_filters(
            zone=normalized_zone,
            status=normalized_status,
            source_kind=normalized_source_kind,
            search=normalized_search,
            search_hit_name=search_hit_name,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            exception_bucket=normalized_exception_bucket,
            bank_tag_row_ids=bank_tag_row_ids,
        )
        if (normalized_pane, normalized_column) in _COMPOSITE_FILTER_OPTION_GROUPS:
            return self._composite_filter_options(
                scope_key=normalized_scope,
                zone=normalized_zone,
                pane=normalized_pane,
                column=str(normalized_column),
                option_search=normalized_option_search,
                page_size=normalized_page_size,
                decoded_cursor=decoded_cursor,
                query_hash=query_hash,
                cursor_sort=cursor_sort,
                search_ctes=search_ctes,
                search_params=search_params,
                where_sql=where_sql,
                where_params=where_params,
                column_filters=normalized_columns,
                time_filters=normalized_times,
                bank_tag_row_ids=bank_tag_row_ids,
            )
        if normalized_facet == "time_year":
            value_sql = "to_char(member.sort_date, 'YYYY')"
        else:
            assert normalized_column is not None
            value_sql = (
                "case when coalesce(nullif(btrim(member.column_values->>"
                f"'{normalized_column}'), ''), '') in ('', '--', '—') "
                f"then '{WORKBENCH_FILTER_MISSING_VALUE}' "
                f"else btrim(member.column_values->>'{normalized_column}') end"
            )
        member_filter_sql, member_filter_params = self._target_member_filters(
            pane=normalized_pane,
            column_filters=normalized_columns,
            time_filters=normalized_times,
            alias="member",
        )
        option_search_sql = ""
        option_search_params: list[Any] = []
        if normalized_option_search:
            option_search_sql = "and facet_label ilike %s escape E'\\\\'"
            option_search_params.append(_literal_ilike_pattern(normalized_option_search))
        cursor_sql = ""
        cursor_params: list[Any] = []
        if decoded_cursor is not None:
            cursor_sql = (
                "and (facet_label > %s or (facet_label = %s and facet_value > %s))"
            )
            cursor_params = [
                decoded_cursor.value,
                decoded_cursor.value,
                decoded_cursor.group_key,
            ]
        rows = self._connection.fetch_all(
            f"""
            with recursive {_SCOPED_CANONICAL_GROUPS_CTE},
            {search_ctes}
            {_FILTER_OPTION_ANOMALY_STATE_CTES},
            {_EFFECTIVE_GROUPS_CTES},
            filtered_groups as materialized (
                select groups.internal_key
                from effective_groups groups
                where {where_sql}
            ),
            facet_values as materialized (
                select {value_sql} as facet_value
                from canonical_group_members member
                join filtered_groups groups
                  on groups.internal_key = member.internal_key
                where member.row_type = %s
                  {member_filter_sql}
            ),
            normalized_values as materialized (
                select distinct
                    facet_value,
                    case when facet_value = %s then '未填写' else facet_value end as facet_label
                from facet_values
                where facet_value is not null
                  and facet_value not in ('', '--', '—')
            )
            select facet_value, facet_label
            from normalized_values
            where true
              {option_search_sql}
              {cursor_sql}
            order by facet_label, facet_value
            limit %s
            """,
            tuple(
                [
                    *self._scope_params(normalized_scope),
                    *search_params,
                    normalized_pane,
                    *where_params,
                    normalized_pane,
                    *member_filter_params,
                    WORKBENCH_FILTER_MISSING_VALUE,
                    *option_search_params,
                    *cursor_params,
                    normalized_page_size + 1,
                ]
            ),
        )
        visible_rows = rows[:normalized_page_size]
        options = [
            {
                "value": str(row.get("facet_value") or ""),
                "label": str(row.get("facet_label") or ""),
                "missing": str(row.get("facet_value") or "")
                == WORKBENCH_FILTER_MISSING_VALUE,
            }
            for row in visible_rows
            if str(row.get("facet_value") or "")
        ]
        has_more = len(rows) > normalized_page_size
        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = encode_workbench_page_cursor(
                WorkbenchPageCursor(
                    query_hash=query_hash,
                    sort=cursor_sort,
                    missing=False,
                    value=str(last.get("facet_label") or ""),
                    group_key=str(last.get("facet_value") or ""),
                )
            )
        return {
            "month": normalized_scope,
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "pane": normalized_pane,
            "facet": normalized_facet,
            "column": normalized_column,
            "page_size": normalized_page_size,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "options": options,
        }

    def _composite_filter_options(
        self,
        *,
        scope_key: str,
        zone: str,
        pane: str,
        column: str,
        option_search: str,
        page_size: int,
        decoded_cursor: WorkbenchPageCursor | None,
        query_hash: str,
        cursor_sort: str,
        search_ctes: str,
        search_params: list[Any],
        where_sql: str,
        where_params: list[Any],
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
        bank_tag_row_ids: list[str] | None,
    ) -> dict[str, Any]:
        member_filter_sql, member_filter_params = self._target_member_filters(
            pane=pane,
            column_filters=column_filters,
            time_filters=time_filters,
            alias="member",
            bank_tag_row_ids=bank_tag_row_ids,
        )
        rows = self._connection.fetch_all(
            f"""
            with recursive {_SCOPED_CANONICAL_GROUPS_CTE},
            {search_ctes}
            {_FILTER_OPTION_ANOMALY_STATE_CTES},
            {_EFFECTIVE_GROUPS_CTES},
            filtered_groups as materialized (
                select groups.internal_key
                from effective_groups groups
                where {where_sql}
            )
            select distinct on (member.row_id)
                member.row_id,
                member.column_values,
                member.oa_expense_items
            from canonical_group_members member
            join filtered_groups groups
              on groups.internal_key = member.internal_key
            where member.row_type = %s
              {member_filter_sql}
            order by member.row_id
            """,
            tuple(
                [
                    *self._scope_params(scope_key),
                    *search_params,
                    pane,
                    *where_params,
                    pane,
                    *member_filter_params,
                ]
            ),
        )
        groups = dict(_COMPOSITE_FILTER_OPTION_GROUPS[(pane, column)])
        ranks = {
            prefix: rank
            for rank, (prefix, _label) in enumerate(
                _COMPOSITE_FILTER_OPTION_GROUPS[(pane, column)]
            )
        }
        by_value: dict[str, dict[str, Any]] = {}

        def add_option(prefix: str, raw_value: object, label: object | None = None) -> None:
            value = str(raw_value or "").strip()
            display_label = str(label if label is not None else value).strip()
            if not value or value in WORKBENCH_FILTER_PLACEHOLDERS or not display_label:
                return
            token = _grouped_filter_token(prefix, value)
            by_value[token] = {
                "value": token,
                "label": display_label,
                "missing": value == WORKBENCH_FILTER_MISSING_VALUE,
                "group": groups[prefix],
                "rank": ranks[prefix],
            }

        if pane == "bank":
            for row in rows:
                values = row.get("column_values")
                values = values if isinstance(values, dict) else {}
                direction = str(values.get("direction") or "").strip()
                if direction == "支出":
                    add_option("direction", "expense", "支出")
                elif direction == "收入":
                    add_option("direction", "income", "收入")
                add_option(
                    "account",
                    values.get("accountLast4"),
                    values.get("paymentAccount"),
                )
            row_ids = [
                row_id
                for row in rows
                if (row_id := str(row.get("row_id") or "").strip())
            ]
            if row_ids:
                settings = PostgresBankDetailsCanonicalQueryRepository.settings_payload(
                    self._connection
                )
                projections = (
                    PostgresBankDetailsCanonicalQueryRepository.workbench_category_projection_rows(
                        self._connection,
                        settings=settings,
                        transaction_ids=row_ids,
                        tenant_id=self._tenant_id,
                    )
                )
                for projection in projections.values():
                    label_path = [
                        str(item).strip()
                        for item in list(projection.get("category_label_path") or [])
                        if str(item).strip()
                    ]
                    add_option(
                        "bankTag",
                        projection.get("category_code"),
                        " / ".join(label_path)
                        or projection.get("category_label"),
                    )
        elif column == "applicant":
            # These are fixed user-facing filter dimensions, not data-derived
            # suggestions. Keep all four choices available even when the
            # current zone happens to contain only one type or workflow state.
            add_option("oaType", "支付申请", "支付申请")
            add_option("oaType", "日常报销", "日常报销")
            add_option("workflow", "completed", "已完成")
            add_option("workflow", "in_progress", "进行中")
            for row in rows:
                values = row.get("column_values")
                values = values if isinstance(values, dict) else {}
                add_option("oaType", values.get("applicationType"))
                workflow = str(values.get("workflowStatus") or "").strip()
                if workflow:
                    add_option(
                        "workflow",
                        workflow,
                        {"completed": "已完成", "in_progress": "进行中"}.get(
                            workflow,
                            workflow,
                        ),
                    )
                applicant = str(values.get("applicant") or "").strip()
                add_option(
                    "applicant",
                    applicant or WORKBENCH_FILTER_MISSING_VALUE,
                    applicant or "未填写",
                )
        else:
            for row in rows:
                values = row.get("column_values")
                values = values if isinstance(values, dict) else {}
                expense_items = row.get("oa_expense_items")
                expense_items = expense_items if isinstance(expense_items, list) else []
                if expense_items:
                    for item in expense_items:
                        if not isinstance(item, dict):
                            continue
                        project = str(
                            item.get("project_name") or item.get("projectName") or ""
                        ).strip()
                        expense_type = str(
                            item.get("expense_type") or item.get("expenseType") or ""
                        ).strip()
                        add_option("expenseType", expense_type)
                        add_option(
                            "project",
                            project or WORKBENCH_FILTER_MISSING_VALUE,
                            project or "未填写",
                        )
                else:
                    project = str(values.get("projectName") or "").strip()
                    add_option("expenseType", values.get("expenseType"))
                    add_option(
                        "project",
                        project or WORKBENCH_FILTER_MISSING_VALUE,
                        project or "未填写",
                    )

        normalized_search = option_search.casefold()
        ordered = [
            option
            for option in by_value.values()
            if not normalized_search
            or normalized_search in str(option["label"]).casefold()
            or normalized_search in str(option["group"]).casefold()
        ]
        ordered.sort(key=lambda option: (option["rank"], option["label"], option["value"]))
        if decoded_cursor is not None:
            ordered = [
                option
                for option in ordered
                if (f"{option['rank']:02d}|{option['label']}", option["value"])
                > (decoded_cursor.value, decoded_cursor.group_key)
            ]
        visible = ordered[:page_size]
        has_more = len(ordered) > page_size
        options = [
            {key: value for key, value in option.items() if key != "rank"}
            for option in visible
        ]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = encode_workbench_page_cursor(
                WorkbenchPageCursor(
                    query_hash=query_hash,
                    sort=cursor_sort,
                    missing=False,
                    value=f"{last['rank']:02d}|{last['label']}",
                    group_key=str(last["value"]),
                )
            )
        return {
            "month": scope_key,
            "scope_key": scope_key,
            "zone": zone,
            "pane": pane,
            "facet": "column",
            "column": column,
            "page_size": page_size,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "options": options,
        }

    @staticmethod
    def _summary_payload(
        *,
        metadata: dict[str, Any],
        paired: dict[str, Any],
        unpaired: dict[str, Any],
    ) -> dict[str, Any]:
        zone_counts = {
            "paired": dict(paired.get("row_counts") or {}),
            "unpaired": dict(unpaired.get("row_counts") or {}),
        }
        zone_counts["paired"]["groups"] = int_value(paired.get("total"), 0)
        zone_counts["unpaired"]["groups"] = int_value(unpaired.get("total"), 0)
        oa_count = int_value(metadata.get("summary_oa_count"), 0)
        bank_count = int_value(metadata.get("summary_bank_count"), 0)
        invoice_count = int_value(metadata.get("summary_invoice_count"), 0)
        paired_count = int_value(metadata.get("summary_paired_count"), 0)
        unpaired_count = int_value(metadata.get("summary_unpaired_count"), 0)
        return {
            "summary": {
                "oa_count": oa_count,
                "bank_count": bank_count,
                "invoice_count": invoice_count,
                "paired_count": paired_count,
                "unpaired_count": unpaired_count,
                "unpaired_exception_count": int_value(
                    metadata.get("unpaired_exception_count"), 0
                ),
                "paired_exception_count": int_value(
                    metadata.get("paired_exception_count"), 0
                ),
                "zone_counts": zone_counts,
            },
            "statistics": {
                "oa_count": oa_count,
                "bank_transaction_count": bank_count,
                "input_invoice_count": int_value(metadata.get("input_invoice_count"), 0),
                "output_invoice_count": int_value(metadata.get("output_invoice_count"), 0),
                "paired_group_count": paired_count,
                "unpaired_object_count": unpaired_count,
                "expense_transaction_count": int_value(
                    metadata.get("expense_transaction_count"), 0
                ),
                "income_transaction_count": int_value(
                    metadata.get("income_transaction_count"), 0
                ),
                "paired_oa_count": int_value(metadata.get("paired_oa_count"), 0),
                "paired_bank_transaction_count": int_value(
                    metadata.get("paired_bank_count"), 0
                ),
                "paired_invoice_count": int_value(metadata.get("paired_invoice_count"), 0),
                "incomplete_group_count": int_value(
                    metadata.get("incomplete_group_count"), 0
                ),
                "missing_oa_group_count": int_value(
                    metadata.get("missing_oa_group_count"), 0
                ),
                "missing_bank_group_count": int_value(
                    metadata.get("missing_bank_group_count"), 0
                ),
                "missing_invoice_group_count": int_value(
                    metadata.get("missing_invoice_group_count"), 0
                ),
            },
            "invoice_inventory": {
                "system_total": int_value(metadata.get("inventory_system_total"), 0),
                "manual_import_total": int_value(
                    metadata.get("inventory_manual_import_total"), 0
                ),
                "workbench_visible_total": int_value(
                    metadata.get("inventory_workbench_visible_total"), 0
                ),
                "hidden_submitted_etc_total": int_value(
                    metadata.get("inventory_hidden_submitted_etc_total"), 0
                ),
                "extra_etc_total": int_value(
                    metadata.get("inventory_extra_etc_total"), 0
                ),
                "etc_summary_batch_count": int_value(
                    metadata.get("inventory_etc_summary_batch_count"), 0
                ),
                "oa_attachment_total": int_value(
                    metadata.get("inventory_oa_attachment_total"), 0
                ),
            },
        }

    def _hydrate_groups(
        self,
        *,
        month: str,
        descriptors: list[dict[str, Any]],
        detail_level: str,
    ) -> list[dict[str, Any]]:
        return PostgresWorkbenchPageHydrationRepository(
            self._connection,
            tenant_id=self._tenant_id,
        ).hydrate_groups(
            scope_key=month,
            descriptors=descriptors,
            detail_level=detail_level,
        )

    @staticmethod
    def _normalized_member_type_sql(expression: str) -> str:
        return (
            f"case lower({expression}) "
            "when 'oa_application' then 'oa' "
            "when 'bank_transaction' then 'bank' "
            "when 'invoice_record' then 'invoice' "
            "when 'formal_invoice' then 'invoice' "
            "when 'input' then 'invoice' "
            "when 'input_invoice' then 'invoice' "
            "when 'output' then 'invoice' "
            "when 'output_invoice' then 'invoice' "
            "when 'etc_summary' then 'invoice' "
            f"else lower({expression}) end"
        )

    @classmethod
    def _relation_has_scoped_member_sql(cls, relation_alias: str) -> str:
        member_type = cls._normalized_member_type_sql("member.member_type")
        return f"""
            exists (
                select 1
                from unnest({relation_alias}.row_ids, {relation_alias}.row_types)
                    with ordinality as member(member_id, member_type, ordinality)
                where (
                    {member_type} = 'oa'
                    and (
                        exists (
                            select 1
                            from app.oa_applications scoped_oa
                            where scoped_oa.row_id = member.member_id
                              and scoped_oa.status <> 'deleted'
                              and {_COMPLETED_OA_SQL.replace('oa.', 'scoped_oa.')}
                              and coalesce(
                                  scoped_oa.scope_month,
                                  date_trunc('month', scoped_oa.application_date)::date
                              ) = scope.scope_month
                        )
                        or exists (
                            select 1
                            from app.oa_pending_payment_admissions scoped_pending
                            where scoped_pending.tenant_id = scope.tenant_id
                              and scoped_pending.workflow_status = 'in_progress'
                              and scoped_pending.oa_id = member.member_id
                              and (scoped_pending.scope_key || '-01')::date = scope.scope_month
                        )
                    )
                )
                or (
                    {member_type} = 'bank'
                    and exists (
                        select 1
                        from app.bank_transactions scoped_bank
                        where coalesce(scoped_bank.legacy_mongo_id, scoped_bank.id::text)
                            = member.member_id
                          and scoped_bank.status <> 'deleted'
                          and scoped_bank.txn_month = scope.scope_month
                    )
                )
                or (
                    {member_type} = 'invoice'
                    and exists (
                        select 1
                        from app.invoices scoped_invoice
                        where coalesce(
                            scoped_invoice.legacy_mongo_id,
                            scoped_invoice.id::text
                        ) = member.member_id
                          and {_visible_invoice_sql('scoped_invoice')}
                          and scoped_invoice.invoice_month = scope.scope_month
                    )
                )
            )
        """

    @staticmethod
    def _group_filters(
        *,
        zone: str,
        status: str | None,
        source_kind: str | None,
        search: str | None,
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
        exception_bucket: str | None = None,
        search_hit_name: str | None = None,
        bank_tag_row_ids: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        clauses = ["groups.zone = %s"]
        params: list[Any] = [zone]
        if normalized_status := text(status):
            # Canonical groups currently expose only the paired/unpaired status
            # contract.  Reject a contradictory legacy status without treating
            # it as a second, accidentally aliased zone predicate.
            if normalized_status != zone:
                clauses.append("false")
        if normalized_source := text(source_kind):
            clauses.append(
                "exists (select 1 from canonical_group_members source_member "
                "where source_member.internal_key = groups.internal_key "
                "and source_member.source_kind = %s)"
            )
            params.append(normalized_source)
        if normalized_search := text(search):
            if not search_hit_name:
                raise ValueError("Workbench search hit boundary is required.")
            clauses.append(
                "exists (select 1 from canonical_group_members search_member "
                f"join {search_hit_name} search_hit "
                "on search_hit.row_type = search_member.row_type "
                "and search_hit.row_id = search_member.row_id "
                "where search_member.internal_key = groups.internal_key)"
            )
        if normalized_exception_bucket := text(exception_bucket):
            if normalized_exception_bucket not in {"unpaired", "paired"}:
                raise ValueError("exception_bucket must be unpaired or paired.")
            if normalized_exception_bucket != zone:
                clauses.append("false")
            clauses.append(
                "exists (select 1 from anomaly_states anomaly "
                "where anomaly.internal_key = groups.internal_key)"
            )
        for pane in ("oa", "bank", "invoice"):
            pane_filters = column_filters.get(pane, {})
            time_filter = time_filters.get(pane)
            if not pane_filters and not time_filter:
                continue
            filter_clauses, filter_params = (
                PostgresWorkbenchPageQueryRepository._member_filter_clauses(
                    pane=pane,
                    pane_filters=pane_filters,
                    time_filter=time_filter,
                    alias="filter_member",
                    bank_tag_row_ids=bank_tag_row_ids,
                )
            )
            member_clauses = [
                "filter_member.internal_key = groups.internal_key",
                "filter_member.row_type = %s",
                *filter_clauses,
            ]
            member_params: list[Any] = [pane, *filter_params]
            clauses.append(
                "exists (select 1 from canonical_group_members filter_member where "
                + " and ".join(member_clauses)
                + ")"
            )
            params.extend(member_params)
        return " and ".join(clauses), params

    def _resolve_bank_tag_filter_row_ids(
        self,
        *,
        scope_key: str,
        zone: str,
        status: str | None,
        source_kind: str | None,
        search: str | None,
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
        exception_bucket: str | None,
    ) -> list[str] | None:
        selected_codes = _grouped_filter_values(
            column_filters.get("bank", {}).get("amount", []),
            "bankTag",
        )
        if not selected_codes:
            return None
        filters_without_tags = {
            pane: {column: list(values) for column, values in pane_filters.items()}
            for pane, pane_filters in column_filters.items()
        }
        bank_filters = filters_without_tags.get("bank", {})
        amount_values = [
            value
            for value in bank_filters.get("amount", [])
            if not value.startswith("bankTag:")
        ]
        if amount_values:
            bank_filters["amount"] = amount_values
        else:
            bank_filters.pop("amount", None)
        if not bank_filters:
            filters_without_tags.pop("bank", None)
        search_ctes, search_params, search_hit_name = self._source_search_hit_ctes(
            prefix="bank_tag_candidates",
            search=search,
        )
        where_sql, where_params = self._group_filters(
            zone=zone,
            status=status,
            source_kind=source_kind,
            search=search,
            search_hit_name=search_hit_name,
            column_filters=filters_without_tags,
            time_filters=time_filters,
            exception_bucket=exception_bucket,
        )
        member_filter_sql, member_filter_params = self._target_member_filters(
            pane="bank",
            column_filters=filters_without_tags,
            time_filters=time_filters,
            alias="member",
        )
        candidate_rows = self._connection.fetch_all(
            f"""
            with recursive {_SCOPED_CANONICAL_GROUPS_CTE},
            {search_ctes}
            {_FILTER_OPTION_ANOMALY_STATE_CTES},
            {_EFFECTIVE_GROUPS_CTES},
            filtered_groups as materialized (
                select groups.internal_key
                from effective_groups groups
                where {where_sql}
            )
            select distinct member.row_id
            from canonical_group_members member
            join filtered_groups groups
              on groups.internal_key = member.internal_key
            where member.row_type = 'bank'
              {member_filter_sql}
            order by member.row_id
            """,
            tuple(
                [
                    *self._scope_params(scope_key),
                    *search_params,
                    "bank",
                    *where_params,
                    *member_filter_params,
                ]
            ),
        )
        candidate_ids = [
            row_id
            for row in candidate_rows
            if (row_id := str(row.get("row_id") or "").strip())
        ]
        if not candidate_ids:
            return []
        settings = PostgresBankDetailsCanonicalQueryRepository.settings_payload(
            self._connection
        )
        projections = (
            PostgresBankDetailsCanonicalQueryRepository.workbench_category_projection_rows(
                self._connection,
                settings=settings,
                transaction_ids=candidate_ids,
                tenant_id=self._tenant_id,
            )
        )
        selected = set(selected_codes)
        return [
            row_id
            for row_id in candidate_ids
            if str((projections.get(row_id) or {}).get("category_code") or "")
            in selected
        ]

    @staticmethod
    def _source_search_hit_ctes(
        *,
        prefix: str,
        search: str | None,
    ) -> tuple[str, list[Any], str | None]:
        normalized = PostgresWorkbenchPageQueryRepository._search(search)
        if not normalized:
            return "", [], None
        if not prefix.replace("_", "").isalnum():
            raise ValueError("Invalid internal Workbench search prefix.")
        hit_name = f"{prefix}_source_search_hits"
        pattern = _literal_ilike_pattern(normalized)

        def text_predicates(expressions: list[str]) -> tuple[str, list[Any]]:
            return (
                " or ".join(
                    f"{expression} ilike %s escape E'\\\\'"
                    for expression in expressions
                ),
                [pattern for _expression in expressions],
            )

        amount: Decimal | None = None
        try:
            amount = Decimal(normalized.replace(",", ""))
        except (InvalidOperation, ValueError):
            pass
        search_date: str | None = None
        try:
            search_date = datetime.strptime(normalized, "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass

        oa_text, oa_params = text_predicates(
            [
                "oa.applicant",
                "oa.project_name",
                "oa.normalized_payload->>'workflow_no'",
            ]
        )
        pending_text, pending_params = text_predicates(
            [
                "pending.applicant",
                "pending.project_name_display",
                "pending.project_name",
                "pending.source_payload->>'apply_type'",
                "pending.source_payload->>'application_type'",
                "pending.source_payload->>'counterparty_name'",
                "pending.source_payload->>'reason'",
            ]
        )
        bank_text, bank_params = text_predicates(
            [
                "bank.counterparty_name_raw",
                "bank.account_no",
                "bank.account_name",
                "bank.summary",
                "bank.remark",
                "bank.project_id",
            ]
        )
        invoice_text, invoice_params = text_predicates(
            [
                "invoice.invoice_no",
                "invoice.invoice_code",
                "invoice.digital_invoice_no",
                "invoice.counterparty_name",
                "invoice.seller_name",
                "invoice.seller_tax_no",
                "invoice.buyer_name",
                "invoice.buyer_tax_no",
                "invoice.invoice_type",
            ]
        )
        etc_text, etc_params = text_predicates(
            [
                "summary.external_batch_id",
                "etc_batch.business_batch_id",
                "etc_batch.raw_payload->'normalized_payload'->>'submission_batch_id'",
                "etc_batch.raw_payload->'normalized_payload'->>'submissionBatchId'",
            ]
        )
        etc_predicates = [
            etc_text,
            """
            exists (
                select 1
                from app.etc_invoices etc_invoice
                where etc_invoice.business_batch_id = etc_batch.business_batch_id
                  and etc_invoice.status <> 'deleted'
                  and coalesce(etc_invoice.invoice_no, '') ilike %s escape E'\\\\'
            )
            """,
        ]
        etc_params.append(pattern)
        oa_predicates = [oa_text]
        pending_predicates = [pending_text]
        bank_predicates = [bank_text]
        invoice_predicates = [invoice_text]
        if amount is not None:
            oa_predicates.append("oa.amount = %s::numeric")
            pending_predicates.append("pending.amount = %s::numeric")
            bank_predicates.append("abs(bank.amount) = abs(%s::numeric)")
            invoice_predicates.append(
                "(invoice.amount = %s::numeric or invoice.total_with_tax = %s::numeric)"
            )
            oa_params.append(amount)
            pending_params.append(amount)
            bank_params.append(amount)
            invoice_params.extend([amount, amount])
            etc_predicates.append("etc_batch.total_amount = %s::numeric")
            etc_params.append(amount)
        if search_date is not None:
            oa_predicates.append(
                "(oa.application_date = %s::date or oa.approved_at::date = %s::date)"
            )
            pending_predicates.append(
                f"coalesce({pending_oa_application_date_sql('pending')}, "
                "(pending.scope_key || '-01')::date) = %s::date"
            )
            bank_predicates.append(
                "coalesce(bank.trade_time::date, bank.txn_date) = %s::date"
            )
            invoice_predicates.append("invoice.invoice_date = %s::date")
            oa_params.extend([search_date, search_date])
            pending_params.append(search_date)
            bank_params.append(search_date)
            invoice_params.append(search_date)

        return (
            f"""
            {hit_name} as materialized (
                select 'oa'::text as row_type, oa.row_id
                from app.oa_applications oa
                join needed_keys needed
                  on needed.row_type = 'oa' and needed.row_id = oa.row_id
                where oa.status <> 'deleted'
                  and {_COMPLETED_OA_SQL}
                  and ({' or '.join(oa_predicates)})
                union
                select 'oa'::text, pending.oa_id
                from app.oa_pending_payment_admissions pending
                join needed_keys needed
                  on needed.row_type = 'oa' and needed.row_id = pending.oa_id
                where pending.tenant_id = (select tenant_id from requested_scope)
                  and pending.workflow_status = 'in_progress'
                  and ({' or '.join(pending_predicates)})
                union
                select 'bank'::text,
                       coalesce(bank.legacy_mongo_id, bank.id::text)
                from app.bank_transactions bank
                join needed_keys needed
                  on needed.row_type = 'bank'
                 and needed.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
                where bank.status <> 'deleted'
                  and ({' or '.join(bank_predicates)})
                union
                select 'invoice'::text,
                       coalesce(invoice.legacy_mongo_id, invoice.id::text)
                from app.invoices invoice
                join needed_keys needed
                  on needed.row_type = 'invoice'
                 and needed.row_id = coalesce(invoice.legacy_mongo_id, invoice.id::text)
                where {_VISIBLE_INVOICE_SQL}
                  and ({' or '.join(invoice_predicates)})
                union
                select 'invoice'::text, summary.row_id
                from etc_summary_keys summary
                join needed_keys needed
                  on needed.row_type = 'invoice' and needed.row_id = summary.row_id
                left join app.etc_business_batches etc_batch
                  on coalesce(
                      nullif(etc_batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                      nullif(etc_batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                      nullif(etc_batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                      nullif(etc_batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                      etc_batch.business_batch_id
                  ) = summary.external_batch_id
                 and etc_batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                where ({' or '.join(etc_predicates)})
            ),
            """,
            [*oa_params, *pending_params, *bank_params, *invoice_params, *etc_params],
            hit_name,
        )

    @staticmethod
    def _target_member_filters(
        *,
        pane: str,
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
        alias: str,
        bank_tag_row_ids: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        clauses, params = PostgresWorkbenchPageQueryRepository._member_filter_clauses(
            pane=pane,
            pane_filters=column_filters.get(pane, {}),
            time_filter=time_filters.get(pane),
            alias=alias,
            bank_tag_row_ids=bank_tag_row_ids,
        )
        return ("and " + " and ".join(clauses), params) if clauses else ("", [])

    @staticmethod
    def _member_filter_clauses(
        *,
        pane: str,
        pane_filters: dict[str, list[str]],
        time_filter: dict[str, str] | None,
        alias: str,
        bank_tag_row_ids: list[str] | None,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, values in sorted(pane_filters.items()):
            if not values:
                continue
            if pane == "bank" and column == "amount":
                direction_keys = _grouped_filter_values(values, "direction")
                directions = [
                    direction
                    for key in direction_keys
                    if (direction := {"expense": "支出", "income": "收入"}.get(key))
                ]
                accounts = _grouped_filter_values(values, "account")
                bank_tags = _grouped_filter_values(values, "bankTag")
                if directions:
                    clauses.append(f"{alias}.column_values->>'direction' = any(%s::text[])")
                    params.append(directions)
                if accounts:
                    clauses.append(f"{alias}.column_values->>'accountLast4' = any(%s::text[])")
                    params.append(accounts)
                if bank_tags:
                    if bank_tag_row_ids is None:
                        raise ValueError("bank tag filters require canonical row resolution.")
                    if bank_tag_row_ids:
                        clauses.append(f"{alias}.row_id = any(%s::text[])")
                        params.append(bank_tag_row_ids)
                    else:
                        clauses.append("false")
                continue
            if pane == "oa" and column == "applicant":
                grouped_columns = (
                    ("oaType", "applicationType"),
                    ("workflow", "workflowStatus"),
                    ("applicant", "applicant"),
                )
                for prefix, source_column in grouped_columns:
                    selected = _grouped_filter_values(values, prefix)
                    concrete = [
                        value
                        for value in selected
                        if value != WORKBENCH_FILTER_MISSING_VALUE
                    ]
                    selected_clauses: list[str] = []
                    if concrete:
                        selected_clauses.append(
                            f"{alias}.column_values->>'{source_column}' = any(%s::text[])"
                        )
                        params.append(concrete)
                    if WORKBENCH_FILTER_MISSING_VALUE in selected:
                        selected_clauses.append(
                            f"coalesce(nullif(btrim({alias}.column_values->>'{source_column}'), ''), '') "
                            "in ('', '--', '—')"
                        )
                    if selected_clauses:
                        clauses.append("(" + " or ".join(selected_clauses) + ")")
                continue
            if pane == "oa" and column == "projectName":
                projects = _grouped_filter_values(values, "project")
                expense_types = _grouped_filter_values(values, "expenseType")
                item_clauses: list[str] = []
                parent_clauses: list[str] = []
                item_params: list[Any] = []
                parent_params: list[Any] = []
                if projects:
                    concrete_projects = [
                        value
                        for value in projects
                        if value != WORKBENCH_FILTER_MISSING_VALUE
                    ]
                    item_project_clauses: list[str] = []
                    parent_project_clauses: list[str] = []
                    if concrete_projects:
                        item_project_clauses.append(
                            "coalesce(nullif(btrim(expense.value->>'project_name'), ''), "
                            "nullif(btrim(expense.value->>'projectName'), '')) = any(%s::text[])"
                        )
                        parent_project_clauses.append(
                            f"{alias}.column_values->>'projectName' = any(%s::text[])"
                        )
                        item_params.append(concrete_projects)
                        parent_params.append(concrete_projects)
                    if WORKBENCH_FILTER_MISSING_VALUE in projects:
                        item_project_clauses.append(
                            "coalesce(nullif(btrim(expense.value->>'project_name'), ''), "
                            "nullif(btrim(expense.value->>'projectName'), ''), '') = ''"
                        )
                        parent_project_clauses.append(
                            f"coalesce(nullif(btrim({alias}.column_values->>'projectName'), ''), '') "
                            "in ('', '--', '—')"
                        )
                    item_clauses.append("(" + " or ".join(item_project_clauses) + ")")
                    parent_clauses.append(
                        "(" + " or ".join(parent_project_clauses) + ")"
                    )
                if expense_types:
                    item_clauses.append(
                        "coalesce(nullif(btrim(expense.value->>'expense_type'), ''), "
                        "nullif(btrim(expense.value->>'expenseType'), '')) = any(%s::text[])"
                    )
                    parent_clauses.append(
                        f"{alias}.column_values->>'expenseType' = any(%s::text[])"
                    )
                    item_params.append(expense_types)
                    parent_params.append(expense_types)
                if item_clauses:
                    clauses.append(
                        "((jsonb_typeof(" + alias + ".oa_expense_items) = 'array' "
                        "and jsonb_array_length(" + alias + ".oa_expense_items) > 0 "
                        "and exists (select 1 from jsonb_array_elements(" + alias
                        + ".oa_expense_items) expense(value) where "
                        + " and ".join(item_clauses)
                        + ")) or ((jsonb_typeof(" + alias + ".oa_expense_items) <> 'array' "
                        "or jsonb_array_length(" + alias + ".oa_expense_items) = 0) and "
                        + " and ".join(parent_clauses)
                        + "))"
                    )
                    params.extend([*item_params, *parent_params])
                continue
            concrete_values = [
                value for value in values if value != WORKBENCH_FILTER_MISSING_VALUE
            ]
            value_clauses: list[str] = []
            if concrete_values:
                value_clauses.append(f"{alias}.column_values->>%s = any(%s::text[])")
                params.extend([column, concrete_values])
            if WORKBENCH_FILTER_MISSING_VALUE in values:
                value_clauses.append(
                    f"coalesce(nullif(btrim({alias}.column_values->>%s), ''), '') "
                    "in ('', '--', '—')"
                )
                params.append(column)
            if value_clauses:
                clauses.append("(" + " or ".join(value_clauses) + ")")
        start_date, end_date = workbench_time_range(time_filter)
        if start_date and end_date:
            clauses.append(
                f"{alias}.sort_date >= %s::date and {alias}.sort_date < %s::date"
            )
            params.extend([start_date, end_date])
        return clauses, params

    @staticmethod
    def _group_sort(sort: str | None) -> tuple[str, str, str]:
        normalized = str(sort or "").strip().lower()
        mapping = {
            "oa:asc": ("oa:asc", "asc", "oa_sort_min"),
            "oa:desc": ("oa:desc", "desc", "oa_sort_max"),
            "bank:asc": ("bank:asc", "asc", "bank_sort_min"),
            "bank:desc": ("bank:desc", "desc", "bank_sort_max"),
            "invoice:asc": ("invoice:asc", "asc", "invoice_sort_min"),
            "invoice:desc": ("invoice:desc", "desc", "invoice_sort_max"),
        }
        if normalized in mapping:
            return mapping[normalized]
        if normalized:
            raise ValueError("sort is not supported.")
        return (
            "default:desc",
            "desc",
            "concat_ws('|', scope_month::text, "
            "to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD HH24:MI:SS.US'))",
        )

    @staticmethod
    def _page_size(value: int | str | None, *, default: int) -> int:
        if value is None or str(value).strip() == "":
            return default
        try:
            normalized = int(str(value).strip())
        except ValueError as error:
            raise ValueError("page_size must be an integer.") from error
        if normalized < 1:
            raise ValueError("page_size must be at least 1.")
        if normalized > WORKBENCH_GROUP_PAGE_SIZE_MAX:
            raise ValueError(
                f"page_size must not exceed {WORKBENCH_GROUP_PAGE_SIZE_MAX}."
            )
        return normalized

    @staticmethod
    def _detail_level(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return "summary"
        if normalized not in {"summary", "full"}:
            raise ValueError("detail_level must be summary or full.")
        return normalized

    @staticmethod
    def _status(value: object) -> str | None:
        normalized = text(value)
        if normalized is None:
            return None
        normalized = normalized.lower()
        if normalized not in {"paired", "unpaired"}:
            raise ValueError("status must be paired or unpaired.")
        return normalized

    @staticmethod
    def _source_kind(value: object) -> str | None:
        normalized = text(value)
        if normalized is None:
            return None
        if normalized == "bank":
            normalized = "bank_transaction"
        if normalized not in WORKBENCH_SOURCE_KINDS:
            raise ValueError("source_kind is not supported.")
        return normalized

    @staticmethod
    def _search(value: object) -> str | None:
        normalized = text(value)
        if normalized is None:
            return None
        if len(normalized) > WORKBENCH_SEARCH_QUERY_MAX_LENGTH:
            raise ValueError(
                f"search must be at most {WORKBENCH_SEARCH_QUERY_MAX_LENGTH} characters."
            )
        return normalized

    @staticmethod
    def _group_order_sql(direction: str) -> str:
        normalized = "asc" if direction == "asc" else "desc"
        return f"sort_missing asc, sort_value {normalized}, internal_key asc"

    @staticmethod
    def _group_cursor_filter(
        cursor: WorkbenchPageCursor | None,
        *,
        direction: str,
    ) -> tuple[str, list[Any]]:
        if cursor is None:
            return "", []
        operator = ">" if direction == "asc" else "<"
        return (
            "and (sort_missing > %s::boolean "
            "or (sort_missing = %s::boolean and sort_value "
            f"{operator} %s) "
            "or (sort_missing = %s::boolean and sort_value = %s and internal_key > %s))",
            [
                cursor.missing,
                cursor.missing,
                cursor.value,
                cursor.missing,
                cursor.value,
                cursor.group_key,
            ],
        )

    @staticmethod
    def _group_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
        return PostgresWorkbenchPageHydrationRepository.group_rows(group)

    @staticmethod
    def _scope_key(scope_key: str | None) -> str:
        return normalize_workbench_scope_key(scope_key)

    def _scope_params(self, scope_key: str) -> list[Any]:
        normalized = self._scope_key(scope_key)
        return [
            normalized,
            normalized,
            None if normalized == "all" else month_start(normalized),
            self._tenant_id,
        ]

    @staticmethod
    def _page_query(value: dict[str, Any] | None) -> dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        return {
            key: payload[key]
            for key in (
                "status",
                "source_kind",
                "search",
                "sort",
                "column_filters",
                "time_filters",
                "exception_bucket",
            )
            if key in payload
        }
