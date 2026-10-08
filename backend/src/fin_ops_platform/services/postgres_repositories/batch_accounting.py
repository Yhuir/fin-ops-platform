from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.services.postgres_repositories.canonical_etc_summary_sql import CANONICAL_ETC_BATCH_CANDIDATES_SQL
from fin_ops_platform.services.workbench_canonical_rows import WorkbenchCanonicalRowsBuilder
from fin_ops_platform.services.workbench_row_identity import canonical_workbench_row_type


_HISTORY_CTE = """
    active_relations as materialized (
        select case_id,row_ids,row_types,note,updated_at
        from app.workbench_pair_relations
        where status='active' and relation_mode='batch_accounting'
    ), bank_members as materialized (
        select r.case_id, member.row_id, bank.parent_bank_transaction_id,
            coalesce(bank.txn_date,bank.trade_time::date,bank.pay_receive_time::date) as bank_date,
            bank.signed_amount,
            bank.counterparty_name_raw as counterparty_name,
            coalesce(nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name',''),
                bank.raw_payload->'normalized_payload'->>'bank_name','') as bank_name,
            coalesce(nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_last4',''),
                nullif(bank.raw_payload->'normalized_payload'->>'account_last4',''),
                right(bank.account_no,4)) as account_last4
        from active_relations r
        cross join lateral (select distinct row_id from unnest(r.row_ids,r.row_types) m(row_id,row_type)
            where lower(btrim(row_type)) in ('bank','bank_transaction')) member
        left join app.bank_transaction_units bank
            on coalesce(bank.legacy_mongo_id,bank.id::text)=member.row_id and bank.status <> 'deleted'
    ), filtered as materialized (
        select r.* from active_relations r
        where %s::date is null or exists (
            select 1 from bank_members b where b.case_id=r.case_id
            and b.bank_date >= %s::date and b.bank_date < %s::date + interval '1 year'
        )
    )
"""


class PostgresBatchAccountingQueryRepository:
    """Read-only history from canonical relation facts in one request snapshot."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Batch accounting query repository requires a PostgreSQL connection.")
        self._connection = connection

    def list_snapshot(self, *, bank_year: str | None, page: int, page_size: int) -> dict[str, Any]:
        start = f"{bank_year}-01-01" if bank_year else None
        with self._snapshot_transaction() as transaction:
            return transaction.fetch_one(
                f"""with {_HISTORY_CTE}, page_relations as (
                    select r.*, (select max(bank_date) from bank_members b where b.case_id=r.case_id) as trade_date
                    from filtered r order by trade_date desc nulls last,r.case_id limit %s offset %s
                ), page_rows as (
                    select r.case_id as relation_id,r.trade_date::text as trade_time,
                        (select jsonb_agg(account order by account->>'bank_name',account->>'account_last4')
                            from (select distinct jsonb_build_object('bank_name',bank_name,
                                'account_last4',account_last4) as account
                                from bank_members b where b.case_id=r.case_id) accounts) as bank_accounts,
                        (select array_agg(distinct counterparty_name order by counterparty_name)
                            filter(where counterparty_name <> '') from bank_members b where b.case_id=r.case_id) as counterparty_names,
                        (select case when count(*)=count(signed_amount) then -sum(signed_amount) else null end
                            from bank_members b where b.case_id=r.case_id) as bank_amount,
                        (select count(distinct parent_bank_transaction_id) from bank_members b where b.case_id=r.case_id) as bank_count,
                        (select count(distinct row_id) from unnest(r.row_ids,r.row_types) m(row_id,row_type)
                            where lower(btrim(row_type)) in ('oa','oa_application')) as oa_count
                    from page_relations r
                ) select
                    (select count(*) from filtered) as relation_count,
                    (select count(distinct b.parent_bank_transaction_id) from bank_members b
                        join filtered r using(case_id)) as transaction_count,
                    coalesce((select jsonb_agg(to_jsonb(p) order by trade_time desc nulls last,relation_id)
                        from page_rows p),'[]'::jsonb) as rows,
                    coalesce((select array_agg(distinct to_char(bank_date,'YYYY') order by to_char(bank_date,'YYYY') desc)
                        filter(where bank_date is not null) from bank_members),array[]::text[]) as available_years
                """,
                (start, start, start, page_size, (page - 1) * page_size),
            )

    def detail_snapshot(self, relation_id: str) -> dict[str, Any] | None:
        with self._snapshot_transaction() as transaction:
            relation = transaction.fetch_one(
                """select case_id,row_ids,row_types,note from app.workbench_pair_relations
                where case_id=%s and status='active' and relation_mode='batch_accounting'""",
                (relation_id,),
            )
            if relation is None:
                return None
            members = self._relation_member_rows(transaction, row_ids=relation["row_ids"])
            summary_ids = {
                row_id
                for row_id, row_type in zip(relation["row_ids"], relation["row_types"])
                if canonical_workbench_row_type(row_type) == "invoice" and row_id.startswith("etc-summary-")
            }
            if summary_ids:
                members.extend(self._etc_summary_members(transaction, summary_ids))
            return {"relation": relation, "member_rows": members}

    @staticmethod
    def _etc_summary_members(transaction: Any, summary_ids: set[str]) -> list[dict[str, Any]]:
        # Resolve the exact stored member against canonical batch identities, never
        # reconstruct an external identity by stripping the sanitized row prefix.
        identities = transaction.fetch_all(
            f"""with batch_candidates as ({CANONICAL_ETC_BATCH_CANDIDATES_SQL})
            select distinct external_batch_id,
                'etc-summary-' || regexp_replace(external_batch_id,'[^A-Za-z0-9_-]+','-','g') as row_id
            from batch_candidates
            where 'etc-summary-' || regexp_replace(external_batch_id,'[^A-Za-z0-9_-]+','-','g') = any(%s::text[])
            """,
            (sorted(summary_ids),),
        )
        by_member: dict[str, list[str]] = {}
        for identity in identities:
            by_member.setdefault(identity["row_id"], []).append(identity["external_batch_id"])
        # Sanitized-ID collisions are unresolved rather than choosing one batch.
        resolved = {row_id: values[0] for row_id, values in by_member.items() if len(values) == 1}
        if not resolved:
            return []
        facts = WorkbenchCanonicalRowsBuilder(connection=transaction).load_page_etc_invoice_facts(
            set(resolved.values())
        )
        by_batch: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            by_batch.setdefault(fact["external_batch_id"], []).append(fact)
        members = []
        for row_id, external_id in resolved.items():
            invoices = by_batch.get(external_id)
            if not invoices:
                continue
            dates = sorted(
                {str(invoice["invoice_date"]) for invoice in invoices if invoice["invoice_date"] is not None}
            )
            payload = {
                "id": row_id,
                "invoice_no": f"ETC发票 {len(invoices)} 张",
                "invoice_code": external_id,
                "digital_invoice_no": None,
                "seller_name": None,
                "buyer_name": None,
                "issue_date": " 至 ".join(dict.fromkeys((dates[0], dates[-1]))) if dates else None,
                **{
                    field: sum(invoice[field] for invoice in invoices)
                    if all(invoice[field] is not None for invoice in invoices)
                    else None
                    for field in ("amount", "total_with_tax")
                },
                "etc_invoice_detail_rows": [
                    {
                        "id": invoice["row_id"],
                        "issue_date": str(invoice["invoice_date"]) if invoice["invoice_date"] else None,
                        **{
                            field: invoice[field]
                            for field in (
                                "invoice_no",
                                "invoice_code",
                                "digital_invoice_no",
                                "seller_name",
                                "buyer_name",
                                "amount",
                                "total_with_tax",
                            )
                        },
                    }
                    for invoice in invoices
                ],
            }
            members.append({"member_type": "invoice", "id": row_id, "payload": payload})

        return members

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _relation_member_rows(transaction: Any, *, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids = PostgresBatchAccountingQueryRepository._dedupe(row_ids)
        if not normalized_ids:
            return []
        return transaction.fetch_all(
            """
            select 'bank'::text as member_type, coalesce(bank.legacy_mongo_id, bank.id::text) as id,
                   jsonb_build_object(
                       'id', coalesce(bank.legacy_mongo_id, bank.id::text),
                       'trade_time', coalesce(bank.txn_date::text, bank.trade_time::text, bank.pay_receive_time::text),
                       'counterparty_name', bank.counterparty_name_raw,
                       'bank_name', coalesce(nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_name',''),
                           bank.raw_payload->'normalized_payload'->>'bank_name',''),
                       'account_last4', coalesce(nullif(bank.raw_payload->'normalized_payload'->>'imported_bank_last4',''),
                           nullif(bank.raw_payload->'normalized_payload'->>'account_last4',''),right(bank.account_no,4)),
                       'amount', -bank.signed_amount,
                       'signed_amount', bank.signed_amount,
                       'direction', bank.txn_direction
                   ) as payload
            from app.bank_transaction_units bank
            where coalesce(bank.legacy_mongo_id,bank.id::text)=any(%s::text[]) and bank.status <> 'deleted'
            union all
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
                       'total_with_tax', invoice.total_with_tax
                   ) as payload
            from app.invoices invoice
            where coalesce(invoice.legacy_mongo_id, invoice.id::text) = any(%s::text[])
              and invoice.status <> 'deleted'
            order by member_type, id
            """,
            (normalized_ids, normalized_ids, normalized_ids),
        )
