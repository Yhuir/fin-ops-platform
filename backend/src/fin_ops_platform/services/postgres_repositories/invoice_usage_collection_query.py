from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    normalize_payment_status_rules_settings,
)
from fin_ops_platform.services.output_invoice_reversal import (
    REVERSED_BLUE_INVOICE_NO_SQL_PATTERN,
)
from fin_ops_platform.services.postgres_repositories.common import row_payload
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAWorkflowRepository,
)
from fin_ops_platform.services.search_query import normalize_money_search_query


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(slots=True)
class InvoiceUsageCollectionCanonicalSnapshot:
    groups: list[dict[str, Any]]
    supporting_groups: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    transactions: list[Any]
    oa_records: list[Any]
    overlays: dict[str, dict[str, Any]]
    pagination: dict[str, int]
    summary: dict[str, Any]
    statistics: dict[str, int]
    facet_counts: dict[str, list[dict[str, Any]]]
    payment_status_labels: dict[str, str]
    payment_status_rules: dict[str, Any] = field(default_factory=dict)


class PostgresInputInvoiceUsageQueryRepository:
    """Page-specific canonical query repository for 进项发票使用情况."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Input invoice usage query repository requires PostgreSQL.")
        self._connection = connection

    def load_page(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        tenant_id: str = "default",
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        return self._load(
            page=page,
            page_size=page_size,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            tenant_id=tenant_id,
        )

    def load_rows_by_invoice_ids(
        self,
        invoice_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        normalized = _texts(invoice_ids)
        if not normalized:
            return _empty_snapshot(page=1, page_size=200)
        return self._load(
            page=1,
            page_size=min(200, max(1, len(normalized))),
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
            tenant_id=tenant_id,
            invoice_ids=normalized,
        )

    def load_row(
        self,
        row_id: str,
        *,
        tenant_id: str = "default",
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        return self._load(
            page=1,
            page_size=1,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
            tenant_id=tenant_id,
            row_id=str(row_id or "").strip(),
        )

    def load_oa_record(
        self,
        oa_id: str,
        *,
        tenant_id: str = "default",
    ) -> Any | None:
        normalized_oa_id = str(oa_id or "").strip()
        if not normalized_oa_id:
            return None
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            records = PostgresOAWorkflowRepository(
                transaction,
                tenant_id=tenant_id,
            ).list_application_records_by_row_ids([normalized_oa_id])
        return records[0] if records else None

    def _load(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        tenant_id: str,
        invoice_ids: list[str] | None = None,
        row_id: str | None = None,
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        normalized_month = _month(month)
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            settings_row = transaction.fetch_one(
                """
                select settings_payload
                from app.app_settings
                where settings_key = 'app_settings'
                limit 1
                """
            )
            settings_payload = (
                settings_row.get("settings_payload")
                if isinstance(settings_row, dict)
                and isinstance(settings_row.get("settings_payload"), dict)
                else {}
            )
            payment_settings = normalize_payment_status_rules_settings(
                settings_payload.get("input_invoice_usage_payment_status_rules")
            )
            status_case, status_params = _input_payment_status_case(payment_settings)
            cte = _fact_cte(
                invoice_type="input",
                month=normalized_month,
                status_case=status_case,
            )
            base_params: list[Any] = [tenant_id, *status_params]
            where_sql, where_params = _where_sql(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                filters=filters,
                field_sql=_INPUT_FIELDS,
                invoice_ids=invoice_ids,
                row_id=row_id,
            )
            status_where_sql, status_where_params = _where_sql(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                filters=_filters_without_field(filters, "payment_status"),
                field_sql=_INPUT_FIELDS,
                invoice_ids=invoice_ids,
                row_id=row_id,
            )
            filtered_sql = (
                f"{cte}, filtered_rows as materialized "
                f"(select * from final_rows {where_sql}), "
                f"status_option_rows as materialized "
                f"(select * from final_rows {status_where_sql})"
            )
            order_sql = _order_sql(
                sort_field=sort_field,
                sort_direction=sort_direction,
                field_sql=_INPUT_FIELDS,
            )
            offset = (page - 1) * page_size
            page_result = transaction.fetch_one(
                f"""
                {filtered_sql},
                page_rows as (
                    select
                        group_key,
                        relation_case_id,
                        identity_key,
                        primary_invoice_id,
                        invoice_ids,
                        array[]::text[] as supporting_group_keys,
                        count(*) over()::bigint as filtered_total,
                        row_number() over ({order_sql}) as page_order
                    from filtered_rows
                    {order_sql}
                    limit %s offset %s
                ),
                selected_members as (
                    select distinct member.invoice_id
                    from filtered_rows filtered
                    cross join lateral unnest(filtered.invoice_ids) member(invoice_id)
                ),
                summary as (
                    select
                        count(*)::bigint as row_count,
                        coalesce(sum(total_with_tax), 0)::numeric as total_with_tax,
                        count(*) filter (where oa_count > 0)::bigint as matched_oa_count,
                        count(*) filter (where bank_count > 0)::bigint as matched_bank_count,
                        count(*) filter (where status_code = 'pending')::bigint as pending_count,
                        (select count(*) from selected_members)::bigint as invoice_count
                    from filtered_rows
                ),
                facet_rows as (
                    select facet.field, facet.value, count(*)::bigint as option_count
                    from filtered_rows
                    cross join lateral (
                        values
                            ('seller_name', seller_name),
                            ('tax_rate', tax_rate),
                            ('specific_business_type', specific_business_type),
                            ('taxable_item_name', taxable_item_name),
                            ('oa_applicant', oa_applicant),
                            ('oa_application_type', oa_application_type),
                            ('oa_project_name', oa_project_name),
                            ('bank_counterparty_name', bank_counterparty_name),
                            ('bank_name', bank_name),
                            ('bank_account', bank_account),
                            ('bank_direction', bank_direction)
                    ) facet(field, value)
                    where nullif(facet.value, '') is not null
                    group by facet.field, facet.value
                    union all
                    select
                        'payment_status'::text,
                        status_code,
                        count(*)::bigint
                    from status_option_rows
                    where nullif(status_code, '') is not null
                    group by status_code
                )
                select
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(page_rows) - 'page_order'
                                order by page_order
                            )
                            from page_rows
                        ),
                        '[]'::jsonb
                    ) as group_rows,
                    coalesce(
                        (select to_jsonb(summary) from summary),
                        '{{}}'::jsonb
                    ) as summary_row,
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(facet_rows)
                                order by field, value
                            )
                            from facet_rows
                        ),
                        '[]'::jsonb
                    ) as facet_rows
                """,
                (
                    *base_params,
                    *where_params,
                    *status_where_params,
                    page_size,
                    offset,
                ),
            ) or {}
            group_rows = _dict_rows(page_result.get("group_rows"))
            summary_row = _dict_value(page_result.get("summary_row"))
            facet_rows = _dict_rows(page_result.get("facet_rows"))
            facts = _load_facts(
                transaction,
                group_rows=group_rows,
                supporting_group_rows=[],
                invoice_type="input",
                tenant_id=tenant_id,
            )
            statistics_row = _canonical_header_statistics(
                transaction,
                tenant_id=tenant_id,
            )
        filtered_total = int((group_rows[0] if group_rows else {}).get("filtered_total") or 0)
        invoice_count = int(summary_row.get("invoice_count") or 0)
        labels = {
            str(rule.get("statusCode") or ""): str(rule.get("label") or "")
            for rule in list(payment_settings.get("rules") or [])
            if str(rule.get("statusCode") or "").strip()
        }
        return InvoiceUsageCollectionCanonicalSnapshot(
            groups=facts["groups"],
            supporting_groups=[],
            relations=facts["relations"],
            transactions=facts["transactions"],
            oa_records=facts["oa_records"],
            overlays={},
            pagination={"page": page, "pageSize": page_size, "total": filtered_total},
            summary={
                "invoiceCount": invoice_count,
                "totalWithTax": _money(summary_row.get("total_with_tax")),
                "matchedOaCount": int(summary_row.get("matched_oa_count") or 0),
                "matchedBankTransactionCount": int(summary_row.get("matched_bank_count") or 0),
                "pendingCount": int(summary_row.get("pending_count") or 0),
            },
            statistics={
                "invoiceCount": int(statistics_row.get("input_invoice_count") or 0),
                "completedOaCount": int(statistics_row.get("completed_oa_count") or 0),
                "inProgressOaCount": int(statistics_row.get("in_progress_oa_count") or 0),
                "expenseTransactionCount": int(
                    statistics_row.get("expense_transaction_count") or 0
                ),
                "incomeTransactionCount": int(
                    statistics_row.get("income_transaction_count") or 0
                ),
            },
            facet_counts=_facet_counts(
                facet_rows,
                status_labels=labels,
                status_field="payment_status",
            ),
            payment_status_labels=labels,
            payment_status_rules=payment_settings,
        )


class PostgresOutputInvoiceCollectionQueryRepository:
    """Page-specific canonical query repository for 销项发票收款情况."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Output invoice collection query repository requires PostgreSQL.")
        self._connection = connection

    def load_page(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        tenant_id: str = "default",
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        return self._load(
            page=page,
            page_size=page_size,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            tenant_id=tenant_id,
        )

    def load_row(
        self,
        row_id: str,
        *,
        tenant_id: str = "default",
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        return self._load(
            page=1,
            page_size=1,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
            tenant_id=tenant_id,
            row_id=str(row_id or "").strip(),
        )

    def _load(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        tenant_id: str,
        row_id: str | None = None,
    ) -> InvoiceUsageCollectionCanonicalSnapshot:
        normalized_month = _month(month)
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            cte = _fact_cte(
                invoice_type="output",
                month=normalized_month,
                status_case=None,
            )
            base_params: list[Any] = []
            where_sql, where_params = _where_sql(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                filters=filters,
                field_sql=_OUTPUT_FIELDS,
                keyword_extra_columns=("invoice_remarks",),
                row_id=row_id,
            )
            status_where_sql, status_where_params = _where_sql(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                filters=_filters_without_field(filters, "collection_status"),
                field_sql=_OUTPUT_FIELDS,
                keyword_extra_columns=("invoice_remarks",),
                row_id=row_id,
            )
            filtered_sql = (
                f"{cte}, filtered_rows as materialized "
                f"(select * from final_rows {where_sql}), "
                f"status_option_rows as materialized "
                f"(select * from final_rows {status_where_sql})"
            )
            order_sql = _order_sql(
                sort_field=sort_field,
                sort_direction=sort_direction,
                field_sql=_OUTPUT_FIELDS,
            )
            offset = (page - 1) * page_size
            page_result = transaction.fetch_one(
                f"""
                {filtered_sql},
                page_rows as (
                    select
                        group_key,
                        relation_case_id,
                        identity_key,
                        primary_invoice_id,
                        invoice_ids,
                        status_code,
                        collected_amount,
                        pending_amount,
                        (bank_count > 0) as bank_attributed,
                        red_related_group_keys as supporting_group_keys,
                        count(*) over()::bigint as filtered_total,
                        row_number() over ({order_sql}) as page_order
                    from filtered_rows
                    {order_sql}
                    limit %s offset %s
                ),
                page_supporting_keys as (
                    select distinct supporting.group_key
                    from page_rows page
                    cross join lateral unnest(page.supporting_group_keys)
                        supporting(group_key)
                ),
                supporting_group_rows as (
                    select
                        final.group_key,
                        final.relation_case_id,
                        final.identity_key,
                        final.primary_invoice_id,
                        final.invoice_ids,
                        final.status_code,
                        final.collected_amount,
                        final.pending_amount,
                        (final.bank_count > 0) as bank_attributed,
                        final.red_related_group_keys as supporting_group_keys
                    from all_final_rows final
                    join page_supporting_keys supporting using (group_key)
                ),
                summary as (
                    select
                        coalesce(sum(invoice_count), 0)::bigint as invoice_count,
                        coalesce(sum(total_with_tax), 0)::numeric as total_with_tax,
                        coalesce(sum(collected_amount), 0)::numeric as collected_amount,
                        coalesce(sum(pending_amount), 0)::numeric as pending_amount,
                        count(*) filter (
                            where status_code = 'pending_collection'
                        )::bigint as pending_collection_count,
                        count(*) filter (
                            where status_code = 'partial_collected'
                        )::bigint as partial_collection_count
                    from filtered_rows
                ),
                facet_rows as (
                    select facet.field, facet.value, count(*)::bigint as option_count
                    from filtered_rows
                    cross join lateral (
                        values
                            ('buyer_name', buyer_name),
                            ('seller_name', seller_name),
                            ('tax_rate', tax_rate),
                            ('specific_business_type', specific_business_type),
                            ('taxable_item_name', taxable_item_name),
                            ('bank_counterparty_name', bank_counterparty_name),
                            ('bank_name', bank_name)
                    ) facet(field, value)
                    where nullif(facet.value, '') is not null
                    group by facet.field, facet.value
                    union all
                    select
                        'collection_status'::text,
                        status_code,
                        count(*)::bigint
                    from status_option_rows
                    where nullif(status_code, '') is not null
                    group by status_code
                )
                select
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(page_rows) - 'page_order'
                                order by page_order
                            )
                            from page_rows
                        ),
                        '[]'::jsonb
                    ) as group_rows,
                    coalesce(
                        (select to_jsonb(summary) from summary),
                        '{{}}'::jsonb
                    ) as summary_row,
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(facet_rows)
                                order by field, value
                            )
                            from facet_rows
                        ),
                        '[]'::jsonb
                    ) as facet_rows,
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(supporting_group_rows)
                                order by group_key
                            )
                            from supporting_group_rows
                        ),
                        '[]'::jsonb
                    ) as supporting_group_rows
                """,
                (
                    *base_params,
                    *where_params,
                    *status_where_params,
                    page_size,
                    offset,
                ),
            ) or {}
            group_rows = _dict_rows(page_result.get("group_rows"))
            summary_row = _dict_value(page_result.get("summary_row"))
            facet_rows = _dict_rows(page_result.get("facet_rows"))
            supporting_group_rows = _dict_rows(
                page_result.get("supporting_group_rows")
            )
            facts = _load_facts(
                transaction,
                group_rows=group_rows,
                supporting_group_rows=supporting_group_rows,
                invoice_type="output",
            )
            statistics_row = _canonical_header_statistics(
                transaction,
                tenant_id=tenant_id,
            )
        filtered_total = int((group_rows[0] if group_rows else {}).get("filtered_total") or 0)
        invoice_count = int(summary_row.get("invoice_count") or 0)
        status_labels = {
            "reversed_by_red": "已被红冲",
            "reverses_blue": "已冲销蓝票",
            "unmatched_red": "红票待核对",
            "collected": "已收款",
            "partial_collected": "部分收款",
            "pending_collection": "待收款",
        }
        return InvoiceUsageCollectionCanonicalSnapshot(
            groups=facts["groups"],
            supporting_groups=facts["supporting_groups"],
            relations=facts["relations"],
            transactions=facts["transactions"],
            oa_records=[],
            overlays={},
            pagination={"page": page, "pageSize": page_size, "total": filtered_total},
            summary={
                "invoiceCount": invoice_count,
                "totalWithTax": _money(summary_row.get("total_with_tax")),
                "collectedAmount": _money(summary_row.get("collected_amount")),
                "pendingAmount": _money(summary_row.get("pending_amount")),
                "pendingCollectionCount": int(
                    summary_row.get("pending_collection_count") or 0
                ),
                "partialCollectionCount": int(
                    summary_row.get("partial_collection_count") or 0
                ),
            },
            statistics={
                "invoiceCount": int(statistics_row.get("output_invoice_count") or 0),
                "incomeBankTransactionCount": int(
                    statistics_row.get("income_transaction_count") or 0
                ),
                "blueInvoiceCount": int(statistics_row.get("blue_invoice_count") or 0),
                "redInvoiceCount": int(statistics_row.get("red_invoice_count") or 0),
            },
            facet_counts=_facet_counts(
                facet_rows,
                status_labels=status_labels,
                status_field="collection_status",
            ),
            payment_status_labels={},
        )


def _canonical_header_statistics(
    transaction: Any,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    return transaction.fetch_one(
        """
        with invoice_statistics as (
            select
                count(*) filter (where invoice_type = 'input')::bigint
                    as input_invoice_count,
                count(*) filter (where invoice_type = 'output')::bigint
                    as output_invoice_count,
                count(*) filter (
                    where invoice_type = 'output'
                      and coalesce(total_with_tax, amount + coalesce(tax_amount, 0), 0) < 0
                )::bigint as red_invoice_count,
                count(*) filter (
                    where invoice_type = 'output'
                      and coalesce(total_with_tax, amount + coalesce(tax_amount, 0), 0) >= 0
                )::bigint as blue_invoice_count
            from app.invoices
            where status <> 'deleted'
        ),
        oa_statistics as (
            select
                (
                    select count(*)::bigint
                    from app.oa_applications oa
                    where oa.workflow_status is null
                       or oa.workflow_status = ''
                       or oa.workflow_status in (
                           'completed', '已完成', 'approved', 'APPROVED', 'Approved', '2'
                       )
                ) as completed_oa_count,
                (
                    select count(*)::bigint
                    from app.oa_pending_payment_admissions admission
                    where admission.tenant_id = %s
                      and admission.workflow_status = 'in_progress'
                      and not exists (
                          select 1
                          from app.oa_applications completed
                          where completed.row_id = admission.oa_id
                            and (
                                completed.workflow_status is null
                                or completed.workflow_status = ''
                                or completed.workflow_status in (
                                    'completed', '已完成', 'approved', 'APPROVED', 'Approved', '2'
                                )
                            )
                      )
                ) as in_progress_oa_count
        ),
        bank_statistics as (
            select
                count(*) filter (where txn_direction = 'outflow')::bigint
                    as expense_transaction_count,
                count(*) filter (where txn_direction = 'inflow')::bigint
                    as income_transaction_count
            from app.bank_transactions
            where status <> 'deleted'
        )
        select *
        from invoice_statistics
        cross join oa_statistics
        cross join bank_statistics
        """,
        (str(tenant_id or "default"),),
    ) or {}


_INPUT_FIELDS = {
    "invoice_no": "invoice_no",
    "invoice_date": "invoice_date",
    "seller_name": "seller_name",
    "seller_tax_no": "seller_tax_no",
    "total_with_tax": "total_with_tax",
    "amount": "amount",
    "tax_rate": "tax_rate",
    "tax_amount": "tax_amount",
    "specific_business_type": "specific_business_type",
    "taxable_item_name": "taxable_item_name",
    "payment_status": "status_code",
    "oa_applicant": "oa_applicant",
    "oa_application_type": "oa_application_type",
    "oa_project_name": "oa_project_name",
    "bank_counterparty_name": "bank_counterparty_name",
    "bank_trade_time": "bank_trade_time",
    "bank_amount": "bank_amount",
    "bank_name": "bank_name",
    "bank_account": "bank_account",
    "bank_direction": "bank_direction",
    "bank_summary": "bank_summary",
}

_OUTPUT_FIELDS = {
    "invoice_no": "invoice_no",
    "invoice_date": "invoice_date",
    "buyer_name": "buyer_name",
    "buyer_tax_no": "buyer_tax_no",
    "seller_name": "seller_name",
    "total_with_tax": "total_with_tax",
    "tax_amount": "tax_amount",
    "tax_rate": "tax_rate",
    "specific_business_type": "specific_business_type",
    "taxable_item_name": "taxable_item_name",
    "collection_status": "status_code",
    "pending_amount": "pending_amount",
    "bank_counterparty_name": "bank_counterparty_name",
    "bank_trade_time": "bank_trade_time",
    "bank_amount": "bank_amount",
    "bank_name": "bank_name",
    "bank_summary": "bank_summary",
}

_NUMERIC_FILTER_FIELDS = {
    "total_with_tax",
    "amount",
    "tax_amount",
    "pending_amount",
    "bank_amount",
}
_DATE_FILTER_FIELDS = {"invoice_date"}


def _filter_cast(field: str) -> str:
    if field in _NUMERIC_FILTER_FIELDS:
        return "::numeric"
    if field in _DATE_FILTER_FIELDS:
        return "::date"
    return "::text"


def _filter_array_cast(field: str) -> str:
    if field in _NUMERIC_FILTER_FIELDS:
        return "::numeric[]"
    if field in _DATE_FILTER_FIELDS:
        return "::date[]"
    return "::text[]"


def _fact_cte(
    *,
    invoice_type: str,
    month: str | None,
    status_case: str | None,
) -> str:
    if invoice_type not in {"input", "output"}:
        raise ValueError("Unsupported invoice type.")
    scope_sql = (
        f"invoice_month = date '{month}-01'"
        if month
        else "true"
    )
    primary_positive_sql = (
        "case when total_with_tax >= 0 then 0 else 1 end,"
        if invoice_type == "output"
        else ""
    )
    identity_sql = """
        case
            when nullif(trim(digital_invoice_no), '') is not null
                then 'digital:' || trim(digital_invoice_no)
            when nullif(trim(invoice_code), '') is not null
             and nullif(trim(invoice_no), '') is not null
                then 'code_no:' || trim(invoice_code) || ':' || trim(invoice_no)
            else 'id:' || coalesce(invoice.legacy_mongo_id, invoice.id::text)
        end
    """
    output_reversal_ctes_sql = (
        f"""
        , output_reversal_matches as (
            select
                red.invoice_id as red_invoice_id,
                matched.value[1] as target_invoice_no
            from invoice_rows red
            cross join lateral regexp_matches(
                    red.remark,
                    '{REVERSED_BLUE_INVOICE_NO_SQL_PATTERN}',
                    'g'
            ) matched(value)
            where red.total_with_tax < 0
        ),
        output_reversal_candidates as (
            select
                matched.red_invoice_id,
                min(matched.target_invoice_no) as target_invoice_no
            from output_reversal_matches matched
            group by matched.red_invoice_id
            having count(distinct matched.target_invoice_no) = 1
        ),
        output_reversal_pairs as (
            select
                candidate.red_invoice_id,
                min(blue.invoice_id) as blue_invoice_id
            from output_reversal_candidates candidate
            join invoice_rows blue
              on coalesce(
                    nullif(trim(blue.digital_invoice_no), ''),
                    trim(blue.invoice_no)
                 ) = candidate.target_invoice_no
             and blue.total_with_tax > 0
            group by candidate.red_invoice_id, candidate.target_invoice_no
            having count(distinct blue.invoice_id) = 1
        )
        """
        if invoice_type == "output"
        else ""
    )
    relation_grouping_sql = (
        """
        eligible_relation_components as (
            select
                mapped.component_id,
                min(mapped.case_id) as case_id
            from relation_invoice_members mapped
            join invoice_rows invoice on invoice.invoice_id = mapped.invoice_id
            group by mapped.component_id
            having count(distinct mapped.invoice_id) > 1
               and bool_or(invoice.in_scope)
        ),
        assigned_relation as (
            select distinct on (mapped.invoice_id)
                mapped.invoice_id,
                eligible.component_id,
                eligible.case_id
            from relation_invoice_members mapped
            join eligible_relation_components eligible using (component_id)
            order by mapped.invoice_id, eligible.component_id
        ),
        group_members as (
            select
                'relation-component:' || assigned.component_id as group_key,
                assigned.case_id as relation_case_id,
                assigned.invoice_id
            from assigned_relation assigned
            union all
            select
                'identity:' || invoice.identity_key as group_key,
                null::text as relation_case_id,
                invoice.invoice_id
            from invoice_rows invoice
            where invoice.in_scope
              and not exists (
                    select 1
                    from assigned_relation assigned
                    where assigned.invoice_id = invoice.invoice_id
              )
        )
        """
        if invoice_type == "input"
        else """
        group_members as (
            select
                'identity:' || invoice.identity_key as group_key,
                null::text as relation_case_id,
                invoice.invoice_id
            from invoice_rows invoice
        )
        """
    )
    group_reversal_links_sql = (
        """
        select
            grouped.group_key,
            array_agg(
                distinct related_group.group_key
                order by related_group.group_key
            ) as related_group_keys
        from grouped_invoices grouped
        cross join lateral unnest(grouped.invoice_ids) own_invoice(invoice_id)
        join invoice_aliases own_alias
          on own_alias.invoice_id = own_invoice.invoice_id
        join relation_members reversal
          on reversal.row_id = own_alias.row_id
         and reversal.relation_mode = 'output_invoice_reversal'
        join relation_members related_member
          on related_member.relation_id = reversal.relation_id
         and related_member.row_id <> reversal.row_id
         and related_member.row_type in (
             'invoice', 'input_invoice', 'output_invoice'
         )
        join invoice_aliases related_alias
          on related_alias.row_id = related_member.row_id
        join group_members related_group
          on related_group.invoice_id = related_alias.invoice_id
        group by grouped.group_key
        """
        if invoice_type == "input"
        else """
        select red_group.group_key,
               array_agg(distinct blue_group.group_key order by blue_group.group_key)
                   as related_group_keys
        from output_reversal_pairs pair
        join group_members red_group on red_group.invoice_id = pair.red_invoice_id
        join group_members blue_group on blue_group.invoice_id = pair.blue_invoice_id
        group by red_group.group_key
        union all
        select blue_group.group_key,
               array_agg(distinct red_group.group_key order by red_group.group_key)
                   as related_group_keys
        from output_reversal_pairs pair
        join group_members red_group on red_group.invoice_id = pair.red_invoice_id
        join group_members blue_group on blue_group.invoice_id = pair.blue_invoice_id
        group by blue_group.group_key
        """
    )
    bank_owner_ctes_sql = (
        """
        , output_component_bank_candidates as (
            select distinct
                mapped.component_id,
                mapped.invoice_id
            from relation_invoice_members mapped
            join invoice_rows invoice on invoice.invoice_id = mapped.invoice_id
            where invoice.total_with_tax > 0
              and not exists (
                    select 1
                    from output_reversal_pairs pair
                    where pair.red_invoice_id = mapped.invoice_id
                       or pair.blue_invoice_id = mapped.invoice_id
              )
        ),
        output_component_bank_owner as (
            select
                component_id,
                min(invoice_id) as invoice_id
            from output_component_bank_candidates
            group by component_id
            having count(distinct invoice_id) = 1
        )
        """
        if invoice_type == "output"
        else ""
    )
    bank_owner_join_sql = (
        """
            join output_component_bank_owner owner
              on owner.component_id = component.component_id
             and owner.invoice_id = invoice_member.invoice_id
        """
        if invoice_type == "output"
        else ""
    )
    final_status_sql = (
        f"""
        , final_rows as (
            select
                facts.*,
                {status_case} as status_code,
                0::numeric as collected_amount,
                abs(facts.total_with_tax)::numeric as pending_amount
            from group_facts facts
        )
        """
        if invoice_type == "input"
        else """
        , all_final_rows as (
            select
                facts.*,
                case
                    when cardinality(facts.red_related_group_keys) > 0
                     and facts.total_with_tax > 0 then 'reversed_by_red'
                    when cardinality(facts.red_related_group_keys) > 0
                     and facts.total_with_tax < 0 then 'reverses_blue'
                    when facts.total_with_tax < 0 then 'unmatched_red'
                    when facts.bank_inflow_total + 0.01 >= abs(facts.total_with_tax)
                     and abs(facts.total_with_tax) > 0 then 'collected'
                    when facts.bank_inflow_total > 0
                     and facts.bank_inflow_total < abs(facts.total_with_tax)
                        then 'partial_collected'
                    else 'pending_collection'
                end as status_code,
                facts.bank_inflow_total::numeric as collected_amount,
                case
                    when cardinality(facts.red_related_group_keys) > 0
                      or facts.total_with_tax < 0
                      or (
                          facts.bank_inflow_total + 0.01 >= abs(facts.total_with_tax)
                          and abs(facts.total_with_tax) > 0
                      )
                        then 0
                    else greatest(
                        0,
                        abs(facts.total_with_tax) - facts.bank_inflow_total
                    )
                end::numeric as pending_amount
            from group_facts facts
        ),
        final_rows as (
            select *
            from all_final_rows
            where in_scope
        )
        """
    )
    oa_ctes_sql = (
        """
        ,
        workflow_oa as materialized (
            select
                row_id,
                applicant,
                normalized_payload,
                form_type,
                project_name,
                amount,
                application_date,
                'completed'::text as workflow_status
            from app.oa_applications
            where workflow_status is null
               or workflow_status = ''
               or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
            union all
            select
                admission.oa_id,
                admission.applicant,
                admission.source_payload,
                coalesce(admission.source_payload->>'apply_type', admission.source_payload->>'form_type', ''),
                coalesce(admission.project_name_display, admission.project_name, ''),
                admission.amount,
                (admission.scope_key || '-01')::date,
                'in_progress'::text
            from app.oa_pending_payment_admissions admission
            where admission.tenant_id = %s
              and admission.workflow_status = 'in_progress'
        ),
        group_oa_rows as (
            select
                relation.group_key,
                oa.row_id as oa_id,
                oa.applicant,
                coalesce(
                    oa.normalized_payload->>'apply_type',
                    oa.normalized_payload->>'application_type',
                    oa.form_type,
                    ''
                ) as application_type,
                coalesce(
                    oa.normalized_payload->>'project_name_display',
                    oa.project_name,
                    ''
                ) as project_name,
                oa.amount,
                bool_or(
                    coalesce(
                        member.amount_check->>'matched' = 'true',
                        member.amount_check->>'status' = 'matched',
                        false
                    )
                    or member.relation_mode = 'oa_invoice_offset_auto_match'
                ) as amount_matched
            from group_relation_ids relation
            join relation_members member on member.relation_id = relation.relation_id
            join workflow_oa oa on oa.row_id = member.row_id
            where member.row_type = 'oa'
            group by
                relation.group_key,
                oa.row_id,
                oa.applicant,
                coalesce(
                    oa.normalized_payload->>'apply_type',
                    oa.normalized_payload->>'application_type',
                    oa.form_type,
                    ''
                ),
                coalesce(
                    oa.normalized_payload->>'project_name_display',
                    oa.project_name,
                    ''
                ),
                oa.amount
        ),
        group_oa as (
            select
                grouped.group_key,
                count(distinct oa.oa_id)::bigint as oa_count,
                coalesce(sum(oa.amount) filter (where oa.amount_matched), 0)::numeric
                    as matched_oa_total,
                (array_agg(oa.applicant order by oa.oa_id))[1]
                    as oa_applicant,
                (array_agg(oa.application_type order by oa.oa_id))[1]
                    as oa_application_type,
                (array_agg(oa.project_name order by oa.oa_id))[1]
                    as oa_project_name
            from grouped_invoices grouped
            left join group_oa_rows oa on oa.group_key = grouped.group_key
            group by grouped.group_key
        )
        """
        if invoice_type == "input"
        else ""
    )
    oa_facts_sql = (
        """
                coalesce(oa.oa_count, 0)::bigint as oa_count,
                coalesce(oa.matched_oa_total, 0)::numeric as matched_oa_total,
                coalesce(oa.oa_applicant, '') as oa_applicant,
                coalesce(oa.oa_application_type, '') as oa_application_type,
                coalesce(oa.oa_project_name, '') as oa_project_name,
        """
        if invoice_type == "input"
        else """
                0::bigint as oa_count,
                0::numeric as matched_oa_total,
                ''::text as oa_applicant,
                ''::text as oa_application_type,
                ''::text as oa_project_name,
        """
    )
    match_facts_sql = (
        """
                (
                    abs(coalesce(oa.matched_oa_total, 0) - grouped.total_with_tax) <= 0.01
                ) as invoice_oa_amount_matched,
                (
                    abs(coalesce(oa.matched_oa_total, 0) - grouped.total_with_tax) <= 0.01
                    and abs(coalesce(banks.matched_bank_total, 0) - abs(grouped.total_with_tax)) <= 0.01
                ) as fully_matched
        """
        if invoice_type == "input"
        else """
                false as invoice_oa_amount_matched,
                (
                    abs(coalesce(banks.matched_bank_total, 0) - abs(grouped.total_with_tax)) <= 0.01
                ) as fully_matched
        """
    )
    oa_join_sql = (
        "left join group_oa oa on oa.group_key = grouped.group_key"
        if invoice_type == "input"
        else ""
    )
    return f"""
        with recursive
        invoice_rows as (
            select
                coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
                invoice.invoice_type,
                invoice.invoice_no,
                coalesce(invoice.invoice_code, '') as invoice_code,
                coalesce(invoice.digital_invoice_no, '') as digital_invoice_no,
                invoice.invoice_date,
                invoice.invoice_month,
                coalesce(invoice.seller_name, invoice.counterparty_name, '') as seller_name,
                coalesce(invoice.seller_tax_no, '') as seller_tax_no,
                coalesce(invoice.buyer_name, invoice.counterparty_name, '') as buyer_name,
                coalesce(invoice.buyer_tax_no, '') as buyer_tax_no,
                invoice.amount,
                coalesce(invoice.tax_amount, 0)::numeric as tax_amount,
                coalesce(invoice.total_with_tax, invoice.amount + coalesce(invoice.tax_amount, 0))
                    ::numeric as total_with_tax,
                coalesce(invoice.tax_rate, '') as tax_rate,
                coalesce(
                    invoice.raw_payload->'normalized_payload'->>'specific_business_type',
                    invoice.raw_payload->>'specific_business_type',
                    ''
                ) as specific_business_type,
                coalesce(
                    invoice.raw_payload->'normalized_payload'->>'taxable_item_name',
                    invoice.raw_payload->>'taxable_item_name',
                    ''
                ) as taxable_item_name,
                coalesce(
                    invoice.raw_payload->'normalized_payload'->>'remark',
                    invoice.raw_payload->>'remark',
                    ''
                ) as remark,
                coalesce(
                    invoice.raw_payload->'normalized_payload'->>'is_positive_invoice',
                    invoice.raw_payload->>'is_positive_invoice',
                    ''
                ) as is_positive_invoice,
                invoice.source_links,
                ({scope_sql}) as in_scope,
                {identity_sql} as identity_key
            from app.invoices invoice
            where invoice.status <> 'deleted'
              and invoice.invoice_type = '{invoice_type}'
        ),
        invoice_aliases as (
            select invoice_id, invoice_id as row_id
            from invoice_rows
            union
            select
                invoice.invoice_id,
                link.value->>'source_workbench_row_id'
            from invoice_rows invoice
            cross join lateral jsonb_array_elements(
                coalesce(invoice.source_links, '[]'::jsonb)
            ) link(value)
            where link.value->>'source_type' = 'oa_attachment_invoice'
              and nullif(link.value->>'source_workbench_row_id', '') is not null
        ),
        active_relations as (
            select
                relation.id,
                relation.case_id,
                relation.relation_mode,
                relation.row_ids,
                relation.row_types,
                relation.amount_check,
                relation.special_metadata,
                relation.raw_payload
            from app.workbench_pair_relations relation
            where relation.status = 'active'
        ),
        relation_members as (
            select
                relation.id as relation_id,
                relation.case_id,
                relation.relation_mode,
                relation.amount_check,
                relation.special_metadata,
                relation.raw_payload,
                member.row_id,
                coalesce(
                    relation.row_types[member.ordinality],
                    case
                        when member.row_id like 'bank%%' then 'bank'
                        when member.row_id like 'oa%%' then 'oa'
                        else 'invoice'
                    end
                ) as row_type
            from active_relations relation
            cross join lateral unnest(relation.row_ids)
                with ordinality member(row_id, ordinality)
        ),
        relation_reach(root_relation_id, relation_id) as (
            select relation.id, relation.id
            from active_relations relation
            where coalesce(relation.relation_mode, '') <> 'output_invoice_reversal'
              and exists (
                select 1
                from relation_members seed
                join invoice_aliases alias on alias.row_id = seed.row_id
                where seed.relation_id = relation.id
                  and seed.row_type in (
                      'invoice', 'input_invoice', 'output_invoice'
                  )
            )
            union
            select reach.root_relation_id, neighbour.relation_id
            from relation_reach reach
            join relation_members current_member
              on current_member.relation_id = reach.relation_id
            join relation_members neighbour
              on neighbour.row_id = current_member.row_id
             and coalesce(neighbour.relation_mode, '') <> 'output_invoice_reversal'
        ),
        relation_component_ids as (
            select
                relation_id,
                min(root_relation_id::text) as component_id
            from relation_reach
            group by relation_id
        ),
        relation_invoice_members as (
            select distinct
                member.relation_id,
                component.component_id,
                member.case_id,
                alias.invoice_id
            from relation_members member
            join relation_component_ids component
              on component.relation_id = member.relation_id
            join invoice_aliases alias on alias.row_id = member.row_id
            where member.row_type in (
                'invoice', 'input_invoice', 'output_invoice'
            )
              and coalesce(member.relation_mode, '') <> 'output_invoice_reversal'
        )
        {output_reversal_ctes_sql},
        {relation_grouping_sql},
        ranked_members as (
            select
                member.group_key,
                member.relation_case_id,
                invoice.*,
                row_number() over (
                    partition by member.group_key
                    order by
                        case when invoice.in_scope then 0 else 1 end,
                        {primary_positive_sql}
                        invoice.invoice_date nulls last,
                        invoice.invoice_id
                ) as primary_rank
            from group_members member
            join invoice_rows invoice on invoice.invoice_id = member.invoice_id
        ),
        grouped_invoices as (
            select
                member.group_key,
                max(member.relation_case_id) as relation_case_id,
                (array_agg(member.identity_key order by member.primary_rank))[1]
                    as identity_key,
                (array_agg(member.invoice_id order by member.primary_rank))[1]
                    as primary_invoice_id,
                array_agg(member.invoice_id order by member.invoice_id) as invoice_ids,
                (array_agg(
                    coalesce(nullif(member.digital_invoice_no, ''), member.invoice_no)
                    order by member.primary_rank
                ))[1] as invoice_no,
                (array_agg(member.invoice_date order by member.primary_rank))[1]
                    as invoice_date,
                (array_agg(member.seller_name order by member.primary_rank))[1]
                    as seller_name,
                (array_agg(member.seller_tax_no order by member.primary_rank))[1]
                    as seller_tax_no,
                (array_agg(member.buyer_name order by member.primary_rank))[1]
                    as buyer_name,
                (array_agg(member.buyer_tax_no order by member.primary_rank))[1]
                    as buyer_tax_no,
                coalesce(sum(member.total_with_tax), 0)::numeric as total_with_tax,
                coalesce(sum(member.amount), 0)::numeric as amount,
                coalesce(sum(member.tax_amount), 0)::numeric as tax_amount,
                (array_agg(member.tax_rate order by member.primary_rank))[1] as tax_rate,
                (array_agg(member.specific_business_type order by member.primary_rank))[1]
                    as specific_business_type,
                (array_agg(member.taxable_item_name order by member.primary_rank))[1]
                    as taxable_item_name,
                coalesce(
                    string_agg(
                        nullif(member.remark, ''),
                        ' ' order by member.primary_rank
                    ),
                    ''
                ) as invoice_remarks,
                count(*)::bigint as invoice_count,
                bool_or(member.total_with_tax < 0) as has_negative_invoice,
                bool_or(member.in_scope) as in_scope
            from ranked_members member
            group by member.group_key
        ),
        group_reversal_links as (
            {group_reversal_links_sql}
        )
        {bank_owner_ctes_sql},
        group_relation_components as (
            select distinct
                grouped.group_key,
                component.component_id
            from grouped_invoices grouped
            cross join lateral unnest(grouped.invoice_ids) invoice_member(invoice_id)
            join invoice_aliases alias on alias.invoice_id = invoice_member.invoice_id
            join relation_members member on member.row_id = alias.row_id
            join relation_component_ids component
              on component.relation_id = member.relation_id
            {bank_owner_join_sql}
        ),
        group_relation_ids as (
            select distinct
                grouped.group_key,
                component.relation_id
            from group_relation_components grouped
            join relation_component_ids component
              on component.component_id = grouped.component_id
        ),
        group_bank_rows as (
            select
                relation.group_key,
                coalesce(bank.legacy_mongo_id, bank.id::text) as bank_id,
                bank.txn_direction,
                bank.amount,
                bank.counterparty_name_raw,
                bank.trade_time,
                bank.txn_date,
                bank.account_no,
                bank.summary,
                coalesce(
                    bank.raw_payload->'normalized_payload'->>'imported_bank_name',
                    bank.raw_payload->>'imported_bank_name',
                    ''
                ) as bank_name,
                bool_or(
                    coalesce(
                        member.amount_check->>'matched' = 'true',
                        member.amount_check->>'status' = 'matched',
                        false
                    )
                ) as amount_matched
            from group_relation_ids relation
            join relation_members member on member.relation_id = relation.relation_id
            join app.bank_transactions bank
              on member.row_id in (coalesce(bank.legacy_mongo_id, ''), bank.id::text)
            where member.row_type in ('bank', 'bank_transaction')
              and bank.status <> 'deleted'
            group by
                relation.group_key,
                coalesce(bank.legacy_mongo_id, bank.id::text),
                bank.txn_direction,
                bank.amount,
                bank.counterparty_name_raw,
                bank.trade_time,
                bank.txn_date,
                bank.account_no,
                bank.summary,
                coalesce(
                    bank.raw_payload->'normalized_payload'->>'imported_bank_name',
                    bank.raw_payload->>'imported_bank_name',
                    ''
                )
        ),
        group_banks as (
            select
                grouped.group_key,
                count(distinct bank.bank_id)::bigint as bank_count,
                coalesce(sum(bank.amount) filter (
                    where bank.txn_direction = 'inflow'
                ), 0)::numeric as bank_inflow_total,
                coalesce(sum(bank.amount) filter (
                    where bank.txn_direction = 'outflow'
                ), 0)::numeric as bank_outflow_total,
                coalesce(sum(bank.amount) filter (where bank.amount_matched), 0)::numeric
                    as matched_bank_total,
                (array_agg(bank.counterparty_name_raw order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_counterparty_name,
                (array_agg(coalesce(bank.trade_time, bank.txn_date::timestamptz) order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_trade_time,
                (array_agg(bank.amount order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_amount,
                (array_agg(bank.bank_name order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_name,
                (array_agg(bank.account_no order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_account,
                (array_agg(bank.txn_direction order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_direction,
                (array_agg(bank.summary order by
                    coalesce(bank.trade_time, bank.txn_date::timestamptz) desc,
                    bank.bank_id
                ))[1] as bank_summary
            from grouped_invoices grouped
            left join group_bank_rows bank on bank.group_key = grouped.group_key
            group by grouped.group_key
        )
        {oa_ctes_sql},
        group_facts as (
            select
                grouped.*,
                coalesce(
                    reversal.related_group_keys,
                    array[]::text[]
                ) as red_related_group_keys,
                {oa_facts_sql}
                coalesce(banks.bank_count, 0)::bigint as bank_count,
                coalesce(banks.bank_inflow_total, 0)::numeric as bank_inflow_total,
                coalesce(banks.bank_outflow_total, 0)::numeric as bank_outflow_total,
                coalesce(banks.matched_bank_total, 0)::numeric as matched_bank_total,
                coalesce(banks.bank_counterparty_name, '') as bank_counterparty_name,
                banks.bank_trade_time,
                coalesce(banks.bank_amount, 0)::numeric as bank_amount,
                coalesce(banks.bank_name, '') as bank_name,
                coalesce(banks.bank_account, '') as bank_account,
                coalesce(banks.bank_direction, '') as bank_direction,
                coalesce(banks.bank_summary, '') as bank_summary,
                {match_facts_sql}
            from grouped_invoices grouped
            left join group_reversal_links reversal
              on reversal.group_key = grouped.group_key
            {oa_join_sql}
            left join group_banks banks on banks.group_key = grouped.group_key
        )
        {final_status_sql}
    """


def _input_payment_status_case(
    settings: dict[str, Any],
) -> tuple[str, list[Any]]:
    fragments = [
        "when facts.oa_count > 0 and facts.bank_count > 0 and not facts.fully_matched "
        "then 'pending'"
    ]
    params: list[Any] = []
    fallback = "pending"
    for rule in sorted(
        list(settings.get("rules") or []),
        key=lambda item: (int(item.get("priority") or 0), str(item.get("id") or "")),
    ):
        if not bool(rule.get("enabled", True)):
            continue
        code = str(rule.get("statusCode") or "pending").strip() or "pending"
        conditions = (
            rule.get("conditions")
            if isinstance(rule.get("conditions"), dict)
            else {}
        )
        if conditions.get("fallback") is True:
            fallback = code
            continue
        predicates: list[str] = []
        for key, column in {
            "hasOa": "facts.oa_count > 0",
            "hasBank": "facts.bank_count > 0",
            "fullyMatched": "facts.fully_matched",
            "invoiceOaAmountMatched": "facts.invoice_oa_amount_matched",
        }.items():
            if key in conditions:
                predicates.append(column if bool(conditions[key]) else f"not ({column})")
        applicant = str(conditions.get("applicantName") or "").strip()
        if applicant:
            predicates.append("facts.oa_applicant = %s")
            params.append(applicant)
        if predicates:
            fragments.append(
                f"when {' and '.join(predicates)} then '{_safe_code(code)}'"
            )
    return (
        "case " + " ".join(fragments) + f" else '{_safe_code(fallback)}' end",
        params,
    )


def _where_sql(
    *,
    keyword: str | None,
    invoice_date_from: str | None,
    invoice_date_to: str | None,
    filters: list[dict[str, Any]],
    field_sql: dict[str, str],
    keyword_extra_columns: tuple[str, ...] = (),
    invoice_ids: list[str] | None = None,
    row_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if text := normalize_money_search_query(keyword):
        amount_columns = [
            f"{field_sql[field]}::text"
            for field in _NUMERIC_FILTER_FIELDS
            if field in field_sql
        ]
        search_columns = [
            "invoice_no",
            "seller_name",
            "seller_tax_no",
            "buyer_name",
            "buyer_tax_no",
            "taxable_item_name",
            "oa_applicant",
            "oa_project_name",
            "bank_counterparty_name",
            "bank_summary",
            *keyword_extra_columns,
            *amount_columns,
        ]
        clauses.append(
            f"concat_ws(' ', {', '.join(search_columns)}) ilike %s"
        )
        params.append(f"%{text}%")
    if text := str(invoice_date_from or "").strip():
        clauses.append("invoice_date >= %s::date")
        params.append(text[:10])
    if text := str(invoice_date_to or "").strip():
        clauses.append("invoice_date <= %s::date")
        params.append(text[:10])
    if invoice_ids:
        clauses.append("invoice_ids && %s::text[]")
        params.append(invoice_ids)
    if row_id:
        if row_id.startswith("invoice_usage_row_"):
            clauses.append(
                "'invoice_usage_row_' || substr(encode(digest("
                "case when relation_case_id is not null then 'relation:' || relation_case_id "
                "else identity_key end, 'sha1'), 'hex'), 1, 16) = %s"
            )
        elif row_id.startswith("output_invoice_collection_row_"):
            clauses.append(
                "'output_invoice_collection_row_' || substr("
                "encode(digest(group_key, 'sha1'), 'hex'), 1, 16) = %s"
            )
        else:
            clauses.append(
                "(%s = any(invoice_ids) or exists ("
                "select 1 from group_relation_ids relation "
                "join relation_members member on member.relation_id = relation.relation_id "
                "where relation.group_key = final_rows.group_key and member.row_id = %s"
                "))"
            )
            params.extend([row_id, row_id])
            row_id = None
        if row_id:
            params.append(row_id)
    for item in filters:
        field = str(item.get("field") or "")
        column = field_sql[field]
        operator = str(item.get("operator") or "")
        value = item.get("value")
        values = _texts(item.get("values") or (value if isinstance(value, list) else []))
        if operator == "contains":
            clauses.append(f"coalesce({column}::text, '') ilike %s")
            params.append(f"%{str(value or '')}%")
        elif operator == "equals":
            cast = _filter_cast(field)
            clauses.append(f"{column} = %s{cast}")
            params.append(str(value or ""))
        elif operator == "in":
            cast = _filter_array_cast(field)
            clauses.append(f"{column} = any(%s{cast})")
            params.append(values)
        elif operator == "between":
            minimum, maximum = _range_values(value)
            if minimum not in (None, ""):
                clauses.append(f"{column} >= %s")
                params.append(minimum)
            if maximum not in (None, ""):
                clauses.append(f"{column} <= %s")
                params.append(maximum)
    return (
        ("where " + " and ".join(clauses)) if clauses else "",
        params,
    )


def _filters_without_field(
    filters: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in filters
        if str(item.get("field") or "") != field
    ]


def _order_sql(
    *,
    sort_field: str,
    sort_direction: str,
    field_sql: dict[str, str],
) -> str:
    column = field_sql[sort_field]
    direction = "asc" if sort_direction == "asc" else "desc"
    return f"order by {column} {direction} nulls last, group_key asc"


def _load_facts(
    transaction: Any,
    *,
    group_rows: list[dict[str, Any]],
    supporting_group_rows: list[dict[str, Any]],
    invoice_type: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    all_group_rows = [*group_rows, *supporting_group_rows]
    invoice_ids = _texts(
        invoice_id
        for row in all_group_rows
        for invoice_id in list(row.get("invoice_ids") or [])
    )
    core = PostgresCoreRepository(transaction)
    invoices = core.list_invoices_by_ids(invoice_ids)
    invoices_by_id = {str(invoice.id): invoice for invoice in invoices}
    aliases = _texts(
        alias
        for invoice in invoices
        for alias in _invoice_aliases(invoice)
    )
    relation_rows = (
        transaction.fetch_all(
            """
            with recursive active_relations as (
                select
                    id,
                    case_id,
                    relation_mode,
                    row_ids,
                    row_types,
                    amount_check,
                    special_metadata,
                    raw_payload
                from app.workbench_pair_relations
                where status = 'active'
            ),
            relation_members as (
                select relation.id as relation_id, member.row_id
                from active_relations relation
                cross join lateral unnest(relation.row_ids) member(row_id)
            ),
            relation_reach(relation_id) as (
                select distinct member.relation_id
                from relation_members member
                where member.row_id = any(%s::text[])
                union
                select neighbour.relation_id
                from relation_reach reach
                join relation_members current_member
                  on current_member.relation_id = reach.relation_id
                join relation_members neighbour
                  on neighbour.row_id = current_member.row_id
            )
            select
                relation.case_id,
                relation.relation_mode,
                relation.row_ids,
                relation.row_types,
                relation.amount_check,
                relation.special_metadata,
                relation.raw_payload
            from active_relations relation
            join relation_reach reach on reach.relation_id = relation.id
            order by relation.case_id
            """,
            (aliases,),
        )
        if aliases
        else []
    )
    relations = [_relation_payload(row) for row in relation_rows]
    bank_ids = _texts(
        row_id
        for relation in relations
        for row_id, row_type in _typed_relation_rows(relation)
        if row_type in {"bank", "bank_transaction"}
    )
    oa_ids = _texts(
        row_id
        for relation in relations
        for row_id, row_type in _typed_relation_rows(relation)
        if row_type == "oa"
    )
    transactions = core.list_bank_transactions_by_ids(bank_ids)
    oa_records = (
        PostgresOAWorkflowRepository(
            transaction,
            tenant_id=tenant_id,
        ).list_application_records_by_row_ids(
            oa_ids
        )
        if invoice_type == "input" and oa_ids
        else []
    )
    return {
        "groups": [
            _group_payload(row, invoices_by_id, invoice_type=invoice_type)
            for row in group_rows
            if _group_has_all_invoices(row, invoices_by_id)
        ],
        "supporting_groups": [
            _group_payload(row, invoices_by_id, invoice_type=invoice_type)
            for row in supporting_group_rows
            if _group_has_all_invoices(row, invoices_by_id)
        ],
        "relations": relations,
        "transactions": transactions,
        "oa_records": oa_records,
    }


def _group_payload(
    row: dict[str, Any],
    invoices_by_id: dict[str, Any],
    *,
    invoice_type: str,
) -> dict[str, Any]:
    invoice_ids = [str(value) for value in list(row.get("invoice_ids") or [])]
    line_items = [invoices_by_id[invoice_id] for invoice_id in invoice_ids]
    primary_id = str(row.get("primary_invoice_id") or "")
    primary = invoices_by_id[primary_id]
    payload = {
        "group_key": str(row.get("group_key") or ""),
        "identity_key": str(row.get("identity_key") or ""),
        "primary": primary,
        "line_items": line_items,
    }
    relation_case_id = str(row.get("relation_case_id") or "").strip()
    if invoice_type == "input":
        payload["row_key"] = (
            f"relation:{relation_case_id}"
            if relation_case_id
            else str(row.get("identity_key") or "")
        )
        if relation_case_id:
            payload["relation_group_id"] = relation_case_id
    else:
        payload["status_code"] = str(row.get("status_code") or "")
        payload["collected_amount"] = _money(row.get("collected_amount"))
        payload["pending_amount"] = _money(row.get("pending_amount"))
        payload["bank_attributed"] = bool(row.get("bank_attributed"))
        payload["supporting_group_keys"] = [
            str(value)
            for value in list(row.get("supporting_group_keys") or [])
            if str(value)
        ]
        if relation_case_id:
            payload["relation_case_id"] = relation_case_id
    return payload


def _group_has_all_invoices(
    row: dict[str, Any],
    invoices_by_id: dict[str, Any],
) -> bool:
    invoice_ids = [str(value) for value in list(row.get("invoice_ids") or [])]
    primary_id = str(row.get("primary_invoice_id") or "")
    return bool(
        invoice_ids
        and primary_id in invoices_by_id
        and all(invoice_id in invoices_by_id for invoice_id in invoice_ids)
    )


def _relation_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row_payload(row, "raw_payload")
    payload = dict(raw) if isinstance(raw, dict) else {}
    payload.update(
        {
            "case_id": str(row.get("case_id") or ""),
            "relation_mode": str(row.get("relation_mode") or ""),
            "relation_source": str(
                payload.get("relation_source")
                or row.get("relation_mode")
                or ""
            ),
            "relation_status": "linked",
            "status": "active",
            "row_ids": [str(value) for value in list(row.get("row_ids") or [])],
            "row_types": [
                str(value) for value in list(row.get("row_types") or [])
            ],
            "amount_check": (
                dict(row.get("amount_check"))
                if isinstance(row.get("amount_check"), dict)
                else {}
            ),
            "special_metadata": (
                dict(row.get("special_metadata"))
                if isinstance(row.get("special_metadata"), dict)
                else {}
            ),
        }
    )
    return payload


def _invoice_aliases(invoice: Any) -> list[str]:
    aliases = [str(getattr(invoice, "id", "") or "").strip()]
    for link in list(getattr(invoice, "source_links", []) or []):
        if not isinstance(link, dict):
            continue
        if str(link.get("source_type") or "") != "oa_attachment_invoice":
            continue
        aliases.append(str(link.get("source_workbench_row_id") or "").strip())
    return [value for value in aliases if value]


def _typed_relation_rows(relation: dict[str, Any]) -> list[tuple[str, str]]:
    row_ids = [str(value) for value in list(relation.get("row_ids") or [])]
    row_types = [str(value) for value in list(relation.get("row_types") or [])]
    return [
        (
            row_id,
            row_types[index]
            if index < len(row_types)
            else "bank"
            if row_id.startswith("bank")
            else "oa"
            if row_id.startswith("oa")
            else "invoice",
        )
        for index, row_id in enumerate(row_ids)
    ]


def _facet_counts(
    rows: list[dict[str, Any]],
    *,
    status_labels: dict[str, str],
    status_field: str,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    status_counts: dict[str, int] = {}
    for row in rows:
        field = str(row.get("field") or "")
        value = str(row.get("value") or "")
        if not field or not value:
            continue
        if field == status_field:
            status_counts[value] = int(row.get("option_count") or 0)
            continue
        label = status_labels.get(value, value)
        if field == "bank_direction":
            label = {"inflow": "收入", "outflow": "支出"}.get(value, value)
        result.setdefault(field, []).append(
            {
                "value": value,
                "label": label,
                "count": int(row.get("option_count") or 0),
            }
        )
    result[status_field] = [
        {
            "value": value,
            "label": label,
            "count": status_counts.get(value, 0),
        }
        for value, label in status_labels.items()
    ]
    result[status_field].extend(
        {
            "value": value,
            "label": value,
            "count": count,
        }
        for value, count in sorted(status_counts.items())
        if value not in status_labels
    )
    return result


def _empty_snapshot(
    *,
    page: int,
    page_size: int,
) -> InvoiceUsageCollectionCanonicalSnapshot:
    return InvoiceUsageCollectionCanonicalSnapshot(
        groups=[],
        supporting_groups=[],
        relations=[],
        transactions=[],
        oa_records=[],
        overlays={},
        pagination={"page": page, "pageSize": page_size, "total": 0},
        summary={},
        statistics={},
        facet_counts={},
        payment_status_labels={},
    )


def _month(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if normalized in {"", "all"}:
        return None
    if not _MONTH_RE.fullmatch(normalized):
        raise ValueError("month must be YYYY-MM or all.")
    return normalized


def _range_values(value: Any) -> tuple[Any, Any]:
    if isinstance(value, dict):
        return value.get("min"), value.get("max")
    if isinstance(value, (list, tuple)):
        return (
            value[0] if len(value) > 0 else None,
            value[1] if len(value) > 1 else None,
        )
    return None, None


def _texts(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in list(values or []):
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in list(value or []) if isinstance(row, dict)]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_code(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise ValueError("Invalid payment status code.")
    return value


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value or '0')).quantize(Decimal('0.01'))}"
    except (ValueError, ArithmeticError):
        return "0.00"


def _date_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value or "")
