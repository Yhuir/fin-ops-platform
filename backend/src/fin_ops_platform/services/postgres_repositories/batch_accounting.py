from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
    bank_category_classification_cte,
)
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
          and relation.row_ids @> array[oa.row_id]::text[]
          and exists (
              select 1
              from app.bank_transactions linked_bank
              where relation.row_ids @> array[
                        coalesce(linked_bank.legacy_mongo_id, linked_bank.id::text)
                    ]::text[]
                and linked_bank.status <> 'deleted'
          )
    )
"""
_BANK_NOT_LINKED_SQL = f"""
    not exists (
        select 1
        from app.workbench_pair_relations relation
        where relation.status = 'active'
          and relation.row_ids @> array[{_BANK_ID_SQL}]::text[]
    )
"""


class PostgresBatchAccountingQueryRepository:
    """Page-owned canonical queries for Batch Accounting."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Batch accounting query repository requires a PostgreSQL connection.")
        self._connection = connection

    @staticmethod
    def _candidate_cte(bank_year: str | None) -> tuple[str, tuple[Any, ...]]:
        bank_start = f"{bank_year}-01-01" if bank_year is not None else None
        return (
            f"""batch_bank_candidates as materialized (
            select {_BANK_ID_SQL} as row_id
            from app.bank_transactions bank
            where bank.status <> 'deleted' and btrim(bank.counterparty_name_raw) = %s
              and bank.txn_direction = 'outflow' and bank.amount > 0
              and (%s::date is null or ({_BANK_DATE_SQL} >= %s::date
                   and {_BANK_DATE_SQL} < %s::date + interval '1 year'))
        )""",
            (BATCH_ACCOUNTING_COUNTERPARTY_NAME, bank_start, bank_start, bank_start),
        )

    def list_snapshot(
        self,
        *,
        bank_year: str | None,
        bucket: str,
        bank_page: int,
        bank_page_size: int,
        oa_page: int,
        oa_page_size: int,
        oa_search: str = "",
    ) -> dict[str, Any]:
        bank_start = f"{bank_year}-01-01" if bank_year is not None else None
        search = str(oa_search or "").strip()
        search_pattern = f"%{search}%"
        completed_statuses = sorted(COMPLETED_WORKFLOW_STATUS_ALIASES)
        with self._snapshot_transaction() as transaction:
            source = (
                transaction.fetch_one(
                    f"""
                select
                    coalesce(
                        (
                            select settings_payload
                            from app.app_settings
                            where settings_key = 'app_settings'
                        ),
                        '{{}}'::jsonb
                    ) as settings_payload,
                    (
                        select count(*)::integer
                        from app.workbench_pair_relations relation
                        where relation.status = 'active'
                          and relation.relation_mode = 'batch_accounting'
                          and exists (
                              select 1
                              from app.bank_transactions submitted_bank
                              where relation.row_ids @> array[
                                        coalesce(
                                            submitted_bank.legacy_mongo_id,
                                            submitted_bank.id::text
                                        )
                                    ]::text[]
                                and submitted_bank.status <> 'deleted'
                                and (%s::date is null or (coalesce(
                                      submitted_bank.txn_date,
                                      submitted_bank.trade_time::date,
                                      submitted_bank.pay_receive_time::date
                                    ) >= %s::date
                                and coalesce(
                                      submitted_bank.txn_date,
                                      submitted_bank.trade_time::date,
                                      submitted_bank.pay_receive_time::date
                                    ) < (%s::date + interval '1 year')))
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
                    (bank_start, bank_start, bank_start, completed_statuses, search, search_pattern),
                )
                or {}
            )
            settings = AppSettingsService.normalize_settings_payload(source.get("settings_payload") or {})
            candidates, candidate_params = self._candidate_cte(bank_year)
            classifier, classifier_params = bank_category_classification_cte(
                definitions=settings["bank_transaction_tags"]["definitions"],
                date_from=None,
                date_to=None,
                candidate_transaction_relation="batch_bank_candidates",
                defer_full_payload=True,
            )
            selected = settings["batch_accounting_tag_selection"]
            tag_columns = """c.effective_category_code as tag_code,
                c.effective_category_label as tag_label,
                c.effective_category_primary_label as tag_primary_label,
                c.effective_category_sub_label as tag_sub_label,
                c.effective_category_source as tag_source"""
            if bucket == "submitted":
                page_cte = f"""selected_relations as ({self._submitted_relations_sql()}),
                    tagged_relations as (select r.*, r.bank_row || jsonb_build_object(
                        'tag_code', c.effective_category_code, 'tag_label', c.effective_category_label,
                        'tag_primary_label', c.effective_category_primary_label,
                        'tag_sub_label', c.effective_category_sub_label,
                        'tag_source', c.effective_category_source) as tagged_bank_row
                      from selected_relations r left join classified_with_semantics c
                        on c.row_id=r.bank_row->>'id')"""
                page_output = """'[]'::jsonb as bank_rows,
                    coalesce((select jsonb_agg((to_jsonb(r)-'tagged_bank_row') ||
                        jsonb_build_object('bank_row',r.tagged_bank_row)
                        order by r.updated_at desc,r.case_id) from tagged_relations r),'[]'::jsonb) as relations"""
                page_params = (bank_start, bank_start, bank_start, bank_page_size, (bank_page - 1) * bank_page_size)
            else:
                page_cte = f"""selected_keys as materialized (
                    select e.row_id from eligible e join app.bank_transactions bank
                      on {_BANK_ID_SQL}=e.row_id
                    order by {_BANK_DATE_SQL} desc nulls last, e.row_id
                    limit %s offset %s
                ), page_rows as (select
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
                    1::integer as version,
                    to_char({_BANK_DATE_SQL}, 'YYYY') as bank_year,
                    {_BANK_DATE_SQL} as bank_date,
                    {tag_columns}
                    from selected_keys p join app.bank_transactions bank on {_BANK_ID_SQL}=p.row_id
                    join classified_with_semantics c on c.row_id=p.row_id)"""
                page_output = """coalesce((select jsonb_agg(to_jsonb(p)-'bank_date'
                    order by p.bank_date desc nulls last,p.id)
                    from page_rows p),'[]'::jsonb) as bank_rows, '[]'::jsonb as relations"""
                page_params = (bank_page_size, (bank_page - 1) * bank_page_size)
            page = (
                transaction.fetch_one(
                    f"""with {candidates}, {classifier},
                eligible as materialized (select c.row_id from classified_with_semantics c
                    join batch_bank_candidates candidate on candidate.row_id=c.row_id
                    join app.bank_transactions bank on {_BANK_ID_SQL}=c.row_id
                    where c.effective_category_code=any(%s::text[]) and {_BANK_NOT_LINKED_SQL}),
                {page_cte}
                select (select count(*) from eligible) as unsubmitted_count, {page_output}
                """,
                    (*candidate_params, *classifier_params, selected["selected_tag_codes"], *page_params),
                )
                or {}
            )
            summary = {
                "unsubmitted_count": self._int(page.get("unsubmitted_count")),
                "submitted_count": self._int(source.get("submitted_count")),
                "oa_count": self._int(source.get("oa_count")),
            }
            relations = list(page.get("relations") or [])
            bank_rows = (
                [row["bank_row"] for row in relations] if bucket == "submitted" else list(page.get("bank_rows") or [])
            )
            result = {
                "summary": summary,
                "bank_rows": bank_rows,
                "oa_rows": [],
                "relations": relations,
                "member_rows": [],
                "invoice_rows": [],
                "tag_selection_version": int(selected["version"]),
                "pagination": {
                    "bank_rows": self._page_payload(
                        page=bank_page,
                        page_size=bank_page_size,
                        total=summary["submitted_count" if bucket == "submitted" else "unsubmitted_count"],
                    )
                },
            }
            if bucket == "submitted":
                result["member_rows"] = self._relation_member_rows(
                    transaction, row_ids=[str(value) for relation in relations for value in relation["row_ids"]]
                )
            else:
                result["oa_rows"] = self._eligible_oa_rows(
                    transaction,
                    completed_statuses=completed_statuses,
                    page=oa_page,
                    page_size=oa_page_size,
                    search=search,
                    search_pattern=search_pattern,
                )
                result["invoice_rows"] = self._oa_attachment_invoice_rows(
                    transaction, oa_row_ids=[row["id"] for row in result["oa_rows"]]
                )
                result["pagination"]["oa_rows"] = self._page_payload(
                    page=oa_page, page_size=oa_page_size, total=summary["oa_count"]
                )
            return result

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
                    to_char({_BANK_DATE_SQL}, 'YYYY') as bank_year,
                    {_BANK_DATE_SQL}::text as canonical_bank_date,
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
                    1::integer as version,
                    coalesce(
                        (
                            select settings_payload
                            from app.app_settings
                            where settings_key = 'app_settings'
                        ),
                        '{{}}'::jsonb
                    ) as settings_payload
                from app.bank_transactions bank
                where {_BANK_ID_SQL} = %s
                  and bank.status <> 'deleted'
                  and {_BANK_DATE_SQL} >= %s::date
                  and {_BANK_DATE_SQL} < (%s::date + interval '1 year')
                limit 1
                """,
                (bank_row_id, bank_start, bank_start),
            )
            raw_settings = (
                bank_row.get("settings_payload")
                if isinstance(bank_row, dict) and isinstance(bank_row.get("settings_payload"), dict)
                else {}
            )
            settings = AppSettingsService.normalize_settings_payload(raw_settings)
            normalized_bank_rows = [dict(bank_row)] if isinstance(bank_row, dict) else []
            categories_by_row_id = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(
                transaction,
                settings=settings,
                transaction_ids=[bank_row_id] if normalized_bank_rows else [],
            )
            normalized_bank_rows = self._annotated_bank_rows(
                normalized_bank_rows,
                categories_by_row_id=categories_by_row_id,
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
                "bank_rows": normalized_bank_rows,
                "oa_rows": oa_rows,
                "invoice_rows": invoice_rows,
                "tag_selection_version": int(settings.get("batch_accounting_tag_selection", {}).get("version") or 1),
                "selected_tag_codes": list(
                    settings.get("batch_accounting_tag_selection", {}).get("selected_tag_codes") or []
                ),
            }

    def tag_rules_snapshot(self) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            source = (
                transaction.fetch_one("select settings_payload from app.app_settings where settings_key='app_settings'")
                or {}
            )
            settings = AppSettingsService.normalize_settings_payload(source.get("settings_payload") or {})
            candidates, params = self._candidate_cte(None)
            classifier, classifier_params = bank_category_classification_cte(
                definitions=settings["bank_transaction_tags"]["definitions"],
                date_from=None,
                date_to=None,
                candidate_transaction_relation="batch_bank_candidates",
                defer_full_payload=True,
            )
            rows = transaction.fetch_all(
                f"""with {candidates}, {classifier}
                select distinct c.effective_category_code as code from classified_with_semantics c
                join batch_bank_candidates candidate on candidate.row_id=c.row_id
                where c.effective_category_code is not null and c.effective_category_code<>''
                order by code""",
                (*params, *classifier_params),
            )
            return {"observed_tag_codes": [row["code"] for row in rows]}

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _annotated_bank_rows(
        rows: list[dict[str, Any]],
        *,
        categories_by_row_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            row_id = str(row.get("id") or "").strip()
            category = categories_by_row_id.get(row_id) or {}
            result.append(
                {
                    **dict(row),
                    "tag_code": str(category.get("effective_category_code") or ""),
                    "tag_label": str(category.get("effective_category_label") or ""),
                    "tag_primary_label": str(category.get("effective_category_primary_label") or ""),
                    "tag_sub_label": str(category.get("effective_category_sub_label") or ""),
                    "tag_source": str(category.get("effective_category_source") or ""),
                }
            )
        return result

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
    def _submitted_relations_sql() -> str:
        return """
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
                    'bank_year', bank.bank_year,
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
                    source.account_no,
                    to_char(coalesce(source.txn_date, source.trade_time::date, source.pay_receive_time::date), 'YYYY') as bank_year
                from app.bank_transactions source
                where coalesce(source.legacy_mongo_id, source.id::text) = any(relation.row_ids)
                  and source.status <> 'deleted'
                  and (%s::date is null or (coalesce(source.txn_date, source.trade_time::date, source.pay_receive_time::date)
                        >= %s::date
                  and coalesce(source.txn_date, source.trade_time::date, source.pay_receive_time::date)
                        < (%s::date + interval '1 year')))
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
        """

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
