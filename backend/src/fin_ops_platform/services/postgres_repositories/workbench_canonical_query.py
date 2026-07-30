from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    int_value,
    month_start,
    row_payload,
    text,
    text_list,
)
from fin_ops_platform.services.postgres_repositories.read_models import (
    _compact_workbench_group_for_summary_page,
    _filter_workbench_group_preview_rows_for_criteria,
    _normalize_workbench_column_filters,
    _normalize_workbench_time_filters,
    _with_workbench_group_counts,
)
from fin_ops_platform.services.workbench_relation_preview_policy import (
    WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS,
    WorkbenchRelationPreviewSelectionError,
)
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
)


_COMPLETED_OA_SQL = """
(
    oa.workflow_status is null
    or oa.workflow_status = ''
    or oa.workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
)
"""

_RETIRED_PAGE_RUNTIME_FIELDS = frozenset(
    {
        "active_generation_id",
        "freshness_targets",
        "operation_barrier_targets",
        "read_model_scope_keys",
        "read_model_scope_source_versions",
        "read_model_stale_reasons",
        "read_model_status",
        "read_model_version",
        "refresh_enqueued",
        "source_versions",
    }
)

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

_CANONICAL_GROUPS_CTE = f"""
requested_scope as (
    select
        %s::text as scope_key,
        case when %s::text = 'all' then null else %s::date end as scope_month
),
active_relations as materialized (
    select
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
    where relation.status = 'active'
),
invoice_candidates as materialized (
    select
        coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
        invoice.invoice_month as scope_month,
        case
            when exists (
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
            )
            then 'oa_attachment_invoice'
            else 'invoice'
        end as source_kind,
        invoice.invoice_type,
        invoice.invoice_no,
        invoice.invoice_code,
        invoice.digital_invoice_no,
        invoice.invoice_date,
        invoice.seller_name,
        invoice.seller_tax_no,
        invoice.buyer_name,
        invoice.buyer_tax_no,
        invoice.amount,
        invoice.tax_rate,
        invoice.tax_amount,
        invoice.total_with_tax,
        invoice.tags,
        invoice.source_links,
        invoice.raw_payload,
        invoice.updated_at,
        case
            when nullif(invoice.digital_invoice_no, '') is not null
                then 'digital:' || invoice.digital_invoice_no
            when nullif(invoice.invoice_code, '') is not null
             and nullif(invoice.invoice_no, '') is not null
                then 'code-no:' || invoice.invoice_code || ':' || invoice.invoice_no
            else 'row:' || coalesce(invoice.legacy_mongo_id, invoice.id::text)
        end as hard_identity,
        exists (
            select 1
            from active_relations relation
            where coalesce(invoice.legacy_mongo_id, invoice.id::text) = any(relation.row_ids)
        ) as active_relation_member
    from app.invoices invoice
    where {_VISIBLE_INVOICE_SQL}
),
ranked_invoices as materialized (
    select
        candidate.*,
        row_number() over (
            partition by candidate.hard_identity
            order by
                candidate.active_relation_member desc,
                case when candidate.source_kind = 'invoice' then 0 else 1 end,
                candidate.row_id
        ) as identity_rank
    from invoice_candidates candidate
),
etc_link_batch_keys as materialized (
    select
        coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            link.business_batch_id
        ) as external_batch_id,
        coalesce(batch.scope_month, invoice.invoice_month) as scope_month,
        greatest(coalesce(batch.updated_at, invoice.updated_at), invoice.updated_at) as updated_at
    from app.etc_batch_invoice_links link
    join app.invoices invoice
      on invoice.id = link.invoice_id
    left join app.etc_business_batches batch
      on batch.business_batch_id = link.business_batch_id
    where link.link_status = 'active'
      and invoice.status <> 'deleted'
),
etc_business_batch_keys as materialized (
    select
        coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            batch.business_batch_id
        ) as external_batch_id,
        batch.scope_month,
        greatest(batch.updated_at, max(invoice.updated_at)) as updated_at
    from app.etc_business_batches batch
    join lateral jsonb_array_elements_text(
        case when jsonb_typeof(batch.raw_payload->'normalized_payload'->'invoice_ids') = 'array'
             then batch.raw_payload->'normalized_payload'->'invoice_ids'
             else '[]'::jsonb end
    ) member(invoice_id) on true
    join app.etc_invoices invoice
      on invoice.etc_invoice_id = member.invoice_id
      or coalesce(invoice.legacy_mongo_id, '') = member.invoice_id
    where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
      and invoice.status <> 'deleted'
    group by external_batch_id, batch.scope_month, batch.updated_at
),
etc_submission_batch_keys as materialized (
    select
        coalesce(
            nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
            submission.submission_batch_id
        ) as external_batch_id,
        invoice.invoice_month as scope_month,
        greatest(submission.updated_at, invoice.updated_at) as updated_at
    from app.etc_submission_batches submission
    join app.invoices invoice
      on submission.submission_batch_id = coalesce(
          invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
          ''
      )
      or coalesce(
          nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
          submission.submission_batch_id
      ) = coalesce(
          invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
          ''
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
etc_batch_key_candidates as materialized (
    select external_batch_id, scope_month, updated_at
    from etc_link_batch_keys
    union all
    select business.external_batch_id, business.scope_month, business.updated_at
    from etc_business_batch_keys business
    where not exists (
        select 1
        from etc_link_batch_keys link
        where link.external_batch_id = business.external_batch_id
    )
    union all
    select submission.external_batch_id, submission.scope_month, submission.updated_at
    from etc_submission_batch_keys submission
    where not exists (
        select 1
        from etc_link_batch_keys link
        where link.external_batch_id = submission.external_batch_id
    )
      and not exists (
        select 1
        from etc_business_batch_keys business
        where business.external_batch_id = submission.external_batch_id
    )
),
etc_batch_keys as materialized (
    select
        candidate.external_batch_id,
        min(candidate.scope_month) as scope_month,
        max(candidate.updated_at) as updated_at
    from etc_batch_key_candidates candidate
    cross join requested_scope scope
    where scope.scope_key = 'all'
       or candidate.scope_month = scope.scope_month
    group by candidate.external_batch_id
),
canonical_rows as materialized (
    select
        oa.row_id,
        'oa'::text as pane,
        'oa'::text as source_kind,
        coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date) as scope_month,
        oa.application_date as sort_date,
        oa.updated_at,
        concat_ws(
            ' ',
            oa.row_id,
            oa.applicant,
            oa.project_name,
            oa.amount::text,
            oa.normalized_payload::text
        ) as searchable_text,
        jsonb_strip_nulls(jsonb_build_object(
            'applicant', oa.applicant,
            'applicationTime', oa.application_date::text,
            'projectName', oa.project_name,
            'applicationType', coalesce(
                oa.normalized_payload->>'apply_type',
                oa.normalized_payload#>>'{{detail_fields,申请类型}}'
            ),
            'counterparty', coalesce(
                oa.normalized_payload->>'counterparty_name',
                oa.normalized_payload#>>'{{detail_fields,往来单位}}'
            ),
            'reconciliationStatus', '待关联',
            'amount', oa.amount::text,
            'reason', oa.normalized_payload->>'reason'
        )) as column_values,
        null::text as external_batch_id
    from app.oa_applications oa
    where oa.status <> 'deleted'
      and {_COMPLETED_OA_SQL}
    union all
    select
        coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
        'bank'::text as pane,
        'bank'::text as source_kind,
        bank.txn_month as scope_month,
        coalesce(bank.trade_time::date, bank.txn_date) as sort_date,
        bank.updated_at,
        concat_ws(
            ' ',
            coalesce(bank.legacy_mongo_id, bank.id::text),
            bank.counterparty_name_raw,
            bank.account_no,
            bank.account_name,
            bank.amount::text,
            bank.summary,
            bank.remark,
            bank.raw_payload::text
        ) as searchable_text,
        jsonb_strip_nulls(jsonb_build_object(
            'transactionTime', coalesce(bank.trade_time::date, bank.txn_date)::text,
            'direction', case
                when lower(coalesce(bank.txn_direction, '')) in ('out', 'outflow', 'debit', 'expense', '支出')
                     or coalesce(bank.signed_amount, 0) < 0
                    then '支出'
                else '收入'
            end,
            'amount', bank.amount::text,
            'debitAmount', case
                when lower(coalesce(bank.txn_direction, '')) in ('out', 'outflow', 'debit', 'expense', '支出')
                     or coalesce(bank.signed_amount, 0) < 0
                    then bank.amount::text
            end,
            'creditAmount', case
                when not (
                    lower(coalesce(bank.txn_direction, '')) in ('out', 'outflow', 'debit', 'expense', '支出')
                    or coalesce(bank.signed_amount, 0) < 0
                )
                    then bank.amount::text
            end,
            'counterparty', bank.counterparty_name_raw,
            'paymentAccount', concat_ws(
                ' ',
                case
                    when bank.account_no like '6225%%' then '招商银行'
                    when bank.account_no like '6222%%' then '工商银行'
                    when bank.account_no like '6217%%' then '建设银行'
                    when bank.account_no like '6228%%' then '农业银行'
                    when bank.account_no like '6214%%' then '中国银行'
                    else '未识别银行'
                end,
                case
                    when bank.account_name like '%%基本%%' then '基本户'
                    when bank.account_name like '%%一般%%' then '一般户'
                    when bank.account_name like '%%专户%%' then '专户'
                    else '账户'
                end,
                right(bank.account_no, 4)
            ),
            'invoiceRelationStatus', '待关联发票',
            'paymentOrReceiptTime', coalesce(
                bank.pay_receive_time::date,
                bank.trade_time::date,
                bank.txn_date
            )::text,
            'note', bank.remark,
            'loanRepaymentDate', bank.raw_payload->>'repayment_date'
        )) as column_values,
        null::text as external_batch_id
    from app.bank_transactions bank
    where bank.status <> 'deleted'
      and not exists (
          select 1
          from app.bank_transaction_relation_claims claim
          where claim.status = 'active'
            and claim.owner_type = 'oa_pending_payment_relation'
            and claim.bank_transaction_id = coalesce(bank.legacy_mongo_id, bank.id::text)
      )
    union all
    select
        invoice.row_id,
        'invoice'::text as pane,
        invoice.source_kind,
        invoice.scope_month,
        invoice.invoice_date as sort_date,
        invoice.updated_at,
        concat_ws(
            ' ',
            invoice.row_id,
            invoice.invoice_type,
            invoice.invoice_no,
            invoice.invoice_code,
            invoice.digital_invoice_no,
            invoice.seller_name,
            invoice.seller_tax_no,
            invoice.buyer_name,
            invoice.buyer_tax_no,
            invoice.amount::text,
            invoice.total_with_tax::text,
            invoice.tags::text,
            invoice.raw_payload::text
        ) as searchable_text,
        jsonb_strip_nulls(jsonb_build_object(
            'sellerTaxId', invoice.seller_tax_no,
            'sellerName', invoice.seller_name,
            'buyerTaxId', invoice.buyer_tax_no,
            'buyerName', invoice.buyer_name,
            'invoiceCode', invoice.invoice_code,
            'invoiceNo', invoice.invoice_no,
            'digitalInvoiceNo', invoice.digital_invoice_no,
            'issueDate', invoice.invoice_date::text,
            'amount', invoice.amount::text,
            'taxRate', invoice.tax_rate,
            'taxAmount', invoice.tax_amount::text,
            'grossAmount', invoice.total_with_tax::text,
            'invoiceType', invoice.invoice_type
        )) as column_values,
        null::text as external_batch_id
    from ranked_invoices invoice
    where invoice.identity_rank = 1
    union all
    select
        'etc-summary-' || regexp_replace(batch.external_batch_id, '[^A-Za-z0-9_-]+', '-', 'g') as row_id,
        'invoice'::text as pane,
        'etc_invoice_summary'::text as source_kind,
        batch.scope_month,
        batch.scope_month as sort_date,
        batch.updated_at,
        concat_ws(' ', batch.external_batch_id, 'ETC', 'ETC发票') as searchable_text,
        jsonb_build_object(
            'sellerTaxId', 'ETC批次',
            'buyerTaxId', batch.external_batch_id,
            'invoiceCode', batch.external_batch_id,
            'invoiceType', '进项发票'
        ) as column_values,
        batch.external_batch_id
    from etc_batch_keys batch
    where batch.external_batch_id is not null
),
relation_groups as materialized (
    select
        'case:' || relation.case_id as internal_key,
        relation.case_id as detail_key,
        'relation'::text as group_kind,
        case
            when not ('bank' = any(relation.row_types)) then 'paired'
            when coalesce(relation.special_metadata->>'source', '') = 'batch_accounting' then 'paired'
            when coalesce(
                (relation.special_metadata->>'requires_oa')::boolean,
                (relation.special_metadata->>'paired_requires_oa')::boolean,
                true
            ) and not ('oa' = any(relation.row_types)) then 'unpaired'
            when coalesce(
                (relation.special_metadata->>'requires_invoice')::boolean,
                (relation.special_metadata->>'paired_requires_invoice')::boolean,
                true
            ) and not ('invoice' = any(relation.row_types)) then 'unpaired'
            else 'paired'
        end as zone,
        relation.row_ids as member_ids,
        relation.month_scope as scope_month,
        relation.updated_at,
        relation.external_etc_batch_id,
        array_remove(array[
            case when 'bank' = any(relation.row_types)
                   and coalesce(
                       (relation.special_metadata->>'requires_oa')::boolean,
                       (relation.special_metadata->>'paired_requires_oa')::boolean,
                       true
                   )
                   and not ('oa' = any(relation.row_types))
                   and coalesce(relation.special_metadata->>'source', '') <> 'batch_accounting'
                 then 'oa' end,
            case when 'bank' = any(relation.row_types)
                   and coalesce(
                       (relation.special_metadata->>'requires_invoice')::boolean,
                       (relation.special_metadata->>'paired_requires_invoice')::boolean,
                       true
                   )
                   and not ('invoice' = any(relation.row_types))
                   and coalesce(relation.special_metadata->>'source', '') <> 'batch_accounting'
                 then 'invoice' end
        ], null) as missing_row_types
    from active_relations relation
    cross join requested_scope scope
    where scope.scope_key = 'all'
       or relation.month_scope = scope.scope_month
       or exists (
           select 1
           from canonical_rows member
           where member.row_id = any(relation.row_ids)
             and member.scope_month = scope.scope_month
       )
       or exists (
           select 1
           from canonical_rows member
           where member.external_batch_id = relation.external_etc_batch_id
             and member.scope_month = scope.scope_month
       )
),
unpaired_groups as materialized (
    select
        'row:' || row.pane || ':' || row.row_id as internal_key,
        coalesce(row.external_batch_id, row.row_id) as detail_key,
        'unpaired'::text as group_kind,
        'unpaired'::text as zone,
        array[row.row_id]::text[] as member_ids,
        row.scope_month,
        row.updated_at,
        row.external_batch_id,
        array[]::text[] as missing_row_types
    from canonical_rows row
    cross join requested_scope scope
    where (scope.scope_key = 'all' or row.scope_month = scope.scope_month)
      and not exists (
          select 1
          from active_relations relation
          where row.row_id = any(relation.row_ids)
             or (
                 row.external_batch_id is not null
                 and row.external_batch_id = relation.external_etc_batch_id
             )
      )
      and not exists (
          select 1
          from app.workbench_row_overrides override
          where override.status = 'active'
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
)
"""


class PostgresWorkbenchCanonicalQueryRepository:
    """Page-owned Workbench query repository over canonical PostgreSQL facts."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

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

    def get_workbench_group_detail(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._in_snapshot(lambda repository: repository._group_detail(**kwargs))

    def get_workbench_row_detail(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._in_snapshot(lambda repository: repository._row_detail(**kwargs))

    def get_workbench_relation_preview_selection(self, **kwargs: Any) -> dict[str, Any]:
        return self._in_snapshot(
            lambda repository: repository._relation_preview_selection(**kwargs)
        )

    def validate_workbench_relation_selection_in_current_transaction(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
    ) -> dict[str, dict[str, str]]:
        normalized_scope = self._scope_key(scope_key)
        normalized_row_ids = list(
            dict.fromkeys(
                str(row_id).strip()
                for row_id in list(row_ids or [])
                if str(row_id).strip()
            )
        )
        rows = self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select distinct
                member.row_id,
                member.pane,
                member.source_kind,
                member.external_batch_id
            from canonical_groups groups
            join lateral unnest(groups.member_ids) member_id(row_id) on true
            join canonical_rows member on member.row_id = member_id.row_id
            where member.row_id = any(%s::text[])
            order by member.row_id
            """,
            tuple([*self._scope_params(normalized_scope), normalized_row_ids]),
        )
        descriptors = {
            str(row.get("row_id") or ""): {
                "pane": str(row.get("pane") or ""),
                "source_kind": str(row.get("source_kind") or ""),
                "external_etc_batch_id": str(row.get("external_batch_id") or ""),
            }
            for row in rows
            if str(row.get("row_id") or "").strip()
        }
        if set(descriptors) != set(normalized_row_ids):
            raise WorkbenchWriteConflict(
                action="confirm_link",
                reason="canonical_selection_changed",
                expected={"row_ids": normalized_row_ids},
                actual={"row_ids": sorted(descriptors)},
            )
        return descriptors

    def list_workbench_ignored_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        return self._in_snapshot(
            lambda repository: repository._ignored_rows(scope_key=scope_key)
        )

    def list_canonical_search_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        return self._in_snapshot(
            lambda repository: repository._search_rows(scope_key=scope_key),
            statement_timeout_seconds=90,
        )

    def list_workbench_search_scope_keys(self) -> list[str]:
        rows = self._connection.fetch_all(
            f"""
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from (
                select coalesce(
                    oa.scope_month,
                    date_trunc('month', oa.application_date)::date
                ) as scope_month
                from app.oa_applications oa
                where oa.status <> 'deleted'
                  and {_COMPLETED_OA_SQL}
                union
                select bank.txn_month
                from app.bank_transactions bank
                where bank.status <> 'deleted'
                union
                select invoice.invoice_month
                from app.invoices invoice
                where {_VISIBLE_INVOICE_SQL}
                union
                select relation.month_scope
                from app.workbench_pair_relations relation
                where relation.status = 'active'
            ) canonical_scopes
            where scope_month is not null
            order by scope_key desc
            """
        )
        return [
            str(row.get("scope_key") or "")
            for row in rows
            if str(row.get("scope_key") or "")
        ]

    def workbench_search_source_versions(self, *, scope_key: str) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        if normalized_scope == "all":
            raise ValueError("Workbench search source versions require a month scope key YYYY-MM.")
        scope_month = month_start(normalized_scope)
        row = self._connection.fetch_one(
            f"""
            select
                (
                    select md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            oa.row_id,
                            oa.updated_at::text
                        ),
                        '|' order by oa.row_id
                    ), ''))
                    from app.oa_applications oa
                    where oa.status <> 'deleted'
                      and {_COMPLETED_OA_SQL}
                      and coalesce(
                          oa.scope_month,
                          date_trunc('month', oa.application_date)::date
                      ) = %s::date
                ) as oa_membership_version,
                (
                    select md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            coalesce(bank.legacy_mongo_id, bank.id::text),
                            bank.updated_at::text
                        ),
                        '|' order by coalesce(bank.legacy_mongo_id, bank.id::text)
                    ), ''))
                    from app.bank_transactions bank
                    where bank.status <> 'deleted'
                      and bank.txn_month = %s::date
                ) as bank_membership_version,
                (
                    select md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            coalesce(invoice.legacy_mongo_id, invoice.id::text),
                            invoice.updated_at::text
                        ),
                        '|' order by coalesce(invoice.legacy_mongo_id, invoice.id::text)
                    ), ''))
                    from app.invoices invoice
                    where {_VISIBLE_INVOICE_SQL}
                      and invoice.invoice_month = %s::date
                ) as invoice_membership_version,
                (
                    select md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            relation.case_id,
                            relation.relation_mode,
                            relation.month_scope::text,
                            array_to_string(relation.row_ids, ','),
                            array_to_string(relation.row_types, ','),
                            relation.updated_at::text
                        ),
                        '|' order by relation.case_id
                    ), ''))
                    from app.workbench_pair_relations relation
                    where relation.status = 'active'
                      and (
                          relation.month_scope = %s::date
                          or exists (
                              select 1
                              from app.oa_applications oa
                              where oa.status <> 'deleted'
                                and coalesce(
                                    oa.scope_month,
                                    date_trunc('month', oa.application_date)::date
                                ) = %s::date
                                and oa.row_id = any(relation.row_ids)
                          )
                          or exists (
                              select 1
                              from app.bank_transactions bank
                              where bank.status <> 'deleted'
                                and bank.txn_month = %s::date
                                and coalesce(bank.legacy_mongo_id, bank.id::text) = any(relation.row_ids)
                          )
                          or exists (
                              select 1
                              from app.invoices invoice
                              where {_VISIBLE_INVOICE_SQL}
                                and invoice.invoice_month = %s::date
                                and coalesce(invoice.legacy_mongo_id, invoice.id::text) = any(relation.row_ids)
                          )
                      )
                ) as relation_membership_version,
                (
                    select md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            override.row_id,
                            override.scope_month::text,
                            override.updated_at::text
                        ),
                        '|' order by override.row_id
                    ), ''))
                    from app.workbench_row_overrides override
                    where override.status = 'active'
                      and override.scope_month = %s::date
                ) as override_membership_version
            """,
            (
                scope_month,
                scope_month,
                scope_month,
                scope_month,
                scope_month,
                scope_month,
                scope_month,
                scope_month,
            ),
        )
        payload = row if isinstance(row, dict) else {}
        return {
            "search_index_schema_version": "2026-07-search-canonical-v1",
            "oa_membership_version": str(payload.get("oa_membership_version") or ""),
            "bank_membership_version": str(payload.get("bank_membership_version") or ""),
            "invoice_membership_version": str(payload.get("invoice_membership_version") or ""),
            "relation_membership_version": str(payload.get("relation_membership_version") or ""),
            "override_membership_version": str(payload.get("override_membership_version") or ""),
        }

    def _in_snapshot(
        self,
        operation: Callable[[PostgresWorkbenchCanonicalQueryRepository], Any],
        *,
        statement_timeout_seconds: int = 2,
    ) -> Any:
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            raise RuntimeError("Workbench canonical queries require PostgreSQL transaction support.")
        with transaction_factory() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            transaction.execute(
                f"set local statement_timeout = '{int(statement_timeout_seconds)}s'"
            )
            return _without_retired_page_runtime_fields(
                operation(PostgresWorkbenchCanonicalQueryRepository(transaction))
            )

    def _initial_page(
        self,
        *,
        scope_key: str,
        paired_query: dict[str, Any] | None,
        unpaired_query: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary_payload = self._summary(scope_key=scope_key)
        paired_page = self._groups_page(
            scope_key=scope_key,
            zone="paired",
            page=1,
            page_size=50,
            detail_level="summary",
            **self._page_query(paired_query),
        )
        unpaired_page = self._groups_page(
            scope_key=scope_key,
            zone="unpaired",
            page=1,
            page_size=50,
            detail_level="summary",
            **self._page_query(unpaired_query),
        )
        return {
            "month": self._scope_key(scope_key),
            "scope_key": self._scope_key(scope_key),
            **summary_payload,
            "paired": paired_page,
            "unpaired": unpaired_page,
            "oa_status": {"code": "ready", "message": "OA canonical snapshot ready"},
        }

    def _groups_page(
        self,
        *,
        scope_key: str,
        zone: str,
        page: int | str | None = None,
        page_size: int | str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: Any = None,
        time_filters: Any = None,
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        normalized_zone = str(zone or "").strip()
        normalized_page = max(1, int_value(page, 1))
        normalized_page_size = min(200, max(1, int_value(page_size, 50)))
        normalized_detail_level = "summary" if str(detail_level or "").strip() == "summary" else "full"
        normalized_columns = _normalize_workbench_column_filters(column_filters)
        normalized_times = _normalize_workbench_time_filters(time_filters)
        where_sql, where_params = self._group_filters(
            zone=normalized_zone,
            status=status,
            source_kind=source_kind,
            search=search,
            column_filters=normalized_columns,
            time_filters=normalized_times,
        )
        scope_params = self._scope_params(normalized_scope)
        count_row = self._connection.fetch_one(
            f"""
            with {_CANONICAL_GROUPS_CTE},
            filtered_groups as materialized (
                select groups.*
                from canonical_groups groups
                where {where_sql}
            )
            select
                count(distinct groups.internal_key)::bigint as total_count,
                count(distinct member.row_id) filter (where member.pane = 'oa')::bigint as oa_count,
                count(distinct member.row_id) filter (where member.pane = 'bank')::bigint as bank_count,
                count(distinct member.row_id) filter (where member.pane = 'invoice')::bigint as invoice_count
            from filtered_groups groups
            left join lateral unnest(groups.member_ids) member_id(row_id) on true
            left join canonical_rows member on member.row_id = member_id.row_id
            """,
            tuple([*scope_params, *where_params]),
        ) or {}
        order_sql = self._groups_order_by(sort)
        rows = self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE},
            filtered_groups as materialized (
                select
                    groups.*,
                    (select min(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'oa') as oa_sort_min,
                    (select max(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'oa') as oa_sort_max,
                    (select min(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'bank') as bank_sort_min,
                    (select max(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'bank') as bank_sort_max,
                    (select min(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'invoice') as invoice_sort_min,
                    (select max(member.sort_date)
                       from canonical_rows member
                      where member.row_id = any(groups.member_ids)
                        and member.pane = 'invoice') as invoice_sort_max
                from canonical_groups groups
                where {where_sql}
            )
            select *
            from filtered_groups
            order by {order_sql}
            limit %s offset %s
            """,
            tuple(
                [
                    *scope_params,
                    *where_params,
                    normalized_page_size + 1,
                    (normalized_page - 1) * normalized_page_size,
                ]
            ),
        )
        visible_descriptors = rows[:normalized_page_size]
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=visible_descriptors,
            detail_level=normalized_detail_level,
            column_filters=normalized_columns,
            time_filters=normalized_times,
        )
        oa_count = int_value(count_row.get("oa_count"), 0)
        bank_count = int_value(count_row.get("bank_count"), 0)
        invoice_count = int_value(count_row.get("invoice_count"), 0)
        return {
            "month": normalized_scope,
            "scope_key": normalized_scope,
            "zone": normalized_zone,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "detail_level": normalized_detail_level,
            "total": int_value(count_row.get("total_count"), 0),
            "row_counts": {
                "oa": oa_count,
                "bank": bank_count,
                "invoice": invoice_count,
                "rows": oa_count + bank_count + invoice_count,
            },
            "has_more": len(rows) > normalized_page_size,
            "groups": groups,
        }

    def _search_group_descriptors(
        self,
        *,
        scope_key: str,
        zone: str,
    ) -> list[dict[str, Any]]:
        normalized_scope = self._scope_key(scope_key)
        return self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select groups.*
            from canonical_groups groups
            where groups.zone = %s
            order by groups.internal_key
            """,
            tuple([*self._scope_params(normalized_scope), zone]),
        )

    def _group_detail(
        self,
        *,
        scope_key: str,
        zone: str,
        group_id: str,
        detail_key: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope = self._scope_key(scope_key)
        normalized_group_id = str(group_id or "").strip()
        resolved_detail_key = str(detail_key or "").strip()
        if normalized_group_id.startswith("case:"):
            resolved_detail_key = normalized_group_id.removeprefix("case:")
        if not resolved_detail_key:
            return None
        rows = self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select *
            from canonical_groups groups
            where groups.zone = %s
              and groups.detail_key = %s
            limit 2
            """,
            tuple([*self._scope_params(normalized_scope), zone, resolved_detail_key]),
        )
        if len(rows) != 1:
            return None
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=rows,
            detail_level="full",
            column_filters={},
            time_filters={},
        )
        if len(groups) != 1 or str(groups[0].get("group_id") or "") != normalized_group_id:
            return None
        return {"group": groups[0], "scope_key": normalized_scope}

    def _row_detail(self, *, scope_key: str, row_id: str) -> dict[str, Any] | None:
        normalized_scope = self._scope_key(scope_key)
        normalized_row_id = str(row_id or "").strip()
        descriptor = self._connection.fetch_one(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select groups.*
            from canonical_groups groups
            where %s = any(groups.member_ids)
            order by case when groups.group_kind = 'relation' then 0 else 1 end
            limit 1
            """,
            tuple([*self._scope_params(normalized_scope), normalized_row_id]),
        )
        if not isinstance(descriptor, dict):
            return None
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=[descriptor],
            detail_level="full",
            column_filters={},
            time_filters={},
        )
        for group in groups:
            for row in self._group_rows(group):
                if str(row.get("id") or "") == normalized_row_id:
                    return {"row": row, "scope_key": normalized_scope}
        return None

    def _search_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        normalized_scope = self._scope_key(scope_key)
        if normalized_scope == "all":
            raise ValueError("Workbench search rows require a month scope key YYYY-MM.")

        contexts_by_row_id: dict[str, dict[str, Any]] = {}
        for zone in ("paired", "unpaired"):
            descriptors = self._search_group_descriptors(
                scope_key=normalized_scope,
                zone=zone,
            )
            groups = self._hydrate_groups(
                month=normalized_scope,
                descriptors=descriptors,
                detail_level="full",
                column_filters={},
                time_filters={},
            )
            for group in groups:
                if not isinstance(group, dict):
                    continue
                rows = self._group_rows(group)
                project_names = sorted(
                    {
                        str(row.get("project_name") or "").strip()
                        for row in rows
                        if str(row.get("type") or "") == "oa"
                        and str(row.get("project_name") or "").strip()
                    }
                )
                for row in rows:
                    row_id = str(row.get("id") or "").strip()
                    if not row_id or row_id in contexts_by_row_id:
                        continue
                    contexts_by_row_id[row_id] = {
                        "row": row,
                        "zone_hint": zone,
                        "group_id": str(group.get("group_id") or "") or None,
                        "project_names": project_names,
                    }

        for row in self._ignored_rows(scope_key=normalized_scope):
            row_id = str(row.get("id") or "").strip()
            if not row_id or row_id in contexts_by_row_id:
                continue
            contexts_by_row_id[row_id] = {
                "row": row,
                "zone_hint": "ignored",
                "group_id": None,
                "project_names": [],
            }
        return list(contexts_by_row_id.values())

    def _relation_preview_selection(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        normalized_row_ids = list(
            dict.fromkeys(
                str(row_id).strip()
                for row_id in list(row_ids or [])
                if str(row_id).strip()
            )
        )
        descriptors = self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select distinct on (groups.internal_key) groups.*
            from canonical_groups groups
            where groups.member_ids && %s::text[]
            order by groups.internal_key
            """,
            tuple([*self._scope_params(normalized_scope), normalized_row_ids]),
        )
        selected_descriptor_ids = {
            row_id
            for descriptor in descriptors
            for row_id in text_list(descriptor.get("member_ids"))
            if row_id in normalized_row_ids
        }
        missing_row_ids = [
            row_id for row_id in normalized_row_ids if row_id not in selected_descriptor_ids
        ]
        if missing_row_ids:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )
        groups = self._hydrate_groups(
            month=normalized_scope,
            descriptors=descriptors,
            detail_level="full",
            column_filters={},
            time_filters={},
        )
        rows_by_id = {
            str(row.get("id") or ""): row
            for group in groups
            for row in self._group_rows(group)
            if str(row.get("id") or "")
        }
        selected_rows = [rows_by_id[row_id] for row_id in normalized_row_ids if row_id in rows_by_id]
        if len(selected_rows) != len(normalized_row_ids):
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )
        oa_row_ids = [
            str(row.get("id") or "")
            for row in selected_rows
            if str(row.get("type") or "") == "oa"
        ]
        context_ids = self._oa_attachment_context_ids(oa_row_ids)
        if len(context_ids) > WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_context_too_large",
                message="所选记录关联的上下文过多，请缩小选择范围后重试。",
            )
        context_rows = (
            self._load_rows(set(context_ids)).values()
            if context_ids
            else []
        )
        ordered_context = [
            row
            for row in context_rows
            if str(row.get("id") or "") not in set(normalized_row_ids)
        ]
        return {
            "scope_key": normalized_scope,
            "selected_row_ids": normalized_row_ids,
            "selected_rows": selected_rows,
            "context_rows": ordered_context,
            "rows": [*selected_rows, *ordered_context],
        }

    def _ignored_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        normalized_scope = self._scope_key(scope_key)
        params: list[Any] = []
        scope_sql = ""
        if normalized_scope != "all":
            scope_sql = "and override.scope_month = %s::date"
            params.append(month_start(normalized_scope))
        rows = self._connection.fetch_all(
            f"""
            select override.row_id
            from app.workbench_row_overrides override
            where override.status = 'active'
              {scope_sql}
              and coalesce(
                  (override.override_payload->>'ignored')::boolean,
                  override.override_payload->>'status' = 'ignored',
                  false
              )
            order by override.updated_at desc, override.row_id
            """,
            tuple(params),
        )
        row_ids = [
            str(row.get("row_id") or "").strip()
            for row in rows
            if str(row.get("row_id") or "").strip()
        ]
        hydrated = self._load_rows(set(row_ids))
        builder = WorkbenchCanonicalRowsBuilder(connection=self._connection)
        builder._apply_workbench_overrides_and_exceptions(hydrated)
        return [hydrated[row_id] for row_id in row_ids if row_id in hydrated]

    def _summary(self, *, scope_key: str) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        row = self._connection.fetch_one(
            f"""
            with {_CANONICAL_GROUPS_CTE},
            group_members as materialized (
                select
                    groups.internal_key,
                    groups.group_kind,
                    groups.zone,
                    groups.missing_row_types,
                    member.row_id,
                    member.pane,
                    member.column_values
                from canonical_groups groups
                left join lateral unnest(groups.member_ids) member_id(row_id) on true
                left join canonical_rows member on member.row_id = member_id.row_id
            )
            select
                count(distinct row_id) filter (where pane = 'oa')::bigint as oa_count,
                count(distinct row_id) filter (where pane = 'bank')::bigint as bank_count,
                count(distinct row_id) filter (where pane = 'invoice')::bigint as invoice_count,
                count(distinct internal_key) filter (where zone = 'paired')::bigint as paired_count,
                count(distinct internal_key) filter (where zone = 'unpaired')::bigint as unpaired_count,
                count(distinct internal_key) filter (
                    where zone = 'unpaired' and group_kind = 'relation'
                )::bigint as incomplete_group_count,
                count(distinct internal_key) filter (
                    where 'oa' = any(missing_row_types)
                )::bigint as missing_oa_group_count,
                count(distinct internal_key) filter (
                    where 'bank' = any(missing_row_types)
                )::bigint as missing_bank_group_count,
                count(distinct internal_key) filter (
                    where 'invoice' = any(missing_row_types)
                )::bigint as missing_invoice_group_count,
                count(distinct row_id) filter (
                    where pane = 'bank' and column_values->>'direction' = '支出'
                )::bigint as expense_transaction_count,
                count(distinct row_id) filter (
                    where pane = 'bank' and column_values->>'direction' = '收入'
                )::bigint as income_transaction_count,
                count(distinct row_id) filter (
                    where pane = 'invoice'
                      and lower(coalesce(column_values->>'invoiceType', '')) like any(array['%%进%%', '%%input%%', '%%purchase%%'])
                )::bigint as input_invoice_count,
                count(distinct row_id) filter (
                    where pane = 'invoice'
                      and lower(coalesce(column_values->>'invoiceType', '')) like any(array['%%销%%', '%%output%%', '%%sale%%'])
                )::bigint as output_invoice_count,
                count(distinct row_id) filter (where zone = 'paired' and pane = 'oa')::bigint as paired_oa_count,
                count(distinct row_id) filter (where zone = 'paired' and pane = 'bank')::bigint as paired_bank_count,
                count(distinct row_id) filter (where zone = 'paired' and pane = 'invoice')::bigint as paired_invoice_count,
                count(distinct internal_key) filter (
                    where zone = 'paired'
                )::bigint as paired_groups,
                count(distinct row_id) filter (
                    where zone = 'unpaired'
                )::bigint as unpaired_objects
            from group_members
            """,
            tuple(self._scope_params(normalized_scope)),
        ) or {}
        zone_rows = self._connection.fetch_all(
            f"""
            with {_CANONICAL_GROUPS_CTE}
            select
                groups.zone,
                count(distinct groups.internal_key)::bigint as groups,
                count(distinct member.row_id) filter (where member.pane = 'oa')::bigint as oa,
                count(distinct member.row_id) filter (where member.pane = 'bank')::bigint as bank,
                count(distinct member.row_id) filter (where member.pane = 'invoice')::bigint as invoice
            from canonical_groups groups
            left join lateral unnest(groups.member_ids) member_id(row_id) on true
            left join canonical_rows member on member.row_id = member_id.row_id
            group by groups.zone
            """,
            tuple(self._scope_params(normalized_scope)),
        )
        zone_counts = {
            "paired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
            "unpaired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
        }
        for zone_row in zone_rows:
            zone = str(zone_row.get("zone") or "")
            if zone not in zone_counts:
                continue
            counts = zone_counts[zone]
            counts.update(
                {
                    "groups": int_value(zone_row.get("groups"), 0),
                    "oa": int_value(zone_row.get("oa"), 0),
                    "bank": int_value(zone_row.get("bank"), 0),
                    "invoice": int_value(zone_row.get("invoice"), 0),
                }
            )
            counts["rows"] = counts["oa"] + counts["bank"] + counts["invoice"]
        invoice_inventory = self._invoice_inventory(scope_key=normalized_scope)
        oa_count = int_value(row.get("oa_count"), 0)
        bank_count = int_value(row.get("bank_count"), 0)
        invoice_count = int_value(row.get("invoice_count"), 0)
        paired_count = int_value(row.get("paired_count"), 0)
        return {
            "summary": {
                "oa_count": oa_count,
                "bank_count": bank_count,
                "invoice_count": invoice_count,
                "paired_count": paired_count,
                "unpaired_count": int_value(row.get("unpaired_count"), 0),
                "exception_count": int_value(row.get("incomplete_group_count"), 0),
                "zone_counts": zone_counts,
            },
            "statistics": {
                "oa_count": oa_count,
                "bank_transaction_count": bank_count,
                "input_invoice_count": int_value(row.get("input_invoice_count"), 0),
                "output_invoice_count": int_value(row.get("output_invoice_count"), 0),
                "paired_group_count": int_value(row.get("paired_groups"), paired_count),
                "unpaired_object_count": int_value(row.get("unpaired_objects"), 0),
                "expense_transaction_count": int_value(row.get("expense_transaction_count"), 0),
                "income_transaction_count": int_value(row.get("income_transaction_count"), 0),
                "paired_oa_count": int_value(row.get("paired_oa_count"), 0),
                "paired_bank_transaction_count": int_value(row.get("paired_bank_count"), 0),
                "paired_invoice_count": int_value(row.get("paired_invoice_count"), 0),
                "incomplete_group_count": int_value(row.get("incomplete_group_count"), 0),
                "missing_oa_group_count": int_value(row.get("missing_oa_group_count"), 0),
                "missing_bank_group_count": int_value(row.get("missing_bank_group_count"), 0),
                "missing_invoice_group_count": int_value(row.get("missing_invoice_group_count"), 0),
            },
            "invoice_inventory": invoice_inventory,
        }

    def _invoice_inventory(self, *, scope_key: str) -> dict[str, int]:
        where = ["invoice.status <> 'deleted'"]
        params: list[Any] = []
        if scope_key != "all":
            where.append("invoice.invoice_month = %s::date")
            params.append(month_start(scope_key))
        row = self._connection.fetch_one(
            f"""
            select
                count(*)::bigint as system_total,
                count(*) filter (
                    where exists (
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
                    )
                )::bigint as manual_import_total,
                count(*) filter (
                    where invoice.workbench_visibility <> 'hidden_after_etc_submission'
                )::bigint as workbench_visible_total,
                count(*) filter (
                    where invoice.workbench_visibility = 'hidden_after_etc_submission'
                )::bigint as hidden_submitted_etc_total,
                count(*) filter (
                    where nullif(invoice.etc_invoice_id, '') is not null
                       or invoice.tags && array['ETC', 'etc', 'etc_invoice']::text[]
                )::bigint as extra_etc_total,
                count(*) filter (
                    where exists (
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
                    )
                )::bigint as oa_attachment_total
            from app.invoices invoice
            where {" and ".join(where)}
            """,
            tuple(params),
        ) or {}
        batch_where = ["batch.status <> 'withdrawn'"]
        batch_params: list[Any] = []
        if scope_key != "all":
            batch_where.append("batch.scope_month = %s::date")
            batch_params.append(month_start(scope_key))
        batch_row = self._connection.fetch_one(
            f"""
            select count(*)::bigint as etc_summary_batch_count
            from app.etc_business_batches batch
            where {" and ".join(batch_where)}
            """,
            tuple(batch_params),
        ) or {}
        return {
            "system_total": int_value(row.get("system_total"), 0),
            "manual_import_total": int_value(row.get("manual_import_total"), 0),
            "workbench_visible_total": int_value(row.get("workbench_visible_total"), 0),
            "hidden_submitted_etc_total": int_value(row.get("hidden_submitted_etc_total"), 0),
            "extra_etc_total": int_value(row.get("extra_etc_total"), 0),
            "etc_summary_batch_count": int_value(batch_row.get("etc_summary_batch_count"), 0),
            "oa_attachment_total": int_value(row.get("oa_attachment_total"), 0),
        }

    def _hydrate_groups(
        self,
        *,
        month: str,
        descriptors: list[dict[str, Any]],
        detail_level: str,
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not descriptors:
            return []
        relation_case_ids = {
            str(descriptor.get("detail_key") or "")
            for descriptor in descriptors
            if descriptor.get("group_kind") == "relation"
        }
        relations = self._load_relations(relation_case_ids)
        row_ids = {
            row_id
            for descriptor in descriptors
            for row_id in text_list(descriptor.get("member_ids"))
        }
        external_batch_ids = {
            str(descriptor.get("external_batch_id") or "")
            for descriptor in descriptors
            if str(descriptor.get("external_batch_id") or "")
        }
        rows_by_id = self._load_rows(row_ids, external_batch_ids=external_batch_ids)
        builder = WorkbenchCanonicalRowsBuilder(connection=self._connection)
        grouped = builder._group_payload(month, rows_by_id, relations)
        grouped_groups = [
            group
            for zone in ("paired", "unpaired")
            for group in list((grouped.get(zone) or {}).get("groups") or [])
            if isinstance(group, dict)
        ]
        groups_by_id = {
            str(group.get("group_id") or ""): group
            for group in grouped_groups
        }
        groups_by_member_id = {
            str(row.get("id") or ""): group
            for group in grouped_groups
            for row in self._group_rows(group)
            if str(row.get("id") or "")
        }
        result: list[dict[str, Any]] = []
        for descriptor in descriptors:
            detail_key = str(descriptor.get("detail_key") or "")
            if descriptor.get("group_kind") == "relation":
                group = groups_by_id.get(f"case:{detail_key}")
            else:
                row_id = text_list(descriptor.get("member_ids"))
                group = groups_by_member_id.get(row_id[0]) if row_id else None
            if not isinstance(group, dict):
                continue
            payload = _with_workbench_group_counts(group)
            payload["detail_key"] = detail_key
            if detail_level == "summary":
                payload = _filter_workbench_group_preview_rows_for_criteria(
                    payload,
                    column_filters=column_filters,
                    time_filters=time_filters,
                )
                payload = _compact_workbench_group_for_summary_page(payload)
                payload["detail_key"] = detail_key
            result.append(payload)
        return result

    def _load_rows(
        self,
        row_ids: set[str],
        *,
        external_batch_ids: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        builder = WorkbenchCanonicalRowsBuilder(connection=self._connection)
        rows = [
            *builder._oa_projection_rows_by_sql_ids(row_ids),
            *builder._bank_rows_by_ids(row_ids),
            *builder._invoice_rows_by_ids(row_ids),
        ]
        if external_batch_ids:
            rows.extend(
                builder._etc_invoice_summary_rows(
                    external_batch_ids=set(external_batch_ids)
                ).values()
            )
        return {
            str(row.get("id") or ""): row
            for row in rows
            if str(row.get("id") or "")
        }

    def _load_relations(self, case_ids: set[str]) -> list[dict[str, Any]]:
        if not case_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select
                relation.case_id,
                relation.relation_mode,
                relation.month_scope,
                relation.row_ids,
                relation.row_types,
                relation.amount_check,
                relation.special_metadata,
                relation.raw_payload
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.case_id = any(%s)
            order by relation.case_id
            """,
            (sorted(case_ids),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "raw_payload")
            payload = payload if isinstance(payload, dict) else {}
            result.append(
                {
                    **payload,
                    "case_id": str(row.get("case_id") or payload.get("case_id") or ""),
                    "status": "active",
                    "relation_mode": row.get("relation_mode") or payload.get("relation_mode"),
                    "row_ids": text_list(row.get("row_ids")) or text_list(payload.get("row_ids")),
                    "row_types": text_list(row.get("row_types")) or text_list(payload.get("row_types")),
                    "amount_check": row_payload(row, "amount_check")
                    or payload.get("amount_check")
                    or {},
                    "special_metadata": row_payload(row, "special_metadata")
                    or payload.get("special_metadata")
                    or {},
                }
            )
        return result

    def _oa_attachment_context_ids(self, oa_row_ids: list[str]) -> list[str]:
        if not oa_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id
            from app.invoices invoice
            where invoice.status <> 'deleted'
              and exists (
                  select 1
                  from jsonb_array_elements(
                      case when jsonb_typeof(invoice.source_links) = 'array'
                           then invoice.source_links else '[]'::jsonb end
                  ) source_link
                  where coalesce(
                      source_link->>'derived_from_oa_id',
                      source_link->>'source_oa_id',
                      source_link->>'oa_row_id'
                  ) = any(%s)
              )
            order by row_id
            limit %s
            """,
            (oa_row_ids, WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS + 1),
        )
        return [
            str(row.get("row_id") or "")
            for row in rows
            if str(row.get("row_id") or "")
        ]

    @staticmethod
    def _group_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
        collapsed = (
            group.get("collapsed_rows")
            if isinstance(group.get("collapsed_rows"), dict)
            else {}
        )
        rows: list[dict[str, Any]] = []
        for pane in ("oa", "bank", "invoice"):
            for row in [
                *list(group.get(f"{pane}_rows") or []),
                *list(collapsed.get(pane) or []),
            ]:
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    @staticmethod
    def _group_filters(
        *,
        zone: str,
        status: str | None,
        source_kind: str | None,
        search: str | None,
        column_filters: dict[str, dict[str, list[str]]],
        time_filters: dict[str, dict[str, str]],
    ) -> tuple[str, list[Any]]:
        clauses = ["groups.zone = %s"]
        params: list[Any] = [zone]
        if normalized_status := text(status):
            clauses.append("groups.zone = %s")
            params.append(normalized_status)
        if normalized_source := text(source_kind):
            clauses.append(
                "exists (select 1 from canonical_rows member "
                "where member.row_id = any(groups.member_ids) and member.source_kind = %s)"
            )
            params.append(normalized_source)
        if normalized_search := text(search):
            clauses.append(
                "exists (select 1 from canonical_rows member "
                "where member.row_id = any(groups.member_ids) and member.searchable_text ilike %s)"
            )
            params.append(f"%{normalized_search[:200]}%")
        for pane in ("oa", "bank", "invoice"):
            pane_clauses: list[str] = ["member.pane = %s"]
            pane_params: list[Any] = [pane]
            for column, values in sorted(column_filters.get(pane, {}).items()):
                if not values:
                    continue
                if pane == "bank" and column == "amount":
                    for value in values:
                        pane_clauses.append(
                            "(member.column_values->>'direction' = %s "
                            "or member.column_values->>'paymentAccount' = %s)"
                        )
                        pane_params.extend([value, value])
                else:
                    pane_clauses.append("member.column_values->>%s = any(%s)")
                    pane_params.extend([column, values])
            time_filter = time_filters.get(pane)
            start_date, end_date = PostgresWorkbenchCanonicalQueryRepository._time_range(
                time_filter
            )
            if start_date and end_date:
                pane_clauses.append(
                    "member.sort_date >= %s::date and member.sort_date < %s::date"
                )
                pane_params.extend([start_date, end_date])
            if len(pane_clauses) == 1:
                continue
            clauses.append(
                "exists (select 1 from canonical_rows member "
                "where member.row_id = any(groups.member_ids) and "
                + " and ".join(pane_clauses)
                + ")"
            )
            params.extend(pane_params)
        return " and ".join(clauses), params

    @staticmethod
    def _time_range(value: dict[str, str] | None) -> tuple[str | None, str | None]:
        payload = value if isinstance(value, dict) else {}
        if payload.get("mode") == "year":
            year = str(payload.get("year") or "")
            if len(year) == 4 and year.isdigit():
                return f"{year}-01-01", f"{int(year) + 1:04d}-01-01"
        if payload.get("mode") == "month":
            month = str(payload.get("month") or "")
            if len(month) == 7 and month[:4].isdigit() and month[5:].isdigit():
                year_number = int(month[:4])
                month_number = int(month[5:])
                if 1 <= month_number <= 12:
                    if month_number == 12:
                        return (
                            f"{year_number:04d}-12-01",
                            f"{year_number + 1:04d}-01-01",
                        )
                    return (
                        f"{year_number:04d}-{month_number:02d}-01",
                        f"{year_number:04d}-{month_number + 1:02d}-01",
                    )
        return None, None

    @staticmethod
    def _groups_order_by(sort: str | None) -> str:
        return {
            "oa:asc": "oa_sort_min asc nulls last, scope_month desc nulls last, internal_key",
            "oa:desc": "oa_sort_max desc nulls last, scope_month desc nulls last, internal_key",
            "bank:asc": "bank_sort_min asc nulls last, scope_month desc nulls last, internal_key",
            "bank:desc": "bank_sort_max desc nulls last, scope_month desc nulls last, internal_key",
            "invoice:asc": "invoice_sort_min asc nulls last, scope_month desc nulls last, internal_key",
            "invoice:desc": "invoice_sort_max desc nulls last, scope_month desc nulls last, internal_key",
        }.get(
            str(sort or "").strip().lower(),
            "scope_month desc nulls last, updated_at desc, internal_key",
        )

    @staticmethod
    def _scope_key(scope_key: str | None) -> str:
        normalized = str(scope_key or "").strip() or "all"
        if normalized.startswith("visibility:"):
            return normalized.rsplit(":", 1)[-1].strip() or "all"
        return normalized

    @classmethod
    def _scope_params(cls, scope_key: str) -> list[Any]:
        normalized = cls._scope_key(scope_key)
        scope_month = None if normalized == "all" else month_start(normalized)
        return [normalized, normalized, scope_month]

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
            )
            if key in payload
        }


def _without_retired_page_runtime_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_retired_page_runtime_fields(item)
            for key, item in value.items()
            if key not in _RETIRED_PAGE_RUNTIME_FIELDS
        }
    if isinstance(value, list):
        return [_without_retired_page_runtime_fields(item) for item in value]
    return value
