from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, oa_flow_id_candidates
from fin_ops_platform.services.oa_pending_payment_canonical_rows import relation_member_ids
from fin_ops_platform.services.postgres_repositories.common import decimal_text, int_value, text
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_admission import (
    PostgresOaPendingPaymentAdmissionRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


FILTER_FIELDS = {
    "oa_applicant": ("oa_applicant", "text"),
    "oa_application_type": ("oa_application_type", "text"),
    "oa_project_name": ("oa_project_name", "text"),
    "oa_amount": ("oa_amount", "money"),
    "payment_status": ("payment_status", "text"),
    "bank_trade_time": ("bank_trade_time", "date"),
    "bank_name": ("bank_name", "text"),
    "bank_account": ("bank_account", "text"),
    "bank_direction": ("bank_direction", "text"),
    "bank_counterparty_name": ("bank_counterparty_name", "text"),
    "bank_summary": ("bank_summary", "text"),
    "invoice_no": ("invoice_no", "text"),
    "seller_name": ("seller_name", "text"),
    "invoice_date": ("invoice_date", "date"),
    "invoice_total_with_tax": ("invoice_total_with_tax", "money"),
}
OPTION_FIELDS = (
    "oa_applicant",
    "oa_application_type",
    "oa_project_name",
    "payment_status",
    "bank_name",
    "bank_account",
    "bank_direction",
    "bank_counterparty_name",
    "seller_name",
)


class PostgresOaPendingPaymentQueryRepository:
    """Page-specific canonical PostgreSQL reader for OA pending payments."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @contextmanager
    def snapshot(self) -> Iterator["PostgresOaPendingPaymentQueryRepository"]:
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            raise RuntimeError("OA pending payment canonical queries require a PostgreSQL transaction.")
        with transaction_factory() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield PostgresOaPendingPaymentQueryRepository(transaction)

    def select_page(
        self,
        *,
        tenant_id: str,
        month: str | None,
        keyword: str | None,
        trade_date_from: str | None,
        trade_date_to: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        page: int,
        page_size: int,
        view_mode: str,
    ) -> dict[str, Any]:
        base_where: list[str] = []
        base_params: list[Any] = []
        if month:
            base_where.append("scope_key = %s")
            base_params.append(month)
        if trade_date_from:
            base_where.append("bank_trade_time >= %s::date")
            base_params.append(trade_date_from)
        if trade_date_to:
            base_where.append("bank_trade_time < (%s::date + interval '1 day')")
            base_params.append(trade_date_to)
        if keyword:
            base_where.append("searchable_text ilike %s")
            base_params.append(f"%{keyword}%")
        for clause, params in _filter_clauses(filters):
            base_where.append(clause)
            base_params.extend(params)

        view_clause = (
            "oa_workflow_status = 'in_progress'"
            if view_mode == "in_progress"
            else "oa_workflow_status = 'completed'"
        )
        base_where_sql = " and ".join(base_where) if base_where else "true"
        option_values_sql = ",\n                        ".join(
            (
                f"('{field}', nullif(btrim({field}::text), ''), "
                f"nullif(btrim({_option_label_expression(field)}::text), ''))"
            )
            for field in OPTION_FIELDS
        )
        order_sql = _order_sql(sort_field, sort_direction)
        result = self._connection.fetch_one(
            f"""
            {_CANONICAL_ROWS_CTE},
            base_rows as materialized (
                select *
                from canonical_rows
                where {base_where_sql}
            ),
            filtered_rows as materialized (
                select *
                from base_rows
                where {view_clause}
            ),
            summary as (
                select
                    count(*)::integer as row_count,
                    coalesce(sum(oa_amount), 0) as oa_amount_total,
                    coalesce(sum(bank_paid_total), 0) as bank_paid_total
                from filtered_rows
            ),
            view_counts as (
                select
                    count(distinct oa_id) filter (where oa_workflow_status = 'completed')::integer
                        as completed_count,
                    count(distinct oa_id) filter (where oa_workflow_status = 'in_progress')::integer
                        as in_progress_count
                from base_rows
                cross join lateral unnest(oa_ids) as expanded(oa_id)
            ),
            status_counts as (
                select coalesce(jsonb_object_agg(payment_status, status_count), '{{}}'::jsonb) as payload
                from (
                    select payment_status, count(*)::integer as status_count
                    from filtered_rows
                    group by payment_status
                ) grouped
            ),
            option_values(field, value, label) as (
                select options.field, options.value, options.label
                from filtered_rows
                cross join lateral (
                    values
                        {option_values_sql}
                ) as options(field, value, label)
            ),
            options_by_field as (
                select
                    field,
                    jsonb_agg(
                        jsonb_build_object(
                            'value', value,
                            'label', coalesce(max_label, value),
                            'count', option_count
                        )
                        order by value
                    ) as options
                from (
                    select
                        field,
                        value,
                        max(label) as max_label,
                        count(*)::integer as option_count
                    from option_values
                    where value is not null
                    group by field, value
                ) counts
                group by field
            ),
            filter_options as (
                select coalesce(jsonb_object_agg(field, options), '{{}}'::jsonb) as payload
                from options_by_field
            ),
            page_descriptors as (
                select
                    row_id,
                    scope_key,
                    source_kind,
                    oa_ids,
                    row_number() over (order by {order_sql}) as row_order
                from filtered_rows
                order by {order_sql}
                limit %s offset %s
            ),
            descriptors as (
                select coalesce(
                    jsonb_agg(
                        jsonb_build_object(
                            'row_id', row_id,
                            'scope_key', scope_key,
                            'source_kind', source_kind,
                            'oa_ids', oa_ids
                        )
                        order by row_order
                    ),
                    '[]'::jsonb
                ) as payload
                from page_descriptors
            ),
            inventory as (
                select
                    (select count(*)::integer from canonical_oa) as oa_count,
                    (
                        select count(distinct coalesce(bank.legacy_mongo_id, bank.id::text))::integer
                        from app.bank_transactions bank
                        where bank.status <> 'deleted'
                    ) as bank_transaction_count,
                    (
                        select count(distinct coalesce(invoice.legacy_mongo_id, invoice.id::text))::integer
                        from app.invoices invoice
                        where invoice.status <> 'deleted'
                          and (
                              invoice.invoice_type in (%s, %s)
                              or invoice.invoice_type like %s
                          )
                    ) as input_invoice_count,
                    (
                        select count(*)::integer
                        from app.bank_transactions bank
                        where bank.status <> 'deleted' and bank.txn_direction = 'outflow'
                    ) as expense_transaction_count,
                    (
                        select count(*)::integer
                        from app.bank_transactions bank
                        where bank.status <> 'deleted' and bank.txn_direction = 'inflow'
                    ) as income_transaction_count,
                    (
                        select count(*)::integer from canonical_oa
                        where source_kind = 'completed'
                    ) as completed_oa_count,
                    (
                        select count(*)::integer from canonical_oa
                        where source_kind = 'in_progress'
                    ) as in_progress_oa_count,
                    (
                        select count(distinct oa_id)::integer
                        from canonical_rows
                        cross join lateral unnest(oa_ids) as expanded(oa_id)
                        where payment_status = 'paid'
                    ) as paid_oa_count,
                    (
                        select count(distinct oa_id)::integer
                        from canonical_rows
                        cross join lateral unnest(oa_ids) as expanded(oa_id)
                        where existing_outflow_count > 0
                    ) as linked_bank_oa_count,
                    (
                        select count(distinct oa_id)::integer
                        from canonical_rows
                        cross join lateral unnest(oa_ids) as expanded(oa_id)
                        where existing_invoice_count > 0
                    ) as linked_input_invoice_oa_count
            )
            select
                summary.row_count,
                summary.oa_amount_total,
                summary.bank_paid_total,
                view_counts.completed_count,
                view_counts.in_progress_count,
                status_counts.payload as status_counts,
                filter_options.payload as filter_options,
                descriptors.payload as descriptors,
                inventory.*
            from summary
            cross join view_counts
            cross join status_counts
            cross join filter_options
            cross join descriptors
            cross join inventory
            """,
            (
                text(tenant_id) or "default",
                *base_params,
                page_size,
                (page - 1) * page_size,
                InvoiceType.INPUT.value,
                f"{InvoiceType.INPUT.value}_invoice",
                "进项%",
            ),
        ) or {}
        total = int_value(result.get("row_count"), 0)
        paid_count = int_value(result.get("paid_oa_count"), 0)
        filter_options = {
            field: [dict(option) for option in list(options or []) if isinstance(option, dict)]
            for field, options in dict(result.get("filter_options") or {}).items()
            if field in OPTION_FIELDS
        }
        for option in filter_options.get("bank_direction", []):
            value = text(option.get("value")) or ""
            option["label"] = "支出" if value == "outflow" else "收入" if value == "inflow" else value
        return {
            "descriptors": [
                dict(descriptor)
                for descriptor in list(result.get("descriptors") or [])
                if isinstance(descriptor, dict)
            ],
            "pagination": {"page": page, "pageSize": page_size, "total": total},
            "summary": {
                "rowCount": total,
                "oaAmountTotal": decimal_text(result.get("oa_amount_total")) or "0.00",
                "bankPaidTotal": decimal_text(result.get("bank_paid_total")) or "0.00",
                "statusCounts": dict(result.get("status_counts") or {}),
                "viewCounts": {
                    "completed": int_value(result.get("completed_count"), 0),
                    "in_progress": int_value(result.get("in_progress_count"), 0),
                },
            },
            "statistics": {
                "oa_count": int_value(result.get("oa_count"), 0),
                "bank_transaction_count": int_value(result.get("bank_transaction_count"), 0),
                "input_invoice_count": int_value(result.get("input_invoice_count"), 0),
                "paid_oa_count": paid_count,
                "completed_oa_count": int_value(result.get("completed_oa_count"), 0),
                "in_progress_oa_count": int_value(result.get("in_progress_oa_count"), 0),
                "expense_transaction_count": int_value(result.get("expense_transaction_count"), 0),
                "income_transaction_count": int_value(result.get("income_transaction_count"), 0),
                "unpaid_oa_count": max(int_value(result.get("oa_count"), 0) - paid_count, 0),
                "linked_bank_oa_count": int_value(result.get("linked_bank_oa_count"), 0),
                "linked_input_invoice_oa_count": int_value(result.get("linked_input_invoice_oa_count"), 0),
            },
            "filterOptions": filter_options,
        }

    def bank_transaction_candidates(
        self,
        *,
        tenant_id: str,
        relation_status: str,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        status_clause = "relation_status = %s" if relation_status in {
            "unmatched",
            "matched",
            "linked_in_progress",
        } else "true"
        keyword_clause = "candidate_payload::text like %s" if keyword else "true"
        params: list[Any] = [text(tenant_id) or "default"]
        if status_clause != "true":
            params.append(relation_status)
        if keyword:
            params.append(f"%{keyword}%")
        params.extend((page_size, (page - 1) * page_size))
        result = self._connection.fetch_one(
            f"""
            with formal_relations as materialized (
                select
                    bank_member.row_id as bank_id,
                    relation.case_id as relation_case_id,
                    array(
                        select oa_member.row_id
                        from unnest(relation.row_ids, relation.row_types)
                            with ordinality as oa_member(row_id, row_type, ordinality)
                        where lower(oa_member.row_type) = 'oa'
                        order by oa_member.ordinality
                    ) as oa_row_ids,
                    case
                        when exists (
                            select 1
                            from unnest(relation.row_ids, relation.row_types)
                                as oa_member(row_id, row_type)
                            join app.oa_pending_payment_admissions admission
                              on admission.tenant_id = %s
                             and admission.workflow_status = 'in_progress'
                             and admission.oa_id = oa_member.row_id
                            where lower(oa_member.row_type) = 'oa'
                        ) then 'linked_in_progress'
                        else 'matched'
                    end as relation_status,
                    1 as priority
                from app.workbench_pair_relations relation
                cross join lateral unnest(relation.row_ids, relation.row_types)
                    as bank_member(row_id, row_type)
                where relation.status = 'active'
                  and lower(bank_member.row_type) in ('bank', 'bank_transaction')
            ),
            pending_relations as materialized (
                select
                    bank_id,
                    relation.relation_id as relation_case_id,
                    relation.oa_row_ids,
                    'linked_in_progress'::text as relation_status,
                    0 as priority
                from app.oa_pending_payment_bank_relations relation
                cross join lateral unnest(relation.bank_transaction_ids) as bank_id
                where relation.status = 'active'
            ),
            relation_candidates as materialized (
                select * from pending_relations
                union all
                select * from formal_relations
            ),
            relation_by_bank as materialized (
                select distinct on (bank_id)
                    bank_id,
                    relation_case_id,
                    oa_row_ids,
                    relation_status
                from relation_candidates
                order by bank_id, priority, relation_case_id
            ),
            canonical_banks as materialized (
                select
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'id', ''),
                        bank.legacy_mongo_id,
                        bank.id::text
                    ) as id,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'counterparty_name_raw', ''),
                        bank.counterparty_name_raw,
                        ''
                    ) as counterparty_name,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'trade_time', ''),
                        bank.trade_time::text,
                        bank.txn_date::text,
                        ''
                    ) as trade_time,
                    to_char(abs(bank.amount), 'FM999999999999999990.00') as amount,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                        nullif(bank.raw_payload->'normalized_payload'->>'bank_name', ''),
                        ''
                    ) as bank_name,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'account_no', ''),
                        bank.account_no,
                        ''
                    ) as account_no,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_last4', ''),
                        nullif(bank.raw_payload->'normalized_payload'->>'account_last4', ''),
                        right(
                            coalesce(
                                nullif(bank.raw_payload->'normalized_payload'->>'account_no', ''),
                                bank.account_no,
                                ''
                            ),
                            4
                        )
                    ) as bank_account_last4,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'summary', ''),
                        bank.summary,
                        ''
                    ) as summary,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'remark', ''),
                        bank.remark,
                        ''
                    ) as remark,
                    relation.relation_case_id,
                    coalesce(relation.oa_row_ids, array[]::text[]) as linked_oa_row_ids,
                    coalesce(relation.relation_status, 'unmatched') as relation_status
                from app.bank_transactions bank
                left join relation_by_bank relation
                  on relation.bank_id = coalesce(
                      nullif(bank.raw_payload->'normalized_payload'->>'id', ''),
                      bank.legacy_mongo_id,
                      bank.id::text
                  )
                where bank.status <> 'deleted'
                  and bank.txn_direction = 'outflow'
            ),
            candidates as materialized (
                select
                    canonical_banks.*,
                    jsonb_build_object(
                        'id', id,
                        'counterpartyName', counterparty_name,
                        'tradeTime', trade_time,
                        'amount', amount,
                        'bankName', bank_name,
                        'accountNo', account_no,
                        'accountLast4', right(account_no, 4),
                        'bankAccount', btrim(concat_ws(' ', nullif(bank_name, ''), nullif(bank_account_last4, ''))),
                        'direction', 'outflow',
                        'directionLabel', '支出',
                        'summary', summary,
                        'remark', remark,
                        'relationStatus', relation_status,
                        'relationStatusLabel', case relation_status
                            when 'matched' then '已配对'
                            when 'linked_in_progress' then '已关联进行中OA'
                            else '未配对'
                        end,
                        'relationCaseId', coalesce(relation_case_id, ''),
                        'linkedOaRowIds', linked_oa_row_ids
                    ) as candidate_payload
                from canonical_banks
            ),
            filtered as materialized (
                select *
                from candidates
                where {status_clause}
                  and {keyword_clause}
            ),
            page_rows as (
                select *
                from filtered
                order by trade_time desc, id desc
                limit %s offset %s
            )
            select
                (select count(*)::integer from filtered) as total,
                coalesce(
                    (select jsonb_agg(candidate_payload order by trade_time desc, id desc) from page_rows),
                    '[]'::jsonb
                ) as rows
            """,
            tuple(params),
        ) or {}
        return {
            "rows": [
                dict(row)
                for row in list(result.get("rows") or [])
                if isinstance(row, dict)
            ],
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": int_value(result.get("total"), 0),
            },
        }

    def find_descriptor(
        self,
        *,
        tenant_id: str,
        identifier_kind: str,
        identifier: str,
        month: str | None,
    ) -> dict[str, Any] | None:
        predicates = {
            "row": "row_id = %s",
            "oa": "%s = any(oa_ids)",
            "bank": "%s = any(bank_ids)",
            "invoice": "%s = any(invoice_ids)",
        }
        predicate = predicates.get(identifier_kind)
        if predicate is None:
            raise ValueError(f"Unsupported OA pending payment identifier kind: {identifier_kind}")
        where = [predicate]
        params: list[Any] = [text(tenant_id) or "default", identifier]
        if month:
            where.append("scope_key = %s")
            params.append(month)
        row = self._connection.fetch_one(
            f"""
            {_CANONICAL_ROWS_CTE}
            select row_id, scope_key, source_kind, oa_ids
            from canonical_rows
            where {' and '.join(where)}
            order by scope_key desc, row_id
            limit 1
            """,
            tuple(params),
        )
        return dict(row) if isinstance(row, dict) else None

    def load_facts(
        self,
        descriptors: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        completed_ids = _descriptor_oa_ids(descriptors, source_kind="completed")
        in_progress_ids = _descriptor_oa_ids(descriptors, source_kind="in_progress")
        completed_records = PostgresOAProjectionRepository(self._connection).list_application_records_by_row_ids(
            completed_ids
        )
        in_progress_records = PostgresOaPendingPaymentAdmissionRepository(
            self._connection
        ).list_application_records_by_row_ids(in_progress_ids, tenant_id=tenant_id)
        canonical_snapshot = PostgresWorkbenchRelationRepository(
            self._connection
        ).load_active_workbench_pair_relations_for_row_ids(completed_ids)
        canonical_relations = [
            dict(relation)
            for relation in dict(canonical_snapshot.get("pair_relations") or {}).values()
            if isinstance(relation, dict)
        ]
        pending_relations = PostgresOaPendingPaymentRelationRepository(
            self._connection
        ).active_relations_for_row_ids(in_progress_ids)
        relations = [*canonical_relations, *pending_relations]
        core = PostgresCoreRepository(self._connection)
        bank_transactions = core.list_bank_transactions_by_ids(
            relation_member_ids(relations, row_types={"bank", "bank_transaction"})
        )
        invoices = core.list_invoices_by_ids(relation_member_ids(relations, row_types={"invoice"}))
        records = [*completed_records, *in_progress_records]
        flow_ids = sorted(
            {
                flow_id
                for record in records
                for flow_id in oa_flow_id_candidates(record).payment_flow_ids[:1]
                if flow_id
            }
        )
        statuses = self._payment_statuses(flow_ids, tenant_id=tenant_id)
        return {
            "completed_records": completed_records,
            "in_progress_records": in_progress_records,
            "canonical_relations": canonical_relations,
            "pending_relations": pending_relations,
            "bank_transactions": bank_transactions,
            "invoices": invoices,
            "payment_statuses": statuses,
        }

    def _payment_statuses(
        self,
        flow_ids: list[str],
        *,
        tenant_id: str,
    ) -> dict[str, OAPaymentStatusRecord]:
        if not flow_ids:
            return {}
        rows = self._connection.fetch_all(
            """
            select flow_id, pay_status
            from app.oa_pending_payment_status_snapshots
            where tenant_id = %s
              and flow_id = any(%s::text[])
            order by flow_id
            """,
            (text(tenant_id) or "default", flow_ids),
        )
        return {
            flow_id: OAPaymentStatusRecord(
                flow_id=flow_id,
                pay_status=int_value(row.get("pay_status"), 0),
            )
            for row in list(rows or [])
            if isinstance(row, dict) and (flow_id := text(row.get("flow_id")))
        }


def _filter_clauses(filters: list[dict[str, Any]]) -> list[tuple[str, list[Any]]]:
    clauses: list[tuple[str, list[Any]]] = []
    for item in filters:
        field = text(item.get("field")) or ""
        operator = text(item.get("operator")) or ""
        expression, mode = FILTER_FIELDS[field]
        if operator == "contains":
            clauses.append((f"{expression} ilike %s", [f"%{text(item.get('value')) or ''}%"]))
        elif operator == "equals":
            value = decimal_text(item.get("value")) if mode == "money" else text(item.get("value"))
            cast = "::date" if mode == "date" else ""
            clauses.append((f"{expression} = %s{cast}", [value]))
        elif operator == "in":
            values = [str(value).strip() for value in list(item.get("values") or []) if str(value).strip()]
            if values:
                clauses.append((f"{expression} = any(%s)", [values]))
        elif operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            minimum = bounds.get("min") or bounds.get("from")
            maximum = bounds.get("max") or bounds.get("to")
            if mode == "money":
                minimum = decimal_text(minimum)
                maximum = decimal_text(maximum)
            else:
                minimum = text(minimum)
                maximum = text(maximum)
            cast = "::date" if mode == "date" else ""
            if minimum not in (None, ""):
                clauses.append((f"{expression} >= %s{cast}", [minimum]))
            if maximum not in (None, ""):
                clauses.append((f"{expression} <= %s{cast}", [maximum]))
    return clauses


def _order_sql(sort_field: str, sort_direction: str) -> str:
    expression = FILTER_FIELDS[sort_field][0]
    return f"{expression} {sort_direction} nulls last, row_id"


def _option_label_expression(field: str) -> str:
    if field == "payment_status":
        return "payment_status_label"
    return field


def _descriptor_oa_ids(
    descriptors: list[dict[str, Any]],
    *,
    source_kind: str,
) -> list[str]:
    return sorted(
        {
            str(oa_id).strip()
            for descriptor in descriptors
            if text(descriptor.get("source_kind")) == source_kind
            for oa_id in list(descriptor.get("oa_ids") or [])
            if str(oa_id).strip()
        }
    )


_CANONICAL_ROWS_CTE = """
with requested as (
    select %s::text as tenant_id
),
canonical_oa as materialized (
    select
        'completed'::text as source_kind,
        to_char(oa.scope_month, 'YYYY-MM') as scope_key,
        oa.row_id as oa_id,
        coalesce(nullif(oa.normalized_payload->>'applicant', ''), oa.applicant, '') as oa_applicant,
        coalesce(nullif(oa.normalized_payload->>'apply_type', ''), nullif(oa.form_type, ''), '') as oa_application_type,
        coalesce(
            nullif(oa.normalized_payload->>'project_name_display', ''),
            nullif(oa.normalized_payload->>'project_name', ''),
            oa.project_name,
            ''
        ) as oa_project_name,
        oa.amount as oa_amount,
        oa.normalized_payload as searchable_payload
    from app.oa_applications oa
    where oa.scope_month is not null
      and (
          oa.workflow_status is null
          or oa.workflow_status = ''
          or oa.workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
      )
    union all
    select
        'in_progress'::text as source_kind,
        admission.scope_key,
        admission.oa_id,
        coalesce(nullif(admission.source_payload->>'applicant', ''), admission.applicant, ''),
        coalesce(nullif(admission.source_payload->>'apply_type', ''), ''),
        coalesce(
            nullif(admission.source_payload->>'project_name_display', ''),
            nullif(admission.source_payload->>'project_name', ''),
            admission.project_name_display,
            admission.project_name,
            ''
        ),
        admission.amount,
        admission.source_payload
    from app.oa_pending_payment_admissions admission
    cross join requested
    where admission.tenant_id = requested.tenant_id
      and admission.workflow_status = 'in_progress'
),
completed_relation_groups as materialized (
    select
        'completed'::text as source_kind,
        oa.scope_key,
        relation.case_id as relation_id,
        array_agg(oa.oa_id order by member.ordinality) as oa_ids,
        relation.row_ids,
        relation.row_types
    from app.workbench_pair_relations relation
    cross join lateral unnest(relation.row_ids) with ordinality as member(row_id, ordinality)
    join canonical_oa oa
      on oa.source_kind = 'completed'
     and oa.oa_id = member.row_id
    where relation.status = 'active'
    group by oa.scope_key, relation.case_id, relation.row_ids, relation.row_types
),
pending_relation_groups as materialized (
    select
        'in_progress'::text as source_kind,
        oa.scope_key,
        relation.relation_id,
        array_agg(oa.oa_id order by member.ordinality) as oa_ids,
        relation.oa_row_ids || relation.bank_transaction_ids as row_ids,
        array_fill('oa'::text, array[cardinality(relation.oa_row_ids)])
            || array_fill('bank'::text, array[cardinality(relation.bank_transaction_ids)]) as row_types
    from app.oa_pending_payment_bank_relations relation
    cross join lateral unnest(relation.oa_row_ids) with ordinality as member(row_id, ordinality)
    join canonical_oa oa
      on oa.source_kind = 'in_progress'
     and oa.oa_id = member.row_id
    where relation.status = 'active'
    group by
        oa.scope_key,
        relation.relation_id,
        relation.oa_row_ids,
        relation.bank_transaction_ids
),
relation_groups as materialized (
    select * from completed_relation_groups
    union all
    select * from pending_relation_groups
),
standalone_groups as materialized (
    select
        oa.source_kind,
        oa.scope_key,
        null::text as relation_id,
        array[oa.oa_id]::text[] as oa_ids,
        array[oa.oa_id]::text[] as row_ids,
        array['oa']::text[] as row_types
    from canonical_oa oa
    where not exists (
        select 1
        from relation_groups relation
        where relation.source_kind = oa.source_kind
          and relation.scope_key = oa.scope_key
          and oa.oa_id = any(relation.oa_ids)
    )
),
groups as materialized (
    select * from relation_groups
    union all
    select * from standalone_groups
),
group_oa as materialized (
    select
        groups.source_kind,
        groups.scope_key,
        groups.relation_id,
        groups.oa_ids,
        groups.row_ids,
        groups.row_types,
        case
            when groups.relation_id is null
                then 'oa_pending_payment_row_'
                    || substring(encode(digest(groups.oa_ids[1], 'sha1'), 'hex') from 1 for 16)
            else 'oa_pending_payment_relation_'
                || substring(
                    encode(digest(groups.relation_id || ':' || groups.scope_key, 'sha1'), 'hex')
                    from 1 for 16
                )
        end as row_id,
        (array_agg(oa.oa_applicant order by array_position(groups.oa_ids, oa.oa_id)))[1] as oa_applicant,
        (array_agg(oa.oa_application_type order by array_position(groups.oa_ids, oa.oa_id)))[1]
            as oa_application_type,
        (array_agg(oa.oa_project_name order by array_position(groups.oa_ids, oa.oa_id)))[1]
            as oa_project_name,
        case
            when count(oa.oa_amount) = count(*) then sum(oa.oa_amount)
            else null
        end as oa_amount,
        jsonb_agg(oa.searchable_payload order by array_position(groups.oa_ids, oa.oa_id)) as oa_search_payload
    from groups
    join canonical_oa oa
      on oa.source_kind = groups.source_kind
     and oa.scope_key = groups.scope_key
     and oa.oa_id = any(groups.oa_ids)
    group by
        groups.source_kind,
        groups.scope_key,
        groups.relation_id,
        groups.oa_ids,
        groups.row_ids,
        groups.row_types
),
group_members as materialized (
    select
        group_oa.row_id,
        group_oa.source_kind,
        group_oa.scope_key,
        member.row_id as member_id,
        lower(coalesce(member_type.row_type, '')) as member_type,
        member.ordinality
    from group_oa
    cross join lateral unnest(group_oa.row_ids) with ordinality as member(row_id, ordinality)
    left join lateral unnest(group_oa.row_types) with ordinality as member_type(row_type, ordinality)
      on member_type.ordinality = member.ordinality
),
bank_edges as materialized (
    select
        members.row_id,
        members.member_id,
        members.ordinality,
        bank.txn_direction,
        abs(bank.amount) as bank_amount,
        coalesce(bank.trade_time, bank.txn_date::timestamptz) as bank_trade_time,
        coalesce(
            nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
            nullif(bank.raw_payload->'normalized_payload'->>'bank_name', ''),
            ''
        ) as bank_name,
        btrim(concat_ws(
            ' ',
            coalesce(
                nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                nullif(bank.raw_payload->'normalized_payload'->>'bank_name', ''),
                ''
            ),
            coalesce(
                nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_last4', ''),
                nullif(bank.raw_payload->'normalized_payload'->>'account_last4', ''),
                right(coalesce(bank.account_no, ''), 4)
            )
        )) as bank_account,
        bank.counterparty_name_raw as bank_counterparty_name,
        bank.summary as bank_summary,
        coalesce(bank.raw_payload->'normalized_payload', bank.raw_payload) as searchable_payload,
        row_number() over (
            partition by members.row_id
            order by
                abs(abs(bank.amount) - coalesce(group_oa.oa_amount, 0)),
                coalesce(bank.trade_time, bank.txn_date::timestamptz) desc nulls last,
                coalesce(bank.legacy_mongo_id, bank.id::text)
        ) as primary_rank
    from group_members members
    join group_oa on group_oa.row_id = members.row_id
    join app.bank_transactions bank
      on coalesce(bank.legacy_mongo_id, bank.id::text) = members.member_id
    where (
        members.member_type in ('bank', 'bank_transaction')
        or (members.member_type = '' and (members.member_id like 'bank%%' or members.member_id like 'txn_%%'))
    )
      and bank.txn_direction = 'outflow'
),
bank_aggregates as materialized (
    select
        group_oa.row_id,
        count(bank_edges.member_id) filter (where bank_edges.txn_direction = 'outflow')::integer
            as existing_outflow_count,
        coalesce(
            array_agg(members.member_id order by members.ordinality)
                filter (
                    where members.member_type in ('bank', 'bank_transaction')
                       or (
                           members.member_type = ''
                           and (members.member_id like 'bank%%' or members.member_id like 'txn_%%')
                       )
                ),
            array[]::text[]
        ) as bank_ids,
        coalesce(sum(bank_edges.bank_amount) filter (where bank_edges.txn_direction = 'outflow'), 0)
            as bank_paid_total,
        max(bank_edges.bank_trade_time) filter (where bank_edges.primary_rank = 1) as bank_trade_time,
        max(bank_edges.bank_amount) filter (where bank_edges.primary_rank = 1) as bank_amount,
        max(bank_edges.bank_name) filter (where bank_edges.primary_rank = 1) as bank_name,
        max(bank_edges.bank_account) filter (where bank_edges.primary_rank = 1) as bank_account,
        max(bank_edges.txn_direction) filter (where bank_edges.primary_rank = 1) as bank_direction,
        max(bank_edges.bank_counterparty_name) filter (where bank_edges.primary_rank = 1)
            as bank_counterparty_name,
        max(bank_edges.bank_summary) filter (where bank_edges.primary_rank = 1) as bank_summary,
        coalesce(jsonb_agg(bank_edges.searchable_payload) filter (where bank_edges.member_id is not null), '[]'::jsonb)
            as bank_search_payload
    from group_oa
    left join group_members members on members.row_id = group_oa.row_id
    left join bank_edges
      on bank_edges.row_id = members.row_id
     and bank_edges.member_id = members.member_id
    group by group_oa.row_id
),
invoice_edges as materialized (
    select
        members.row_id,
        members.member_id,
        coalesce(invoice.digital_invoice_no, invoice.invoice_no, '') as invoice_no,
        invoice.invoice_date,
        coalesce(invoice.seller_name, invoice.counterparty_name, '') as seller_name,
        coalesce(invoice.total_with_tax, invoice.amount + coalesce(invoice.tax_amount, 0)) as invoice_total,
        coalesce(invoice.raw_payload->'normalized_payload', invoice.raw_payload) as searchable_payload,
        row_number() over (
            partition by members.row_id
            order by
                abs(
                    coalesce(invoice.total_with_tax, invoice.amount + coalesce(invoice.tax_amount, 0))
                    - coalesce(group_oa.oa_amount, 0)
                ),
                invoice.invoice_date,
                coalesce(invoice.legacy_mongo_id, invoice.id::text)
        ) as primary_rank
    from group_members members
    join group_oa on group_oa.row_id = members.row_id
    join app.invoices invoice
      on coalesce(invoice.legacy_mongo_id, invoice.id::text) = members.member_id
    where members.member_type = 'invoice'
       or (
           members.member_type = ''
           and members.member_id not like 'oa%%'
           and members.member_id not like 'bank%%'
           and members.member_id not like 'txn_%%'
       )
),
invoice_aggregates as materialized (
    select
        group_oa.row_id,
        count(invoice_edges.member_id)::integer as existing_invoice_count,
        max(invoice_edges.invoice_no) filter (where invoice_edges.primary_rank = 1) as invoice_no,
        max(invoice_edges.invoice_date) filter (where invoice_edges.primary_rank = 1) as invoice_date,
        max(invoice_edges.seller_name) filter (where invoice_edges.primary_rank = 1) as seller_name,
        case
            when count(invoice_edges.member_id) > 0 then sum(invoice_edges.invoice_total)
            else null
        end as invoice_total_with_tax,
        coalesce(jsonb_agg(invoice_edges.searchable_payload) filter (where invoice_edges.member_id is not null), '[]'::jsonb)
            as invoice_search_payload,
        coalesce(
            array_agg(invoice_edges.member_id order by invoice_edges.primary_rank)
                filter (where invoice_edges.member_id is not null),
            array[]::text[]
        ) as invoice_ids
    from group_oa
    left join invoice_edges on invoice_edges.row_id = group_oa.row_id
    group by group_oa.row_id
),
canonical_rows as materialized (
    select
        group_oa.row_id,
        group_oa.scope_key,
        group_oa.source_kind,
        group_oa.relation_id,
        group_oa.oa_ids,
        bank_aggregates.bank_ids,
        invoice_aggregates.invoice_ids,
        group_oa.oa_applicant,
        group_oa.oa_application_type,
        group_oa.oa_project_name,
        group_oa.oa_amount,
        case when bank_aggregates.existing_outflow_count > 0 then 'paid' else 'unpaid' end as payment_status,
        case when bank_aggregates.existing_outflow_count > 0 then '已支付' else '未支付' end
            as payment_status_label,
        bank_aggregates.bank_trade_time,
        bank_aggregates.bank_amount,
        bank_aggregates.bank_paid_total,
        bank_aggregates.bank_name,
        bank_aggregates.bank_account,
        bank_aggregates.bank_direction,
        bank_aggregates.bank_counterparty_name,
        bank_aggregates.bank_summary,
        invoice_aggregates.invoice_no,
        invoice_aggregates.invoice_date,
        invoice_aggregates.seller_name,
        invoice_aggregates.invoice_total_with_tax,
        case when group_oa.source_kind = 'in_progress' then 'in_progress' else 'completed' end
            as oa_workflow_status,
        bank_aggregates.existing_outflow_count,
        invoice_aggregates.existing_invoice_count,
        concat_ws(
            ' ',
            group_oa.oa_search_payload::text,
            bank_aggregates.bank_search_payload::text,
            invoice_aggregates.invoice_search_payload::text
        ) as searchable_text
    from group_oa
    join bank_aggregates on bank_aggregates.row_id = group_oa.row_id
    join invoice_aggregates on invoice_aggregates.row_id = group_oa.row_id
)
"""


def list_oa_pending_payment_relation_visibility_gaps(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Compare active OA/outflow facts with the exact canonical page consumer."""

    rows = connection.fetch_all(
        f"""
        {_CANONICAL_ROWS_CTE},
        expected_relations as materialized (
            select distinct
                relation.case_id as relation_id,
                oa.scope_key
            from app.workbench_pair_relations relation
            cross join lateral unnest(relation.row_ids) with ordinality
                as oa_member(row_id, ordinality)
            join canonical_oa oa
              on oa.source_kind = 'completed'
             and oa.oa_id = oa_member.row_id
            where relation.status = 'active'
              and relation.row_types[oa_member.ordinality] = 'oa'
              and exists (
                  select 1
                  from unnest(relation.row_ids) with ordinality
                      as bank_member(row_id, ordinality)
                  join app.bank_transactions bank
                    on coalesce(bank.legacy_mongo_id, bank.id::text) = bank_member.row_id
                  where relation.row_types[bank_member.ordinality]
                            in ('bank', 'bank_transaction')
                    and bank.txn_direction = 'outflow'
              )
        )
        /* check: oa_pending_payment_relation_visibility */
        select
            expected.relation_id as subject_id,
            expected.scope_key,
            consumer.existing_outflow_count,
            consumer.payment_status
        from expected_relations expected
        left join canonical_rows consumer
          on consumer.source_kind = 'completed'
         and consumer.relation_id = expected.relation_id
         and consumer.scope_key = expected.scope_key
        where consumer.relation_id is null
           or consumer.existing_outflow_count = 0
           or consumer.payment_status <> 'paid'
        order by expected.scope_key, expected.relation_id
        limit %s
        """,
        (text(tenant_id) or "default", max(int(limit), 1)),
    )
    return [dict(row) for row in list(rows or []) if isinstance(row, dict)]
