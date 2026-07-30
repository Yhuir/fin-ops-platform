from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.services.postgres_repositories.oa_projection import (
    COMPLETED_WORKFLOW_STATUS_ALIASES,
)


BATCH_ACCOUNTING_COUNTERPARTY_NAME = "批量账务集中处理"

_BANK_ID_SQL = "coalesce(bank.legacy_mongo_id, bank.id::text)"
_BANK_DATE_SQL = "coalesce(bank.txn_date, bank.trade_time::date, bank.pay_receive_time::date)"
_OA_DAILY_REIMBURSEMENT_SQL = """
    (
        coalesce(oa.form_type, '')
        || ' '
        || coalesce(oa.normalized_payload->>'apply_type', '')
        || ' '
        || coalesce(oa.normalized_payload->>'expense_type', '')
    ) like '%%日常报销%%'
"""
_OA_SEARCH_SQL = """
    (
        %s = ''
        or concat_ws(
            ' ',
            oa.row_id,
            oa.applicant,
            oa.project_name,
            oa.amount::text,
            oa.normalized_payload->>'reason',
            oa.normalized_payload->>'remark'
        ) ilike %s
    )
"""
_OA_NOT_LINKED_TO_BANK_SQL = f"""
    not exists (
        select 1
        from app.workbench_pair_relations relation
        where relation.status = 'active'
          and oa.row_id = any(relation.row_ids)
          and exists (
              select 1
              from app.bank_transactions linked_bank
              where coalesce(linked_bank.legacy_mongo_id, linked_bank.id::text) = any(relation.row_ids)
                and linked_bank.status <> 'deleted'
          )
    )
"""
_BANK_NOT_LINKED_SQL = f"""
    not exists (
        select 1
        from app.workbench_pair_relations relation
        where relation.status = 'active'
          and {_BANK_ID_SQL} = any(relation.row_ids)
    )
"""


class PostgresBatchAccountingQueryRepository:
    """Page-owned canonical queries for Batch Accounting."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Batch accounting query repository requires a PostgreSQL connection.")
        self._connection = connection

    def list_snapshot(
        self,
        *,
        bank_year: str,
        bucket: str,
        bank_page: int,
        bank_page_size: int,
        oa_page: int,
        oa_page_size: int,
        oa_search: str = "",
    ) -> dict[str, Any]:
        bank_start = f"{bank_year}-01-01"
        search = str(oa_search or "").strip()
        search_pattern = f"%{search}%"
        completed_statuses = sorted(COMPLETED_WORKFLOW_STATUS_ALIASES)
        with self._snapshot_transaction() as transaction:
            summary = transaction.fetch_one(
                f"""
                select
                    (
                        select count(*)::integer
                        from app.bank_transactions bank
                        where bank.status <> 'deleted'
                          and btrim(bank.counterparty_name_raw) = %s
                          and {_BANK_DATE_SQL} >= %s::date
                          and {_BANK_DATE_SQL} < (%s::date + interval '1 year')
                          and bank.txn_direction = 'outflow'
                          and bank.amount > 0
                          and {_BANK_NOT_LINKED_SQL}
                    ) as unsubmitted_count,
                    (
                        select count(*)::integer
                        from app.workbench_pair_relations relation
                        where relation.status = 'active'
                          and relation.relation_mode = 'batch_accounting'
                          and exists (
                              select 1
                              from app.bank_transactions submitted_bank
                              where coalesce(submitted_bank.legacy_mongo_id, submitted_bank.id::text)
                                    = any(relation.row_ids)
                                and submitted_bank.status <> 'deleted'
                                and coalesce(
                                      submitted_bank.txn_date,
                                      submitted_bank.trade_time::date,
                                      submitted_bank.pay_receive_time::date
                                    ) >= %s::date
                                and coalesce(
                                      submitted_bank.txn_date,
                                      submitted_bank.trade_time::date,
                                      submitted_bank.pay_receive_time::date
                                    ) < (%s::date + interval '1 year')
                          )
                    ) as submitted_count,
                    (
                        select count(*)::integer
                        from app.oa_applications oa
                        where oa.status <> 'deleted'
                          and (
                              oa.workflow_status is null
                              or oa.workflow_status = ''
                              or oa.workflow_status = any(%s::text[])
                          )
                          and {_OA_DAILY_REIMBURSEMENT_SQL}
                          and {_OA_NOT_LINKED_TO_BANK_SQL}
                          and {_OA_SEARCH_SQL}
                    ) as oa_count
                """,
                (
                    BATCH_ACCOUNTING_COUNTERPARTY_NAME,
                    bank_start,
                    bank_start,
                    bank_start,
                    bank_start,
                    completed_statuses,
                    search,
                    search_pattern,
                ),
            ) or {}
            if bucket == "submitted":
                relations = self._submitted_relations(
                    transaction,
                    bank_start=bank_start,
                    page=bank_page,
                    page_size=bank_page_size,
                )
                member_rows = self._relation_member_rows(
                    transaction,
                    row_ids=[
                        str(row_id)
                        for relation in relations
                        for row_id in list(relation.get("row_ids") or [])
                        if str(row_id or "").strip()
                    ],
                )
                bank_rows = [dict(relation.get("bank_row") or {}) for relation in relations]
                return {
                    "summary": summary,
                    "bank_rows": bank_rows,
                    "oa_rows": [],
                    "relations": relations,
                    "member_rows": member_rows,
                    "pagination": {
                        "bank_rows": self._page_payload(
                            page=bank_page,
                            page_size=bank_page_size,
                            total=self._int(summary.get("submitted_count")),
                        )
                    },
                }

            bank_rows = self._unsubmitted_bank_rows(
                transaction,
                bank_start=bank_start,
                page=bank_page,
                page_size=bank_page_size,
            )
            oa_rows = self._eligible_oa_rows(
                transaction,
                completed_statuses=completed_statuses,
                page=oa_page,
                page_size=oa_page_size,
                search=search,
                search_pattern=search_pattern,
            )
            invoice_rows = self._oa_attachment_invoice_rows(
                transaction,
                oa_row_ids=[str(row.get("id") or "") for row in oa_rows],
            )
            return {
                "summary": summary,
                "bank_rows": bank_rows,
                "oa_rows": oa_rows,
                "invoice_rows": invoice_rows,
                "relations": [],
                "member_rows": [],
                "pagination": {
                    "bank_rows": self._page_payload(
                        page=bank_page,
                        page_size=bank_page_size,
                        total=self._int(summary.get("unsubmitted_count")),
                    ),
                    "oa_rows": self._page_payload(
                        page=oa_page,
                        page_size=oa_page_size,
                        total=self._int(summary.get("oa_count")),
                    ),
                },
            }

    def load_submission_context(
        self,
        *,
        bank_year: str,
        bank_row_id: str,
        oa_row_ids: list[str],
    ) -> dict[str, Any]:
        bank_start = f"{bank_year}-01-01"
        normalized_oa_ids = self._dedupe(oa_row_ids)
        completed_statuses = sorted(COMPLETED_WORKFLOW_STATUS_ALIASES)
        with self._snapshot_transaction() as transaction:
            bank_row = transaction.fetch_one(
                f"""
                select
                    {_BANK_ID_SQL} as id,
                    'bank'::text as type,
                    coalesce(
                        to_char(bank.trade_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                        to_char(bank.pay_receive_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                        bank.txn_date::text,
                        ''
                    ) as trade_time,
                    bank.counterparty_name_raw as counterparty_name,
                    bank.amount as debit_amount,
                    bank.signed_amount,
                    bank.txn_direction as direction,
                    coalesce(
                        nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                        nullif(bank.raw_payload->'normalized_payload'->>'bank_name', ''),
                        ''
                    ) as bank_name,
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
                    ) as account_last4,
                    bank.account_no,
                    1::integer as version
                from app.bank_transactions bank
                where {_BANK_ID_SQL} = %s
                  and bank.status <> 'deleted'
                  and {_BANK_DATE_SQL} >= %s::date
                  and {_BANK_DATE_SQL} < (%s::date + interval '1 year')
                limit 1
                """,
                (bank_row_id, bank_start, bank_start),
            )
            oa_rows = transaction.fetch_all(
                f"""
                select
                    oa.row_id as id,
                    'oa'::text as type,
                    oa.applicant,
                    coalesce(
                        nullif(oa.normalized_payload->>'apply_time', ''),
                        nullif(oa.normalized_payload->>'application_time', ''),
                        oa.application_date::text,
                        ''
                    ) as apply_time,
                    oa.project_name,
                    oa.amount,
                    coalesce(
                        nullif(oa.normalized_payload->>'reason', ''),
                        nullif(oa.normalized_payload->>'remark', ''),
                        ''
                    ) as reason,
                    coalesce(nullif(oa.normalized_payload->>'apply_type', ''), oa.form_type, '') as apply_type,
                    coalesce(oa.normalized_payload->>'expense_type', '') as expense_type
                from app.oa_applications oa
                where oa.row_id = any(%s::text[])
                  and oa.status <> 'deleted'
                  and (
                      oa.workflow_status is null
                      or oa.workflow_status = ''
                      or oa.workflow_status = any(%s::text[])
                  )
                order by array_position(%s::text[], oa.row_id)
                """,
                (normalized_oa_ids, completed_statuses, normalized_oa_ids),
            )
            invoice_rows = self._oa_attachment_invoice_rows(
                transaction,
                oa_row_ids=normalized_oa_ids,
            )
            return {
                "bank_rows": [dict(bank_row)] if isinstance(bank_row, dict) else [],
                "oa_rows": oa_rows,
                "invoice_rows": invoice_rows,
            }

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _unsubmitted_bank_rows(
        transaction: Any,
        *,
        bank_start: str,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        return transaction.fetch_all(
            f"""
            select
                {_BANK_ID_SQL} as id,
                'bank'::text as type,
                coalesce(
                    to_char(bank.trade_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                    to_char(bank.pay_receive_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                    bank.txn_date::text,
                    ''
                ) as trade_time,
                bank.counterparty_name_raw as counterparty_name,
                bank.amount as debit_amount,
                bank.signed_amount,
                bank.txn_direction as direction,
                coalesce(
                    nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                    nullif(bank.raw_payload->'normalized_payload'->>'bank_name', ''),
                    ''
                ) as bank_name,
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
                ) as account_last4,
                bank.account_no,
                1::integer as version
            from app.bank_transactions bank
            where bank.status <> 'deleted'
              and btrim(bank.counterparty_name_raw) = %s
              and {_BANK_DATE_SQL} >= %s::date
              and {_BANK_DATE_SQL} < (%s::date + interval '1 year')
              and bank.txn_direction = 'outflow'
              and bank.amount > 0
              and {_BANK_NOT_LINKED_SQL}
            order by coalesce(bank.trade_time, bank.pay_receive_time, bank.txn_date::timestamptz) desc,
                     {_BANK_ID_SQL}
            limit %s offset %s
            """,
            (
                BATCH_ACCOUNTING_COUNTERPARTY_NAME,
                bank_start,
                bank_start,
                page_size,
                (page - 1) * page_size,
            ),
        )

    @staticmethod
    def _eligible_oa_rows(
        transaction: Any,
        *,
        completed_statuses: list[str],
        page: int,
        page_size: int,
        search: str,
        search_pattern: str,
    ) -> list[dict[str, Any]]:
        return transaction.fetch_all(
            f"""
            select
                oa.row_id as id,
                'oa'::text as type,
                oa.applicant,
                coalesce(
                    nullif(oa.normalized_payload->>'apply_time', ''),
                    nullif(oa.normalized_payload->>'application_time', ''),
                    oa.application_date::text,
                    ''
                ) as apply_time,
                oa.project_name,
                oa.amount,
                coalesce(
                    nullif(oa.normalized_payload->>'reason', ''),
                    nullif(oa.normalized_payload->>'remark', ''),
                    ''
                ) as reason,
                coalesce(nullif(oa.normalized_payload->>'apply_type', ''), oa.form_type, '') as apply_type,
                coalesce(oa.normalized_payload->>'expense_type', '') as expense_type
            from app.oa_applications oa
            where oa.status <> 'deleted'
              and (
                  oa.workflow_status is null
                  or oa.workflow_status = ''
                  or oa.workflow_status = any(%s::text[])
              )
              and {_OA_DAILY_REIMBURSEMENT_SQL}
              and {_OA_NOT_LINKED_TO_BANK_SQL}
              and {_OA_SEARCH_SQL}
            order by oa.application_date desc nulls last,
                     nullif(oa.normalized_payload->>'apply_time', '') desc nulls last,
                     oa.row_id
            limit %s offset %s
            """,
            (
                completed_statuses,
                search,
                search_pattern,
                page_size,
                (page - 1) * page_size,
            ),
        )

    @staticmethod
    def _oa_attachment_invoice_rows(
        transaction: Any,
        *,
        oa_row_ids: list[str],
    ) -> list[dict[str, Any]]:
        normalized_ids = PostgresBatchAccountingQueryRepository._dedupe(oa_row_ids)
        if not normalized_ids:
            return []
        return transaction.fetch_all(
            """
            select distinct on (invoice_row_id, source_oa_id)
                invoice_row_id as id,
                'invoice'::text as type,
                'oa_attachment_invoice'::text as source_kind,
                source_oa_id,
                source_oa_id as derived_from_oa_id,
                invoice_no,
                invoice_code,
                digital_invoice_no,
                invoice_date as issue_date,
                seller_name,
                buyer_name,
                amount,
                total_with_tax,
                source_attachment_key,
                attachment_filename
            from (
                select
                    coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_row_id,
                    regexp_replace(
                        coalesce(
                            nullif(source_link.value->>'derived_from_oa_id', ''),
                            nullif(source_link.value->>'source_expense_item_id', ''),
                            nullif(source_link.value->>'source_workbench_row_id', '')
                        ),
                        ':item:.*$',
                        ''
                    ) as source_oa_id,
                    invoice.invoice_no,
                    invoice.invoice_code,
                    invoice.digital_invoice_no,
                    invoice.invoice_date,
                    invoice.seller_name,
                    invoice.buyer_name,
                    invoice.amount,
                    invoice.total_with_tax,
                    source_link.value->>'source_attachment_key' as source_attachment_key,
                    attachment.filename as attachment_filename
                from app.invoices invoice
                cross join lateral jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb))
                    as source_link(value)
                left join app.oa_attachments attachment
                  on attachment.source_attachment_key = source_link.value->>'source_attachment_key'
                where invoice.status <> 'deleted'
                  and source_link.value->>'source_type' = 'oa_attachment_invoice'
            ) linked_invoice
            where source_oa_id = any(%s::text[])
            order by invoice_row_id, source_oa_id
            """,
            (normalized_ids,),
        )

    @staticmethod
    def _submitted_relations(
        transaction: Any,
        *,
        bank_start: str,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        rows = transaction.fetch_all(
            """
            select
                relation.case_id,
                relation.relation_mode,
                relation.status,
                relation.version,
                relation.month_scope,
                relation.row_ids,
                relation.row_types,
                relation.note,
                relation.amount_check,
                relation.special_metadata,
                relation.created_by,
                relation.created_at,
                relation.updated_at,
                jsonb_build_object(
                    'id', bank.row_id,
                    'type', 'bank',
                    'trade_time', bank.trade_time,
                    'counterparty_name', bank.counterparty_name,
                    'debit_amount', bank.amount,
                    'signed_amount', bank.signed_amount,
                    'direction', bank.direction,
                    'bank_name', bank.bank_name,
                    'account_last4', bank.account_last4,
                    'account_no', bank.account_no,
                    'version', relation.version,
                    'relation_id', relation.case_id
                ) as bank_row
            from app.workbench_pair_relations relation
            join lateral (
                select
                    coalesce(source.legacy_mongo_id, source.id::text) as row_id,
                    coalesce(
                        to_char(source.trade_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                        to_char(source.pay_receive_time, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                        source.txn_date::text,
                        ''
                    ) as trade_time,
                    source.counterparty_name_raw as counterparty_name,
                    source.amount,
                    source.signed_amount,
                    source.txn_direction as direction,
                    coalesce(
                        nullif(source.raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                        nullif(source.raw_payload->'normalized_payload'->>'bank_name', ''),
                        ''
                    ) as bank_name,
                    coalesce(
                        nullif(source.raw_payload->'normalized_payload'->>'imported_bank_last4', ''),
                        nullif(source.raw_payload->'normalized_payload'->>'account_last4', ''),
                        right(
                            coalesce(
                                nullif(source.raw_payload->'normalized_payload'->>'account_no', ''),
                                source.account_no,
                                ''
                            ),
                            4
                        )
                    ) as account_last4,
                    source.account_no
                from app.bank_transactions source
                where coalesce(source.legacy_mongo_id, source.id::text) = any(relation.row_ids)
                  and source.status <> 'deleted'
                  and coalesce(source.txn_date, source.trade_time::date, source.pay_receive_time::date)
                        >= %s::date
                  and coalesce(source.txn_date, source.trade_time::date, source.pay_receive_time::date)
                        < (%s::date + interval '1 year')
                order by array_position(
                    relation.row_ids,
                    coalesce(source.legacy_mongo_id, source.id::text)
                )
                limit 1
            ) bank on true
            where relation.status = 'active'
              and relation.relation_mode = 'batch_accounting'
            order by relation.updated_at desc, relation.case_id
            limit %s offset %s
            """,
            (bank_start, bank_start, page_size, (page - 1) * page_size),
        )
        return [dict(row) for row in rows]

    @staticmethod
    def _relation_member_rows(transaction: Any, *, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids = PostgresBatchAccountingQueryRepository._dedupe(row_ids)
        if not normalized_ids:
            return []
        return transaction.fetch_all(
            """
            select 'oa'::text as member_type, oa.row_id as id,
                   jsonb_build_object(
                       'id', oa.row_id,
                       'type', 'oa',
                       'applicant', oa.applicant,
                       'apply_time', coalesce(
                           nullif(oa.normalized_payload->>'apply_time', ''),
                           nullif(oa.normalized_payload->>'application_time', ''),
                           oa.application_date::text,
                           ''
                       ),
                       'project_name', oa.project_name,
                       'amount', oa.amount,
                       'reason', coalesce(
                           nullif(oa.normalized_payload->>'reason', ''),
                           nullif(oa.normalized_payload->>'remark', ''),
                           ''
                       ),
                       'apply_type', coalesce(
                           nullif(oa.normalized_payload->>'apply_type', ''),
                           oa.form_type,
                           ''
                       ),
                       'expense_type', coalesce(oa.normalized_payload->>'expense_type', '')
                   ) as payload
            from app.oa_applications oa
            where oa.row_id = any(%s::text[])
              and oa.status <> 'deleted'
            union all
            select 'invoice'::text as member_type,
                   coalesce(invoice.legacy_mongo_id, invoice.id::text) as id,
                   jsonb_build_object(
                       'id', coalesce(invoice.legacy_mongo_id, invoice.id::text),
                       'type', 'invoice',
                       'invoice_type', invoice.invoice_type,
                       'invoice_no', invoice.invoice_no,
                       'invoice_code', invoice.invoice_code,
                       'digital_invoice_no', invoice.digital_invoice_no,
                       'issue_date', invoice.invoice_date::text,
                       'seller_name', invoice.seller_name,
                       'buyer_name', invoice.buyer_name,
                       'amount', invoice.amount,
                       'total_with_tax', invoice.total_with_tax,
                       'source_oa_id', invoice_link.source_oa_id
                   ) as payload
            from app.invoices invoice
            left join lateral (
                select regexp_replace(
                           coalesce(
                               nullif(source_link.value->>'derived_from_oa_id', ''),
                               nullif(source_link.value->>'source_expense_item_id', ''),
                               nullif(source_link.value->>'source_workbench_row_id', '')
                           ),
                           ':item:.*$',
                           ''
                       ) as source_oa_id
                from jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb))
                    as source_link(value)
                where source_link.value->>'source_type' = 'oa_attachment_invoice'
                  and regexp_replace(
                          coalesce(
                              nullif(source_link.value->>'derived_from_oa_id', ''),
                              nullif(source_link.value->>'source_expense_item_id', ''),
                              nullif(source_link.value->>'source_workbench_row_id', '')
                          ),
                          ':item:.*$',
                          ''
                      ) = any(%s::text[])
                order by source_link.value::text
                limit 1
            ) invoice_link on true
            where coalesce(invoice.legacy_mongo_id, invoice.id::text) = any(%s::text[])
              and invoice.status <> 'deleted'
            order by member_type, id
            """,
            (normalized_ids, normalized_ids, normalized_ids),
        )

    @staticmethod
    def _page_payload(*, page: int, page_size: int, total: int) -> dict[str, int]:
        return {
            "page": page,
            "page_size": page_size,
            "pageSize": page_size,
            "total": total,
        }

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
