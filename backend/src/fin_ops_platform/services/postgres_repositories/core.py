from __future__ import annotations

from dataclasses import is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from types import SimpleNamespace
from typing import Any

from fin_ops_platform.domain.enums import BatchStatus, BatchType, ImportDecision, InvoiceStatus, InvoiceType, TransactionDirection, TransactionStatus
from fin_ops_platform.domain.models import BankTransaction, Counterparty, ImportedBatch, ImportedBatchRowResult, Invoice
from fin_ops_platform.services.import_file_service import FileImportPreviewItem, FileImportSession
from fin_ops_platform.services.import_preview_audit import ImportPreviewAuditCounts, ImportPreviewDuplicateGroup
from fin_ops_platform.services.imports import ImportPreview
from fin_ops_platform.services.postgres_repositories.common import jsonb as _jsonb


class PostgresCoreRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Invoice], int]:
        limit, offset = self._page_bounds(page, page_size)
        where_sql, params = self._invoice_filter_sql(
            month=month,
            invoice_type=invoice_type,
            status=status,
            keyword=keyword,
        )
        total_row = self._connection.fetch_one(
            f"select count(*)::bigint as total from app.invoices {where_sql}",
            params,
        )
        rows = self._connection.fetch_all(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
                   data_fingerprint, invoice_date, counterparty_id, counterparty_name, seller_name,
                   seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount, written_off_amount,
                   tax_rate, tax_amount, total_with_tax, currency, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status, tags, source_links, raw_payload
            from app.invoices
            {where_sql}
            order by created_at desc, legacy_id desc
            limit %s offset %s
            """,
            (*params, limit, offset),
        )
        return [self._invoice_from_row(row) for row in rows], self._int((total_row or {}).get("total"), 0)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        account_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[BankTransaction], int]:
        limit, offset = self._page_bounds(page, page_size)
        where_sql, params = self._bank_transaction_filter_sql(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
        )
        total_row = self._connection.fetch_one(
            f"select count(*)::bigint as total from app.bank_transactions {where_sql}",
            params,
        )
        rows = self._connection.fetch_all(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            {where_sql}
            order by coalesce(trade_time, txn_date::timestamptz) desc, legacy_id desc
            limit %s offset %s
            """,
            (*params, limit, offset),
        )
        return [self._transaction_from_row(row) for row in rows], self._int((total_row or {}).get("total"), 0)

    def list_bank_transactions_auto_category_context(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[BankTransaction]:
        where_sql, params = self._bank_transaction_filter_sql(
            account_key=None,
            date_from=date_from,
            date_to=date_to,
            keyword=None,
        )
        rows = self._connection.fetch_all(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            {where_sql}
            order by coalesce(trade_time, txn_date::timestamptz) desc, legacy_id desc
            """,
            params,
        )
        return [self._transaction_from_row(row) for row in rows]

    def list_bank_transaction_accounts(self, *, date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
        filter_clauses: list[str] = []
        params: list[Any] = []
        if text := self._text(date_from):
            filter_clauses.append("txn_date >= %s::date")
            params.append(text[:10])
        if text := self._text(date_to):
            filter_clauses.append("txn_date <= %s::date")
            params.append(text[:10])
        filtered_where = "where " + " and ".join(filter_clauses) if filter_clauses else ""
        rows = self._connection.fetch_all(
            f"""
            with normalized as (
                select
                    coalesce(
                        nullif(raw_payload->'normalized_payload'->>'imported_bank_name', ''),
                        nullif(raw_payload->'normalized_payload'->>'bank_name', ''),
                        '未知银行'
                    ) as bank_name,
                    coalesce(
                        nullif(right(coalesce(
                            nullif(raw_payload->'normalized_payload'->>'imported_bank_last4', ''),
                            nullif(raw_payload->'normalized_payload'->>'account_last4', ''),
                            account_no,
                            ''
                        ), 4), ''),
                        'unknown'
                    ) as account_last4,
                    account_no,
                    balance,
                    txn_date,
                    trade_time,
                    coalesce(trade_time, txn_date::timestamptz) as sort_time
                from app.bank_transactions
            ),
            accounts as (
                select bank_name, account_last4, count(*)::bigint as total_count
                from normalized
                group by bank_name, account_last4
            ),
            filtered_counts as (
                select bank_name, account_last4, count(*)::bigint as transaction_count
                from normalized
                {filtered_where}
                group by bank_name, account_last4
            ),
            latest_balances as (
                select distinct on (bank_name, account_last4)
                    bank_name,
                    account_last4,
                    balance,
                    coalesce(trade_time::text, txn_date::text) as latest_balance_at
                from normalized
                where balance is not null
                order by bank_name, account_last4, sort_time desc nulls last
            )
            select
                accounts.bank_name,
                accounts.account_last4,
                coalesce(filtered_counts.transaction_count, 0)::bigint as transaction_count,
                latest_balances.balance,
                latest_balances.latest_balance_at
            from accounts
            left join filtered_counts
              on filtered_counts.bank_name = accounts.bank_name
             and filtered_counts.account_last4 = accounts.account_last4
            left join latest_balances
              on latest_balances.bank_name = accounts.bank_name
             and latest_balances.account_last4 = accounts.account_last4
            order by accounts.bank_name, accounts.account_last4
            """,
            tuple(params),
        )
        return [
            {
                "bank_name": self._text(row.get("bank_name")) or "未知银行",
                "account_last4": self._text(row.get("account_last4")) or "unknown",
                "transaction_count": self._int(row.get("transaction_count"), 0),
                "latest_balance": self._decimal_or_none(row.get("balance")),
                "latest_balance_at": self._date_text(row.get("latest_balance_at")),
            }
            for row in rows
        ]

    def list_import_batches_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        batch_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[ImportedBatch], int]:
        limit, offset = self._page_bounds(page, page_size)
        clauses: list[str] = []
        params: list[Any] = []
        if text := self._text(batch_type):
            clauses.append("batch_type = %s")
            params.append(text)
        if text := self._text(status):
            clauses.append("status = %s")
            params.append(text)
        where_sql = "where " + " and ".join(clauses) if clauses else ""
        total_row = self._connection.fetch_one(
            f"select count(*)::bigint as total from app.import_batches {where_sql}",
            tuple(params),
        )
        rows = self._connection.fetch_all(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   batch_type, source_name, imported_by, row_count, success_count,
                   error_count, duplicate_count, suspected_duplicate_count, updated_count,
                   status, imported_at, raw_payload
            from app.import_batches
            {where_sql}
            order by imported_at desc, legacy_id desc
            limit %s offset %s
            """,
            (*params, limit, offset),
        )
        return [self._batch_from_row(row) for row in rows], self._int((total_row or {}).get("total"), 0)

    def list_import_files_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        session_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        limit, offset = self._page_bounds(page, page_size)
        clauses: list[str] = []
        params: list[Any] = []
        if text := self._text(session_id):
            clauses.append("import_files.session_id = %s")
            params.append(text)
        if text := self._text(status):
            clauses.append("import_files.status = %s")
            params.append(text)
        else:
            clauses.append("import_files.status <> 'deleted'")
        where_sql = "where " + " and ".join(clauses) if clauses else ""
        count_clauses = [*clauses, "import_files.uploaded_at is not null"]
        count_where_sql = "where " + " and ".join(count_clauses)
        total_row = self._connection.fetch_one(
            f"select count(*)::bigint as total from app.import_files import_files {count_where_sql}",
            tuple(params),
        )
        rows = self._connection.fetch_all(
            f"""
            select coalesce(import_files.legacy_mongo_id, import_files.id::text) as legacy_id,
                   import_files.session_id, import_files.stored_file_path,
                   import_files.original_filename, import_files.template_kind, import_files.status,
                   import_files.uploaded_by, import_files.uploaded_at,
                   payload.data->>'batch_type' as payload_batch_type,
                   payload.data->>'override_batch_type' as payload_override_batch_type,
                   payload.data->>'message' as payload_message,
                   payload.data->>'row_count' as payload_row_count,
                   payload.data->>'success_count' as payload_success_count,
                   payload.data->>'error_count' as payload_error_count,
                   payload.data->>'duplicate_count' as payload_duplicate_count,
                   payload.data->>'suspected_duplicate_count' as payload_suspected_duplicate_count,
                   payload.data->>'updated_count' as payload_updated_count,
                   payload.data->>'preview_batch_id' as payload_preview_batch_id,
                   payload.data->>'batch_id' as payload_batch_id,
                   payload.data->'audit' as payload_audit
            from app.import_files import_files
            cross join lateral (
                select coalesce(import_files.raw_payload->'normalized_payload', import_files.raw_payload, '{{}}'::jsonb) as data
            ) payload
            {where_sql}
            order by import_files.uploaded_at desc, legacy_id desc
            limit %s offset %s
            """,
            (*params, limit, offset),
        )
        files: list[dict[str, Any]] = []
        for row in rows:
            files.append(self._file_summary_item_from_row(row))
        return files, self._int((total_row or {}).get("total"), 0)

    def find_invoice_identity(
        self,
        *,
        source_unique_key: str | None = None,
        data_fingerprint: str | None = None,
    ) -> Invoice | None:
        return self.find_invoice_by_identity(canonical_key=source_unique_key, suspected_key=data_fingerprint)

    def find_invoices_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[Invoice]:
        source_unique_key = canonical_key
        data_fingerprint = suspected_key
        if source_unique_key:
            return self._fetch_invoices_by_clause(
                "(source_unique_key = %s or digital_invoice_no = %s)",
                (source_unique_key, source_unique_key),
            )
        if data_fingerprint:
            return self._fetch_invoices_by_clause("data_fingerprint = %s", (data_fingerprint,))
        return []

    def find_invoices_by_identity_keys(
        self,
        *,
        canonical_keys: list[str] | tuple[str, ...] | set[str] | None = None,
        suspected_keys: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> list[Invoice]:
        normalized_canonical_keys = self._unique_texts(canonical_keys or [])
        normalized_suspected_keys = self._unique_texts(suspected_keys or [])
        clauses: list[str] = []
        params: list[Any] = []
        if normalized_canonical_keys:
            clauses.append("(source_unique_key = any(%s::text[]) or digital_invoice_no = any(%s::text[]))")
            params.extend([normalized_canonical_keys, normalized_canonical_keys])
        if normalized_suspected_keys:
            clauses.append("data_fingerprint = any(%s::text[])")
            params.append(normalized_suspected_keys)
        if not clauses:
            return []
        return self._fetch_invoices_by_clause(" or ".join(clauses), tuple(params))

    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        source_unique_key = canonical_key
        data_fingerprint = suspected_key
        if source_unique_key:
            return self._fetch_invoice_by_clause(
                "(source_unique_key = %s or digital_invoice_no = %s)",
                (source_unique_key, source_unique_key),
            )
        if data_fingerprint:
            return self._fetch_invoice_by_clause("data_fingerprint = %s", (data_fingerprint,))
        return None

    def find_transaction_identity(self, *, source_unique_key: str) -> BankTransaction | None:
        return self.find_bank_transaction_by_identity(canonical_key=source_unique_key)

    def find_bank_transaction_by_identity(self, *, canonical_key: str | None = None) -> BankTransaction | None:
        source_unique_key = canonical_key
        if not source_unique_key:
            return None
        row = self._connection.fetch_one(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            where source_unique_key = %s
            limit 1
            """,
            (source_unique_key,),
        )
        return self._transaction_from_row(row) if row else None

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        normalized_key = self._text(canonical_key)
        if not normalized_key:
            return False
        row = self._connection.fetch_one(
            """
            select 1 as exists
            from app.invoices
            where source_unique_key = %s or digital_invoice_no = %s
            limit 1
            """,
            (normalized_key, normalized_key),
        )
        return bool(row)

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        normalized_invoice_id = self._text(invoice_id)
        if not normalized_invoice_id:
            return None
        return self._fetch_invoice_by_clause(
            "legacy_mongo_id = %s or id::text = %s",
            (normalized_invoice_id, normalized_invoice_id),
        )

    def list_invoices_by_ids(self, invoice_ids: list[str]) -> list[Invoice]:
        normalized_ids = self._unique_texts(invoice_ids)
        if not normalized_ids:
            return []
        return self._fetch_invoices_by_clause(
            "legacy_mongo_id = any(%s::text[]) or id::text = any(%s::text[])",
            (normalized_ids, normalized_ids),
        )

    def list_submitted_etc_invoices(self) -> list[Invoice]:
        rows = self._connection.fetch_all(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
                   data_fingerprint, invoice_date, counterparty_id, counterparty_name, seller_name,
                   seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount, written_off_amount,
                   tax_rate, tax_amount, total_with_tax, currency, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status, tags, source_links, raw_payload
            from app.invoices
            where workbench_visibility = 'hidden_after_etc_submission'
               or raw_payload->'normalized_payload'->>'workbench_visibility' = 'hidden_after_etc_submission'
               or raw_payload->'normalized_payload'->>'etc_submission_status' = 'submitted'
            order by invoice_date, legacy_id
            """
        )
        return [self._invoice_from_row(row) for row in rows]

    def find_submitted_etc_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
        invoice_no: str | None = None,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
    ) -> object | None:
        candidates = [
            self._text(digital_invoice_no),
            self._text(invoice_no),
            self._text(canonical_key),
        ]
        invoice_numbers = [value for value in candidates if value and "|" not in value and ":" not in value]
        normalized_invoice_code = self._text(invoice_code)
        normalized_invoice_no = self._text(invoice_no)
        if not invoice_numbers and not (normalized_invoice_code and normalized_invoice_no):
            return None
        row = self._connection.fetch_one(
            """
            select
                etc_invoices.etc_invoice_id,
                etc_invoices.invoice_no,
                etc_invoices.invoice_code,
                etc_invoices.invoice_date::text,
                etc_invoices.seller_name,
                nullif(etc_invoices.raw_payload->'normalized_payload'->>'seller_tax_no', '') as seller_tax_no,
                etc_invoices.buyer_name,
                nullif(etc_invoices.raw_payload->'normalized_payload'->>'buyer_tax_no', '') as buyer_tax_no,
                etc_invoices.amount,
                etc_invoices.tax_amount,
                etc_invoices.total_with_tax,
                nullif(etc_invoices.raw_payload->'normalized_payload'->>'tax_rate', '') as tax_rate,
                etc_invoices.batch_id,
                etc_invoices.business_batch_id,
                etc_invoices.status,
                etc_business_batches.status as business_batch_status
            from app.etc_invoices etc_invoices
            left join app.etc_business_batches etc_business_batches
              on etc_business_batches.business_batch_id = etc_invoices.business_batch_id
            where (
                    etc_invoices.invoice_no = any(%s::text[])
                 or (
                        %s::text is not null
                    and %s::text is not null
                    and etc_invoices.invoice_code = %s::text
                    and etc_invoices.invoice_no = %s::text
                 )
            )
              and (
                    etc_business_batches.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                 or (
                        etc_invoices.status = 'submitted'
                    and coalesce(etc_business_batches.status, '') <> 'deleted'
                 )
              )
            order by etc_invoices.updated_at desc, etc_invoices.created_at desc
            limit 1
            """,
            (
                invoice_numbers,
                normalized_invoice_code,
                normalized_invoice_no,
                normalized_invoice_code,
                normalized_invoice_no,
            ),
        )
        if not row:
            return None
        return SimpleNamespace(
            id=self._text(row.get("etc_invoice_id")),
            invoice_number=self._text(row.get("invoice_no")),
            issue_date=self._date_text(row.get("invoice_date")),
            passage_start_date=None,
            passage_end_date=None,
            plate_number=None,
            vehicle_type=None,
            seller_name=self._text(row.get("seller_name")),
            seller_tax_no=self._text(row.get("seller_tax_no")),
            buyer_name=self._text(row.get("buyer_name")),
            buyer_tax_no=self._text(row.get("buyer_tax_no")),
            amount_without_tax=row.get("amount"),
            tax_amount=row.get("tax_amount"),
            total_amount=row.get("total_with_tax"),
            tax_rate=self._text(row.get("tax_rate")),
            import_batch_id=self._text(row.get("batch_id")),
            business_batch_id=self._text(row.get("business_batch_id")),
            current_batch_id=self._text(row.get("business_batch_id")),
            last_batch_id=self._text(row.get("business_batch_id")),
            status=self._text(row.get("status")),
        )

    def upsert_etc_batch_invoice_link(
        self,
        *,
        invoice_id: str,
        business_batch_id: str,
        etc_invoice_id: str | None = None,
        invoice_no: str | None = None,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
        invoice_date: str | None = None,
        link_source: str = "formal_invoice_import",
        confidence: str = "strict",
        raw_payload: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_invoice_id = self._text(invoice_id)
        normalized_business_batch_id = self._text(business_batch_id)
        identity_key = self._etc_batch_invoice_identity_key(
            invoice_no=invoice_no,
            invoice_code=invoice_code,
            digital_invoice_no=digital_invoice_no,
        )
        if not normalized_invoice_id:
            raise ValueError("invoice_id is required for ETC batch invoice link")
        if not normalized_business_batch_id:
            raise ValueError("business_batch_id is required for ETC batch invoice link")
        if not identity_key:
            raise ValueError("invoice identity is required for ETC batch invoice link")
        row = self._connection.fetch_one(
            """
            with resolved_invoice as (
                select id
                from app.invoices
                where legacy_mongo_id = %s or id::text = %s
                limit 1
            ),
            upserted as (
                insert into app.etc_batch_invoice_links(
                    tenant_id, business_batch_id, etc_invoice_id, invoice_id,
                    identity_key, invoice_no, invoice_code, digital_invoice_no, invoice_date,
                    link_status, link_source, confidence, raw_payload
                )
                select
                    %s, %s, %s, resolved_invoice.id,
                    %s, %s, %s, %s, %s::date,
                    'active', %s, %s, %s
                from resolved_invoice
                on conflict (tenant_id, business_batch_id, identity_key) where link_status = 'active'
                do update set
                    invoice_id = excluded.invoice_id,
                    etc_invoice_id = coalesce(excluded.etc_invoice_id, app.etc_batch_invoice_links.etc_invoice_id),
                    invoice_no = excluded.invoice_no,
                    invoice_code = excluded.invoice_code,
                    digital_invoice_no = excluded.digital_invoice_no,
                    invoice_date = excluded.invoice_date,
                    link_source = excluded.link_source,
                    confidence = excluded.confidence,
                    raw_payload = coalesce(app.etc_batch_invoice_links.raw_payload, '{}'::jsonb)
                        || coalesce(excluded.raw_payload, '{}'::jsonb),
                    updated_at = now()
                returning
                    id::text,
                    tenant_id,
                    business_batch_id,
                    etc_invoice_id,
                    invoice_id::text,
                    identity_key,
                    invoice_no,
                    invoice_code,
                    digital_invoice_no,
                    invoice_date::text,
                    link_status,
                    link_source,
                    confidence,
                    raw_payload
            )
            select * from upserted
            """,
            (
                normalized_invoice_id,
                normalized_invoice_id,
                self._text(tenant_id) or "default",
                normalized_business_batch_id,
                self._text(etc_invoice_id),
                identity_key,
                self._text(invoice_no),
                self._text(invoice_code),
                self._text(digital_invoice_no),
                self._date_text(invoice_date),
                self._text(link_source) or "formal_invoice_import",
                self._text(confidence) or "strict",
                _jsonb(raw_payload or {}),
            ),
        )
        return dict(row) if row else None

    @classmethod
    def _etc_batch_invoice_identity_key(
        cls,
        *,
        invoice_no: str | None = None,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
    ) -> str | None:
        digital = cls._text(digital_invoice_no)
        if digital:
            return digital
        code = cls._text(invoice_code)
        number = cls._text(invoice_no)
        if code and number:
            return f"{code}:{number}"
        return number

    def get_transaction(self, transaction_id: str) -> BankTransaction | None:
        normalized_transaction_id = self._text(transaction_id)
        if not normalized_transaction_id:
            return None
        row = self._connection.fetch_one(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            where legacy_mongo_id = %s or id::text = %s
            limit 1
            """,
            (normalized_transaction_id, normalized_transaction_id),
        )
        return self._transaction_from_row(row) if row else None

    def list_bank_transactions_by_ids(self, transaction_ids: list[str]) -> list[BankTransaction]:
        normalized_ids = self._unique_texts(transaction_ids)
        if not normalized_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            where legacy_mongo_id = any(%s::text[]) or id::text = any(%s::text[])
            order by created_at, id
            """,
            (normalized_ids, normalized_ids),
        )
        return [self._transaction_from_row(row) for row in rows if isinstance(row, dict)]

    def load_imports(self) -> dict[str, Any]:
        batches = self._connection.fetch_all(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   batch_type, source_name, imported_by, row_count, success_count,
                   error_count, duplicate_count, suspected_duplicate_count, updated_count,
                   status, imported_at, raw_payload
            from app.import_batches
            order by imported_at, legacy_id
            """
        )
        invoices = self._connection.fetch_all(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
                   data_fingerprint, invoice_date, counterparty_id, counterparty_name, seller_name,
                   seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount, written_off_amount,
                   tax_rate, tax_amount, total_with_tax, currency, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status, tags, source_links, raw_payload
            from app.invoices
            order by created_at, legacy_id
            """
        )
        transactions = self._connection.fetch_all(
            """
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   account_no, account_name, txn_direction, counterparty_name_raw,
                   normalized_counterparty_name, amount, signed_amount, written_off_amount,
                   txn_date, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                   data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                   currency, summary, remark, bank_text_fields, status, raw_payload
            from app.bank_transactions
            order by created_at, legacy_id
            """
        )
        if not batches and not invoices and not transactions:
            return {}
        batch_rows = self._connection.fetch_all(
            """
            select rows.id::text as postgres_id, coalesce(rows.legacy_mongo_id, rows.id::text) as legacy_id,
                   rows.legacy_batch_id, coalesce(batches.legacy_mongo_id, batches.id::text) as joined_batch_id,
                   rows.row_no, rows.source_record_type, rows.source_unique_key, rows.data_fingerprint,
                   rows.decision, rows.decision_reason, rows.linked_object_type, rows.linked_object_id,
                   rows.identity_kind, rows.account_no, rows.trade_time, rows.direction, rows.amount,
                   rows.counterparty_name, rows.raw_payload
            from app.import_batch_rows rows
            left join app.import_batches batches on batches.id = rows.import_batch_id
            order by coalesce(rows.legacy_batch_id, batches.legacy_mongo_id, batches.id::text), rows.row_no
            """
        )
        row_results_by_batch: dict[str, list[ImportedBatchRowResult]] = {}
        normalized_rows_by_batch: dict[str, list[dict[str, Any]]] = {}
        for row in batch_rows:
            row_result = self._batch_row_from_row(row)
            batch_id = row_result.batch_id
            row_results_by_batch.setdefault(batch_id, []).append(row_result)
            row_payload = self._row_payload(row)
            normalized_row = row_payload.get("normalized_row") if isinstance(row_payload, dict) else None
            normalized_rows_by_batch.setdefault(batch_id, []).append(dict(normalized_row if isinstance(normalized_row, dict) else {}))

        preview_map: dict[str, ImportPreview] = {}
        for row in batches:
            batch = self._batch_from_row(row)
            preview_map[batch.id] = ImportPreview(
                batch=batch,
                row_results=row_results_by_batch.get(batch.id, []),
                normalized_rows=normalized_rows_by_batch.get(batch.id, []),
            )
        invoice_objects = [self._invoice_from_row(row) for row in invoices]
        transaction_objects = [self._transaction_from_row(row) for row in transactions]
        return {
            "batch_counter": self._max_suffix(preview_map),
            "invoice_counter": len(invoice_objects),
            "txn_counter": len(transaction_objects),
            "counterparty_counter": len({invoice.counterparty.id for invoice in invoice_objects}),
            "batches": preview_map,
            "invoices": invoice_objects,
            "transactions": transaction_objects,
        }

    def save_imports(self, snapshot: dict[str, Any]) -> None:
        if not snapshot:
            return
        connection = self._connection
        transaction_factory = getattr(connection, "transaction", None)
        if callable(transaction_factory):
            with transaction_factory() as tx:
                self._save_imports_with_connection(tx, snapshot)
        else:
            self._save_imports_with_connection(connection, snapshot)

    def save_import_delta(
        self,
        imports_snapshot: dict[str, Any],
        file_imports_snapshot: dict[str, Any],
    ) -> None:
        connection = self._connection
        transaction_factory = getattr(connection, "transaction", None)
        if callable(transaction_factory):
            with transaction_factory() as tx:
                self._save_imports_with_connection(tx, imports_snapshot)
                self._save_file_imports_with_connection(tx, file_imports_snapshot)
        else:
            self._save_imports_with_connection(connection, imports_snapshot)
            self._save_file_imports_with_connection(connection, file_imports_snapshot)

    def save_invoices(self, invoices: list[Any]) -> None:
        serialized_invoices = self._iter_items(invoices)
        if not serialized_invoices:
            return
        snapshot = {"invoices": serialized_invoices}
        connection = self._connection
        transaction_factory = getattr(connection, "transaction", None)
        if callable(transaction_factory):
            with transaction_factory() as tx:
                for invoice in serialized_invoices:
                    self._save_invoice(tx, invoice)
        else:
            for invoice in serialized_invoices:
                self._save_invoice(connection, invoice)

    def save_invoice_etc_metadata(self, invoices: list[Any]) -> None:
        serialized_invoices = self._iter_items(invoices)
        if not serialized_invoices:
            return
        connection = self._connection
        transaction_factory = getattr(connection, "transaction", None)
        if callable(transaction_factory):
            with transaction_factory() as tx:
                for invoice in serialized_invoices:
                    self._update_invoice_etc_metadata(tx, invoice)
        else:
            for invoice in serialized_invoices:
                self._update_invoice_etc_metadata(connection, invoice)

    def repair_imported_invoice_totals(self, connection: Any, updates: list[dict[str, Any]]) -> None:
        for update in updates:
            affected = connection.execute(
                """
                update app.invoices
                set amount = %s,
                    signed_amount = %s,
                    tax_amount = %s,
                    total_with_tax = %s,
                    tax_rate = %s,
                    raw_payload = %s,
                    updated_at = now()
                where coalesce(legacy_mongo_id, id::text) = %s
                  and legacy_source_batch_id = %s
                """,
                (
                    update["amount"],
                    update["signed_amount"],
                    update["tax_amount"],
                    update["total_with_tax"],
                    update["tax_rate"],
                    _jsonb(update["raw_payload"]),
                    update["invoice_id"],
                    update["source_batch_id"],
                ),
            )
            if affected != 1:
                raise RuntimeError(f"Invoice {update['invoice_id']} changed after the repair plan was built.")

    def repair_submitted_etc_invoice_overlap(
        self,
        *,
        invoice_id: str,
        etc_invoice_id: str,
        etc_batch_id: str | None,
        reason: str,
        operator: str,
    ) -> int:
        return int(
            self._connection.execute(
                """
                update app.invoices
                set etc_invoice_id = %s,
                    workbench_visibility = 'hidden_after_etc_submission',
                    tags = case
                        when 'ETC' = any(coalesce(tags, array[]::text[])) then tags
                        else array_append(coalesce(tags, array[]::text[]), 'ETC')
                    end,
                    source_links = coalesce(source_links, '[]'::jsonb) || jsonb_build_array(
                        jsonb_build_object(
                            'source_type', 'etc_invoice_import',
                            'source_id', %s::text,
                            'batch_id', coalesce(%s::text, ''),
                            'created_at', now()::text,
                            'repair_reason', %s::text,
                            'operator', %s::text
                        )
                    ),
                    raw_payload = jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                coalesce(raw_payload, '{}'::jsonb),
                                '{normalized_payload,etc_invoice_id}',
                                to_jsonb(%s::text),
                                true
                            ),
                            '{normalized_payload,etc_submission_status}',
                            to_jsonb('submitted'::text),
                            true
                        ),
                        '{normalized_payload,workbench_visibility}',
                        to_jsonb('hidden_after_etc_submission'::text),
                        true
                    ),
                    updated_at = now()
                where id::text = %s
                  and coalesce(workbench_visibility, 'visible') = 'visible'
                  and nullif(etc_invoice_id, '') is null
                """,
                (
                    self._text(etc_invoice_id),
                    self._text(etc_invoice_id),
                    self._text(etc_batch_id),
                    self._text(reason),
                    self._text(operator),
                    self._text(etc_invoice_id),
                    self._text(invoice_id),
                ),
            )
            or 0
        )

    def load_file_imports(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select coalesce(import_files.legacy_mongo_id, import_files.id::text) as legacy_id,
                   import_files.session_id, import_files.stored_file_path,
                   import_files.original_filename, import_files.template_kind, import_files.status,
                   import_files.uploaded_by, import_files.uploaded_at,
                   import_files.raw_payload
            from app.import_files import_files
            where import_files.status <> 'deleted'
            order by import_files.session_id, import_files.original_filename, legacy_id
            """
        )
        sessions: dict[str, FileImportSession] = {}
        for row in rows:
            payload = self._row_payload(row)
            if not isinstance(payload, dict):
                payload = {}
            session_id = self._text(payload.get("session_id") or row.get("session_id") or "default") or "default"
            session = sessions.setdefault(
                session_id,
                FileImportSession(
                    id=session_id,
                    imported_by=self._text(payload.get("imported_by") or row.get("uploaded_by")) or "postgres",
                    file_count=0,
                    status=self._text(payload.get("session_status")) or "preview_ready",
                    files=[],
                    created_at=self._datetime(payload.get("created_at") or row.get("uploaded_at")),
                ),
            )
            if "session_audit" in payload:
                session.audit = self._audit_counts_from_payload(payload.get("session_audit"))
            if "duplicate_groups" in payload:
                session.duplicate_groups = self._duplicate_groups_from_payload(payload.get("duplicate_groups"))
            item = self._file_item_from_row(row, payload)
            session.files.append(item)
            session.file_count = len(session.files)
            if any(file.status == "confirmed" for file in session.files):
                session.status = "confirmed"
        if not sessions:
            return {}
        return {
            "session_counter": len(sessions),
            "file_counter": sum(len(session.files) for session in sessions.values()),
            "sessions": sessions,
        }

    def save_file_imports(self, snapshot: dict[str, Any]) -> None:
        self._save_file_imports_with_connection(self._connection, snapshot)

    def _save_file_imports_with_connection(self, connection: Any, snapshot: dict[str, Any]) -> None:
        sessions = snapshot.get("sessions") if isinstance(snapshot, dict) else None
        if not isinstance(sessions, dict):
            return
        for session_id, raw_session in sessions.items():
            session_payload = self._serialize(raw_session)
            if not isinstance(session_payload, dict):
                continue
            files = session_payload.get("files")
            if not isinstance(files, list):
                continue
            for raw_file in files:
                if not isinstance(raw_file, dict):
                    continue
                file_id = self._text(raw_file.get("id"))
                if not file_id:
                    continue
                connection.execute(
                    """
                    insert into app.import_files(
                        legacy_mongo_id, session_id, stored_file_path, original_filename,
                        template_kind, status, raw_payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (legacy_mongo_id) do update set
                        session_id = excluded.session_id,
                        stored_file_path = excluded.stored_file_path,
                        original_filename = excluded.original_filename,
                        template_kind = excluded.template_kind,
                        status = excluded.status,
                        raw_payload = excluded.raw_payload
                    """,
                    (
                        file_id,
                        self._text(session_payload.get("id") or session_id),
                        self._text(raw_file.get("stored_file_path")),
                        self._text(raw_file.get("file_name")) or file_id,
                        self._text(raw_file.get("template_code")),
                        self._text(raw_file.get("status")) or "stored",
                        _jsonb(
                            {
                                "normalized_payload": {
                                    **raw_file,
                                    "session_id": self._text(session_payload.get("id") or session_id),
                                    "session_status": self._text(session_payload.get("status")),
                                    "session_audit": session_payload.get("audit"),
                                    "duplicate_groups": session_payload.get("duplicate_groups"),
                                }
                            }
                        ),
                    ),
                )

    def _save_imports_with_connection(self, connection: Any, snapshot: dict[str, Any]) -> None:
        for preview in self._iter_previews(snapshot.get("batches")):
            batch = preview.get("batch") if isinstance(preview.get("batch"), dict) else preview
            if not isinstance(batch, dict):
                continue
            batch_id = self._text(batch.get("id"))
            if not batch_id:
                continue
            connection.execute(
                """
                insert into app.import_batches(
                    legacy_mongo_id, batch_type, source_name, imported_by, row_count,
                    success_count, error_count, duplicate_count, suspected_duplicate_count,
                    updated_count, status, imported_at, raw_payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s)
                on conflict (legacy_mongo_id) do update set
                    batch_type = excluded.batch_type,
                    source_name = excluded.source_name,
                    imported_by = excluded.imported_by,
                    row_count = excluded.row_count,
                    success_count = excluded.success_count,
                    error_count = excluded.error_count,
                    duplicate_count = excluded.duplicate_count,
                    suspected_duplicate_count = excluded.suspected_duplicate_count,
                    updated_count = excluded.updated_count,
                    status = excluded.status,
                    imported_at = excluded.imported_at,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    batch_id,
                    self._text(batch.get("batch_type")) or BatchType.BANK_TRANSACTION.value,
                    self._text(batch.get("source_name")) or "unknown",
                    self._text(batch.get("imported_by")) or "unknown",
                    self._int(batch.get("row_count"), 0),
                    self._int(batch.get("success_count"), 0),
                    self._int(batch.get("error_count"), 0),
                    self._int(batch.get("duplicate_count"), 0),
                    self._int(batch.get("suspected_duplicate_count"), 0),
                    self._int(batch.get("updated_count"), 0),
                    self._text(batch.get("status")) or BatchStatus.PENDING.value,
                    self._text(batch.get("imported_at")),
                    _jsonb({"normalized_payload": batch}),
                ),
            )
            row_results = preview.get("row_results") if isinstance(preview, dict) else None
            normalized_rows = preview.get("normalized_rows") if isinstance(preview, dict) else None
            self._save_batch_rows(connection, batch_id, row_results, normalized_rows)
        for invoice in self._iter_items(snapshot.get("invoices")):
            self._save_invoice(connection, invoice)
        for transaction in self._iter_items(snapshot.get("transactions")):
            self._save_transaction(connection, transaction)

    def _save_batch_rows(self, connection: Any, batch_id: str, row_results: Any, normalized_rows: Any) -> None:
        if not isinstance(row_results, list):
            return
        normalized_list = normalized_rows if isinstance(normalized_rows, list) else []
        insert_sql = """
            insert into app.import_batch_rows(
                legacy_mongo_id, import_batch_id, legacy_batch_id, row_no, source_record_type,
                source_unique_key, data_fingerprint, decision, decision_reason,
                linked_object_type, linked_object_id, identity_kind, account_no, trade_time,
                direction, amount, counterparty_name, raw_payload
            )
            values (
                %s,
                (select id from app.import_batches where legacy_mongo_id = %s or id::text = %s limit 1),
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s, %s, %s, %s
            )
            on conflict (legacy_mongo_id) do update set
                import_batch_id = excluded.import_batch_id,
                legacy_batch_id = excluded.legacy_batch_id,
                row_no = excluded.row_no,
                source_record_type = excluded.source_record_type,
                source_unique_key = excluded.source_unique_key,
                data_fingerprint = excluded.data_fingerprint,
                decision = excluded.decision,
                decision_reason = excluded.decision_reason,
                linked_object_type = excluded.linked_object_type,
                linked_object_id = excluded.linked_object_id,
                identity_kind = excluded.identity_kind,
                account_no = excluded.account_no,
                trade_time = excluded.trade_time,
                direction = excluded.direction,
                amount = excluded.amount,
                counterparty_name = excluded.counterparty_name,
                raw_payload = excluded.raw_payload
            where app.import_batch_rows.legacy_batch_id = excluded.legacy_batch_id
        """
        params_seq: list[tuple[Any, ...]] = []
        for index, row_result in enumerate(row_results):
            payload = self._serialize(row_result)
            if not isinstance(payload, dict):
                continue
            row_id = self._text(payload.get("id"))
            if not row_id:
                continue
            normalized = normalized_list[index] if index < len(normalized_list) and isinstance(normalized_list[index], dict) else {}
            raw_payload = {**payload, "normalized_row": normalized}
            params_seq.append(
                (
                    row_id,
                    batch_id,
                    batch_id,
                    batch_id,
                    self._int(payload.get("row_no"), 0),
                    self._text(payload.get("source_record_type")) or "unknown",
                    self._text(payload.get("source_unique_key")),
                    self._text(payload.get("data_fingerprint")),
                    self._text(payload.get("decision")) or ImportDecision.ERROR.value,
                    self._text(payload.get("decision_reason")) or "",
                    self._text(payload.get("linked_object_type")),
                    self._text(payload.get("linked_object_id")),
                    self._text(payload.get("identity_kind")),
                    self._text(payload.get("account_no")),
                    self._text(payload.get("trade_time")),
                    self._text(payload.get("direction")),
                    self._decimal_text(payload.get("amount")),
                    self._text(payload.get("counterparty_name")),
                    _jsonb({"normalized_payload": raw_payload}),
                )
            )
        if not params_seq:
            return
        execute_many_values = getattr(connection, "execute_many_values", None)
        affected = (
            int(execute_many_values(insert_sql, params_seq) or 0)
            if callable(execute_many_values)
            else sum(int(connection.execute(insert_sql, params) or 0) for params in params_seq)
        )
        if affected != len(params_seq):
            raise RuntimeError(
                "One or more import batch rows are already owned by another batch; refusing to re-parent them."
            )

    def _save_invoice(self, connection: Any, invoice: dict[str, Any]) -> None:
        invoice_id = self._text(invoice.get("id"))
        if not invoice_id:
            return
        source_unique_key, data_fingerprint = self._invoice_identity_values(invoice)
        normalized_payload = self._invoice_payload_with_identity_values(
            invoice,
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
        )
        counterparty = invoice.get("counterparty") if isinstance(invoice.get("counterparty"), dict) else {}
        connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_code, digital_invoice_no,
                source_unique_key, data_fingerprint, invoice_date, invoice_month, counterparty_id,
                counterparty_name, seller_name, seller_tax_no, buyer_name, buyer_tax_no, amount,
                signed_amount, written_off_amount, tax_rate, tax_amount, total_with_tax, currency,
                legacy_source_batch_id, oa_form_id, etc_invoice_id, workbench_visibility, status,
                tags, source_links, raw_payload
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s::date, date_trunc('month', %s::date)::date,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            on conflict (legacy_mongo_id) do update set
                invoice_type = excluded.invoice_type,
                invoice_no = excluded.invoice_no,
                invoice_code = excluded.invoice_code,
                digital_invoice_no = excluded.digital_invoice_no,
                source_unique_key = excluded.source_unique_key,
                data_fingerprint = excluded.data_fingerprint,
                invoice_date = excluded.invoice_date,
                invoice_month = excluded.invoice_month,
                counterparty_id = excluded.counterparty_id,
                counterparty_name = excluded.counterparty_name,
                seller_name = excluded.seller_name,
                seller_tax_no = excluded.seller_tax_no,
                buyer_name = excluded.buyer_name,
                buyer_tax_no = excluded.buyer_tax_no,
                amount = excluded.amount,
                signed_amount = excluded.signed_amount,
                written_off_amount = excluded.written_off_amount,
                tax_rate = excluded.tax_rate,
                tax_amount = excluded.tax_amount,
                total_with_tax = excluded.total_with_tax,
                currency = excluded.currency,
                legacy_source_batch_id = excluded.legacy_source_batch_id,
                oa_form_id = excluded.oa_form_id,
                etc_invoice_id = excluded.etc_invoice_id,
                workbench_visibility = excluded.workbench_visibility,
                status = excluded.status,
                tags = excluded.tags,
                source_links = excluded.source_links,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                invoice_id,
                self._text(invoice.get("invoice_type")) or InvoiceType.INPUT.value,
                self._text(invoice.get("invoice_no")) or invoice_id,
                self._text(invoice.get("invoice_code")),
                self._text(invoice.get("digital_invoice_no")),
                source_unique_key,
                data_fingerprint,
                self._date_text(invoice.get("invoice_date")),
                self._date_text(invoice.get("invoice_date")),
                self._text(counterparty.get("id") or invoice.get("counterparty_id")),
                self._text(counterparty.get("name") or invoice.get("counterparty_name")),
                self._text(invoice.get("seller_name")),
                self._text(invoice.get("seller_tax_no")),
                self._text(invoice.get("buyer_name")),
                self._text(invoice.get("buyer_tax_no")),
                self._decimal_text(invoice.get("amount")) or "0",
                self._decimal_text(invoice.get("signed_amount")) or self._decimal_text(invoice.get("amount")) or "0",
                self._decimal_text(invoice.get("written_off_amount")) or "0",
                self._text(invoice.get("tax_rate")),
                self._decimal_text(invoice.get("tax_amount")),
                self._decimal_text(invoice.get("total_with_tax")),
                self._text(invoice.get("currency")) or "CNY",
                self._text(invoice.get("source_batch_id") or invoice.get("legacy_source_batch_id")),
                self._text(invoice.get("oa_form_id")),
                self._text(invoice.get("etc_invoice_id")),
                self._text(invoice.get("workbench_visibility")) or "visible",
                self._text(invoice.get("status")) or InvoiceStatus.PENDING.value,
                self._text_list(invoice.get("tags")),
                _jsonb(invoice.get("source_links") if isinstance(invoice.get("source_links"), list) else []),
                _jsonb({"normalized_payload": normalized_payload}),
            ),
        )

    def _update_invoice_etc_metadata(self, connection: Any, invoice: dict[str, Any]) -> None:
        invoice_id = self._text(invoice.get("id"))
        if not invoice_id:
            return
        source_unique_key, data_fingerprint = self._invoice_identity_values(invoice)
        normalized_payload = self._invoice_payload_with_identity_values(
            invoice,
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
        )
        connection.execute(
            """
            update app.invoices
            set etc_invoice_id = %s,
                legacy_source_batch_id = coalesce(%s, legacy_source_batch_id),
                workbench_visibility = %s,
                status = %s,
                tags = %s,
                source_links = %s,
                raw_payload = jsonb_set(
                    coalesce(raw_payload, '{}'::jsonb),
                    '{normalized_payload}',
                    %s,
                    true
                ),
                updated_at = now()
            where legacy_mongo_id = %s or id::text = %s
            """,
            (
                self._text(invoice.get("etc_invoice_id")),
                self._text(invoice.get("source_batch_id") or invoice.get("legacy_source_batch_id")),
                self._text(invoice.get("workbench_visibility")) or "visible",
                self._text(invoice.get("status")) or InvoiceStatus.PENDING.value,
                self._text_list(invoice.get("tags")),
                _jsonb(invoice.get("source_links") if isinstance(invoice.get("source_links"), list) else []),
                _jsonb(normalized_payload),
                invoice_id,
                invoice_id,
            ),
        )

    def _invoice_identity_values(self, invoice: dict[str, Any]) -> tuple[str | None, str | None]:
        source_unique_key = self._text(invoice.get("source_unique_key"))
        data_fingerprint = None if source_unique_key else self._text(invoice.get("data_fingerprint"))
        return source_unique_key, data_fingerprint

    def _invoice_payload_with_identity_values(
        self,
        invoice: dict[str, Any],
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> dict[str, Any]:
        payload = dict(invoice)
        payload["source_unique_key"] = source_unique_key
        payload["data_fingerprint"] = data_fingerprint
        return payload

    def _save_transaction(self, connection: Any, transaction: dict[str, Any]) -> None:
        transaction_id = self._text(transaction.get("id"))
        if not transaction_id:
            return
        connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction, counterparty_name_raw,
                normalized_counterparty_name, amount, signed_amount, written_off_amount, txn_date,
                txn_month, trade_time, pay_receive_time, bank_serial_no, source_unique_key,
                data_fingerprint, legacy_source_batch_id, counterparty_id, project_id, balance,
                currency, summary, remark, bank_text_fields, status, raw_payload
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date,
                date_trunc('month', %s::date)::date, %s::timestamptz, %s::timestamptz, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            on conflict (legacy_mongo_id) do update set
                account_no = excluded.account_no,
                account_name = excluded.account_name,
                txn_direction = excluded.txn_direction,
                counterparty_name_raw = excluded.counterparty_name_raw,
                normalized_counterparty_name = excluded.normalized_counterparty_name,
                amount = excluded.amount,
                signed_amount = excluded.signed_amount,
                written_off_amount = excluded.written_off_amount,
                txn_date = excluded.txn_date,
                txn_month = excluded.txn_month,
                trade_time = excluded.trade_time,
                pay_receive_time = excluded.pay_receive_time,
                bank_serial_no = excluded.bank_serial_no,
                source_unique_key = excluded.source_unique_key,
                data_fingerprint = excluded.data_fingerprint,
                legacy_source_batch_id = excluded.legacy_source_batch_id,
                counterparty_id = excluded.counterparty_id,
                project_id = excluded.project_id,
                balance = excluded.balance,
                currency = excluded.currency,
                summary = excluded.summary,
                remark = excluded.remark,
                bank_text_fields = excluded.bank_text_fields,
                status = excluded.status,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                transaction_id,
                self._text(transaction.get("account_no")) or "unknown",
                self._text(transaction.get("account_name")),
                self._text(transaction.get("txn_direction")) or TransactionDirection.OUTFLOW.value,
                self._text(transaction.get("counterparty_name_raw")) or "unknown",
                self._text(transaction.get("normalized_counterparty_name") or transaction.get("counterparty_name_raw")),
                self._decimal_text(transaction.get("amount")) or "0",
                self._decimal_text(transaction.get("signed_amount")) or self._decimal_text(transaction.get("amount")) or "0",
                self._decimal_text(transaction.get("written_off_amount")) or "0",
                self._date_text(transaction.get("txn_date")),
                self._date_text(transaction.get("txn_date")),
                self._text(transaction.get("trade_time")),
                self._text(transaction.get("pay_receive_time")),
                self._text(transaction.get("bank_serial_no")),
                self._text(transaction.get("source_unique_key")),
                self._text(transaction.get("data_fingerprint")),
                self._text(transaction.get("source_batch_id") or transaction.get("legacy_source_batch_id")),
                self._text(transaction.get("counterparty_id")),
                self._text(transaction.get("project_id")),
                self._decimal_text(transaction.get("balance")),
                self._text(transaction.get("currency")),
                self._text(transaction.get("summary")),
                self._text(transaction.get("remark")),
                _jsonb(transaction.get("bank_text_fields") if isinstance(transaction.get("bank_text_fields"), list) else []),
                self._text(transaction.get("status")) or TransactionStatus.PENDING.value,
                _jsonb({"normalized_payload": transaction}),
            ),
        )

    def _batch_from_row(self, row: dict[str, Any]) -> ImportedBatch:
        payload = self._row_payload(row)
        if isinstance(payload, dict) and isinstance(payload.get("batch"), dict):
            payload = payload["batch"]
        payload = payload if isinstance(payload, dict) else {}
        return ImportedBatch(
            id=self._text(payload.get("id") or row.get("legacy_id")) or str(row.get("legacy_id")),
            batch_type=BatchType(self._text(payload.get("batch_type") or row.get("batch_type")) or BatchType.BANK_TRANSACTION.value),
            source_name=self._text(payload.get("source_name") or row.get("source_name")) or "unknown",
            imported_by=self._text(payload.get("imported_by") or row.get("imported_by")) or "unknown",
            row_count=self._int(payload.get("row_count") or row.get("row_count"), 0),
            success_count=self._int(payload.get("success_count") or row.get("success_count"), 0),
            error_count=self._int(payload.get("error_count") or row.get("error_count"), 0),
            status=BatchStatus(self._text(payload.get("status") or row.get("status")) or BatchStatus.PENDING.value),
            duplicate_count=self._int(payload.get("duplicate_count") or row.get("duplicate_count"), 0),
            suspected_duplicate_count=self._int(payload.get("suspected_duplicate_count") or row.get("suspected_duplicate_count"), 0),
            updated_count=self._int(payload.get("updated_count") or row.get("updated_count"), 0),
            imported_at=self._datetime(payload.get("imported_at") or row.get("imported_at")),
        )

    def _batch_row_from_row(self, row: dict[str, Any]) -> ImportedBatchRowResult:
        payload = self._row_payload(row)
        payload = payload if isinstance(payload, dict) else {}
        batch_id = self._text(payload.get("batch_id") or row.get("legacy_batch_id") or row.get("joined_batch_id")) or "unknown"
        return ImportedBatchRowResult(
            id=self._text(payload.get("id") or row.get("legacy_id")) or str(row.get("legacy_id")),
            batch_id=batch_id,
            row_no=self._int(payload.get("row_no") or row.get("row_no"), 0),
            source_record_type=self._text(payload.get("source_record_type") or row.get("source_record_type")) or "unknown",
            source_unique_key=self._text(payload.get("source_unique_key") or row.get("source_unique_key")),
            data_fingerprint=self._text(payload.get("data_fingerprint") or row.get("data_fingerprint")),
            decision=ImportDecision(self._text(payload.get("decision") or row.get("decision")) or ImportDecision.ERROR.value),
            decision_reason=self._text(payload.get("decision_reason") or row.get("decision_reason")) or "",
            linked_object_type=self._text(payload.get("linked_object_type") or row.get("linked_object_type")),
            linked_object_id=self._text(payload.get("linked_object_id") or row.get("linked_object_id")),
            raw_payload=dict(payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else payload),
            identity_kind=self._text(payload.get("identity_kind") or row.get("identity_kind")),
            account_no=self._text(payload.get("account_no") or row.get("account_no")),
            trade_time=self._text(payload.get("trade_time") or row.get("trade_time")),
            direction=self._text(payload.get("direction") or row.get("direction")),
            amount=self._text(payload.get("amount") or row.get("amount")),
            counterparty_name=self._text(payload.get("counterparty_name") or row.get("counterparty_name")),
        )

    def _invoice_from_row(self, row: dict[str, Any]) -> Invoice:
        payload = self._row_payload(row)
        payload = payload if isinstance(payload, dict) else {}
        counterparty_payload = payload.get("counterparty") if isinstance(payload.get("counterparty"), dict) else {}
        counterparty_name = self._text(counterparty_payload.get("name") or row.get("counterparty_name")) or "unknown"
        source_unique_key = self._text(payload.get("source_unique_key") or row.get("source_unique_key"))
        data_fingerprint = (
            None
            if source_unique_key
            else self._text(payload.get("data_fingerprint") or row.get("data_fingerprint"))
        )
        counterparty = Counterparty(
            id=self._text(counterparty_payload.get("id") or row.get("counterparty_id")) or f"counterparty:{counterparty_name}",
            name=counterparty_name,
            normalized_name=self._text(counterparty_payload.get("normalized_name")) or counterparty_name,
            counterparty_type=self._text(counterparty_payload.get("counterparty_type")) or "unknown",
            tax_no=self._text(counterparty_payload.get("tax_no") or row.get("seller_tax_no") or row.get("buyer_tax_no")),
        )
        return Invoice(
            id=self._text(row.get("legacy_id") or payload.get("id")) or str(row.get("legacy_id")),
            invoice_type=InvoiceType(self._text(payload.get("invoice_type") or row.get("invoice_type")) or InvoiceType.INPUT.value),
            invoice_no=self._text(payload.get("invoice_no") or row.get("invoice_no")) or str(row.get("legacy_id")),
            counterparty=counterparty,
            amount=Decimal(str(payload.get("amount") or row.get("amount") or "0")),
            signed_amount=Decimal(str(payload.get("signed_amount") or row.get("signed_amount") or payload.get("amount") or row.get("amount") or "0")),
            invoice_code=self._text(payload.get("invoice_code") or row.get("invoice_code")),
            digital_invoice_no=self._text(payload.get("digital_invoice_no") or row.get("digital_invoice_no")),
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
            invoice_status_from_source=self._text(
                payload.get("invoice_status_from_source") or row.get("invoice_status_from_source")
            ),
            written_off_amount=Decimal(str(payload.get("written_off_amount") or row.get("written_off_amount") or "0")),
            currency=self._text(payload.get("currency") or row.get("currency")) or "CNY",
            invoice_date=self._date_text(payload.get("invoice_date") or row.get("invoice_date")),
            seller_tax_no=self._text(payload.get("seller_tax_no") or row.get("seller_tax_no")),
            seller_name=self._text(payload.get("seller_name") or row.get("seller_name")),
            buyer_tax_no=self._text(payload.get("buyer_tax_no") or row.get("buyer_tax_no")),
            buyer_name=self._text(payload.get("buyer_name") or row.get("buyer_name")),
            tax_rate=self._text(payload.get("tax_rate") or row.get("tax_rate")),
            tax_amount=self._decimal_or_none(payload.get("tax_amount") or row.get("tax_amount")),
            total_with_tax=self._decimal_or_none(payload.get("total_with_tax") or row.get("total_with_tax")),
            source_batch_id=self._text(payload.get("source_batch_id") or row.get("legacy_source_batch_id")),
            oa_form_id=self._text(payload.get("oa_form_id") or row.get("oa_form_id")),
            tags=self._text_list(payload.get("tags") or row.get("tags")),
            source_links=list(payload.get("source_links") if isinstance(payload.get("source_links"), list) else row.get("source_links") or []),
            etc_invoice_id=self._text(payload.get("etc_invoice_id") or row.get("etc_invoice_id")),
            etc_import_batch_id=self._text(payload.get("etc_import_batch_id") or row.get("etc_import_batch_id")),
            etc_submission_batch_id=self._text(payload.get("etc_submission_batch_id") or row.get("etc_submission_batch_id")),
            etc_submission_status=self._text(payload.get("etc_submission_status") or row.get("etc_submission_status")),
            workbench_visibility=self._text(payload.get("workbench_visibility") or row.get("workbench_visibility")) or "visible",
            status=InvoiceStatus(self._text(payload.get("status") or row.get("status")) or InvoiceStatus.PENDING.value),
        )

    def _transaction_from_row(self, row: dict[str, Any]) -> BankTransaction:
        payload = self._row_payload(row)
        payload = payload if isinstance(payload, dict) else {}
        return BankTransaction(
            id=self._text(payload.get("id") or row.get("legacy_id")) or str(row.get("legacy_id")),
            account_no=self._text(payload.get("account_no") or row.get("account_no")) or "unknown",
            txn_direction=TransactionDirection(self._text(payload.get("txn_direction") or row.get("txn_direction")) or TransactionDirection.OUTFLOW.value),
            counterparty_name_raw=self._text(payload.get("counterparty_name_raw") or row.get("counterparty_name_raw")) or "unknown",
            amount=Decimal(str(payload.get("amount") or row.get("amount") or "0")),
            signed_amount=Decimal(str(payload.get("signed_amount") or row.get("signed_amount") or payload.get("amount") or row.get("amount") or "0")),
            bank_serial_no=self._text(payload.get("bank_serial_no") or row.get("bank_serial_no")),
            source_unique_key=self._text(payload.get("source_unique_key") or row.get("source_unique_key")),
            data_fingerprint=self._text(payload.get("data_fingerprint") or row.get("data_fingerprint")),
            written_off_amount=Decimal(str(payload.get("written_off_amount") or row.get("written_off_amount") or "0")),
            txn_date=self._date_text(payload.get("txn_date") or row.get("txn_date")),
            trade_time=self._text(payload.get("trade_time") or row.get("trade_time")),
            pay_receive_time=self._text(payload.get("pay_receive_time") or row.get("pay_receive_time")),
            counterparty_id=self._text(payload.get("counterparty_id") or row.get("counterparty_id")),
            project_id=self._text(payload.get("project_id") or row.get("project_id")),
            source_batch_id=self._text(payload.get("source_batch_id") or row.get("legacy_source_batch_id")),
            account_name=self._text(payload.get("account_name") or row.get("account_name")),
            balance=self._decimal_or_none(payload.get("balance") or row.get("balance")),
            currency=self._text(payload.get("currency") or row.get("currency")),
            summary=self._text(payload.get("summary") or row.get("summary")),
            remark=self._text(payload.get("remark") or row.get("remark")),
            bank_text_fields=list(payload.get("bank_text_fields") if isinstance(payload.get("bank_text_fields"), list) else row.get("bank_text_fields") or []),
            imported_bank_name=self._text(payload.get("imported_bank_name") or row.get("imported_bank_name") or payload.get("bank_name") or row.get("bank_name")),
            imported_bank_last4=self._text(
                payload.get("imported_bank_last4")
                or row.get("imported_bank_last4")
                or payload.get("account_last4")
                or row.get("account_last4")
            ),
            status=TransactionStatus(self._text(payload.get("status") or row.get("status")) or TransactionStatus.PENDING.value),
        )

    def _file_item_from_row(self, row: dict[str, Any], payload: dict[str, Any]) -> FileImportPreviewItem:
        batch_type = self._text(payload.get("batch_type") or payload.get("override_batch_type"))
        return FileImportPreviewItem(
            id=self._text(payload.get("id") or row.get("legacy_id")) or str(row.get("legacy_id")),
            file_name=self._text(payload.get("file_name") or row.get("original_filename")) or "unknown",
            template_code=self._text(payload.get("template_code") or row.get("template_kind")),
            batch_type=BatchType(batch_type) if batch_type else None,
            status=self._text(payload.get("status") or row.get("status")) or "stored",
            message=self._text(payload.get("message")) or "",
            row_count=self._int(payload.get("row_count"), 0),
            success_count=self._int(payload.get("success_count"), 0),
            error_count=self._int(payload.get("error_count"), 0),
            duplicate_count=self._int(payload.get("duplicate_count"), 0),
            suspected_duplicate_count=self._int(payload.get("suspected_duplicate_count"), 0),
            updated_count=self._int(payload.get("updated_count"), 0),
            preview_batch_id=self._text(payload.get("preview_batch_id")),
            batch_id=self._text(payload.get("batch_id")),
            stored_file_path=self._text(payload.get("stored_file_path") or row.get("stored_file_path")),
            override_template_code=self._text(payload.get("override_template_code")),
            override_batch_type=BatchType(self._text(payload.get("override_batch_type"))) if self._text(payload.get("override_batch_type")) else None,
            selected_bank_mapping_id=self._text(payload.get("selected_bank_mapping_id")),
            selected_bank_name=self._text(payload.get("selected_bank_name")),
            selected_bank_short_name=self._text(payload.get("selected_bank_short_name")),
            selected_bank_last4=self._text(payload.get("selected_bank_last4")),
            detected_bank_name=self._text(payload.get("detected_bank_name")),
            detected_last4=self._text(payload.get("detected_last4")),
            bank_selection_conflict=bool(payload.get("bank_selection_conflict") or False),
            conflict_message=self._text(payload.get("conflict_message")),
            row_results=self._file_row_results_from_payload(payload),
            normalized_rows=self._file_normalized_rows_from_payload(payload),
            audit=self._audit_counts_from_payload(payload.get("audit")),
        )

    def _file_summary_item_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        batch_type = self._text(row.get("payload_batch_type") or row.get("payload_override_batch_type"))
        return {
            "id": self._text(row.get("legacy_id")) or str(row.get("legacy_id")),
            "file_name": self._text(row.get("original_filename")) or "unknown",
            "template_code": self._text(row.get("template_kind")),
            "batch_type": BatchType(batch_type).value if batch_type else None,
            "status": self._text(row.get("status")) or "stored",
            "message": self._text(row.get("payload_message")) or "",
            "row_count": self._int(row.get("payload_row_count"), 0),
            "success_count": self._int(row.get("payload_success_count"), 0),
            "error_count": self._int(row.get("payload_error_count"), 0),
            "duplicate_count": self._int(row.get("payload_duplicate_count"), 0),
            "suspected_duplicate_count": self._int(row.get("payload_suspected_duplicate_count"), 0),
            "updated_count": self._int(row.get("payload_updated_count"), 0),
            "preview_batch_id": self._text(row.get("payload_preview_batch_id")),
            "batch_id": self._text(row.get("payload_batch_id")),
            "stored_file_path": self._text(row.get("stored_file_path")),
            "audit": self._serialize(self._audit_counts_from_payload(row.get("payload_audit"))),
        }

    def _file_row_results_from_payload(self, payload: dict[str, Any]) -> list[ImportedBatchRowResult]:
        rows = payload.get("row_results")
        if not isinstance(rows, list):
            return []
        results: list[ImportedBatchRowResult] = []
        for row in rows:
            if isinstance(row, dict):
                results.append(self._batch_row_from_row({"raw_payload": {"normalized_payload": row}}))
        return results

    @staticmethod
    def _file_normalized_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("normalized_rows")
        if not isinstance(rows, list):
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _audit_counts_from_payload(self, payload: Any) -> ImportPreviewAuditCounts:
        if isinstance(payload, ImportPreviewAuditCounts):
            return payload
        payload = payload if isinstance(payload, dict) else {}
        return ImportPreviewAuditCounts(
            original_count=self._int(payload.get("original_count"), 0),
            unique_count=self._int(payload.get("unique_count"), 0),
            duplicate_count=self._int(payload.get("duplicate_count"), 0),
            duplicate_in_file_count=self._int(payload.get("duplicate_in_file_count"), 0),
            duplicate_across_files_count=self._int(payload.get("duplicate_across_files_count"), 0),
            existing_duplicate_count=self._int(payload.get("existing_duplicate_count"), 0),
            importable_count=self._int(payload.get("importable_count"), 0),
            update_count=self._int(payload.get("update_count"), 0),
            merge_count=self._int(payload.get("merge_count"), 0),
            suspected_duplicate_count=self._int(payload.get("suspected_duplicate_count"), 0),
            error_count=self._int(payload.get("error_count"), 0),
            confirmable_count=self._int(payload.get("confirmable_count"), 0),
            skipped_count=self._int(payload.get("skipped_count"), 0),
        )

    def _duplicate_groups_from_payload(self, payload: Any) -> list[ImportPreviewDuplicateGroup]:
        groups = payload if isinstance(payload, list) else []
        result: list[ImportPreviewDuplicateGroup] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            result.append(
                ImportPreviewDuplicateGroup(
                    identity_key=self._text(group.get("identity_key")) or "",
                    record_type=self._text(group.get("record_type")) or "",
                    duplicate_type=self._text(group.get("duplicate_type")) or "",
                    rows=[dict(row) for row in group.get("rows", []) if isinstance(row, dict)],
                )
            )
        return result

    def _fetch_invoice_by_clause(self, where_clause: str, params: tuple[Any, ...]) -> Invoice | None:
        row = self._connection.fetch_one(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
                   data_fingerprint, invoice_date, counterparty_id, counterparty_name, seller_name,
                   seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount, written_off_amount,
                   tax_rate, tax_amount, total_with_tax, currency, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status, tags, source_links, raw_payload
            from app.invoices
            where {where_clause}
            limit 1
            """,
            params,
        )
        return self._invoice_from_row(row) if row else None

    def _fetch_invoices_by_clause(self, where_clause: str, params: tuple[Any, ...]) -> list[Invoice]:
        rows = self._connection.fetch_all(
            f"""
            select id::text as postgres_id, coalesce(legacy_mongo_id, id::text) as legacy_id,
                   invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
                   data_fingerprint, invoice_date, counterparty_id, counterparty_name, seller_name,
                   seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount, written_off_amount,
                   tax_rate, tax_amount, total_with_tax, currency, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status, tags, source_links, raw_payload
            from app.invoices
            where {where_clause}
            order by created_at, id
            """,
            params,
        )
        return [self._invoice_from_row(row) for row in rows or [] if row]

    @staticmethod
    def _unique_texts(values: list[str] | tuple[str, ...] | set[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _page_bounds(page: int, page_size: int) -> tuple[int, int]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 100), 1), 500)
        return normalized_page_size, (normalized_page - 1) * normalized_page_size

    def _invoice_filter_sql(
        self,
        *,
        month: str | None,
        invoice_type: str | None,
        status: str | None,
        keyword: str | None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []
        if text := self._text(month):
            clauses.append("invoice_month = (%s || '-01')::date")
            params.append(text[:7])
        if text := self._text(invoice_type):
            clauses.append("invoice_type = %s")
            params.append(text)
        if text := self._text(status):
            clauses.append("status = %s")
            params.append(text)
        if text := self._text(keyword):
            like = f"%{text}%"
            clauses.append("(invoice_no ilike %s or counterparty_name ilike %s or seller_name ilike %s or buyer_name ilike %s)")
            params.extend([like, like, like, like])
        return ("where " + " and ".join(clauses) if clauses else ""), tuple(params)

    def _bank_transaction_filter_sql(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []
        if text := self._text(account_key):
            try:
                bank_name, account_last4 = text.rsplit(":", 1)
            except ValueError:
                bank_name, account_last4 = "", text
            bank_name = bank_name.replace("-", " ")
            clauses.append(
                "(lower(coalesce(raw_payload->'normalized_payload'->>'imported_bank_name', '')) = %s "
                "or right(account_no, 4) = %s)"
            )
            params.extend([bank_name.lower(), account_last4])
        if text := self._text(date_from):
            clauses.append("txn_date >= %s::date")
            params.append(text[:10])
        if text := self._text(date_to):
            clauses.append("txn_date <= %s::date")
            params.append(text[:10])
        if text := self._text(keyword):
            like = f"%{text}%"
            clauses.append("(counterparty_name_raw ilike %s or summary ilike %s or remark ilike %s or bank_serial_no ilike %s)")
            params.extend([like, like, like, like])
        return ("where " + " and ".join(clauses) if clauses else ""), tuple(params)

    def _month_key(self, value: Any) -> str | None:
        text = self._date_text(value)
        return text[:7] if text and len(text) >= 7 else None

    @staticmethod
    def _row_payload(row: dict[str, Any] | None) -> Any:
        if not row:
            return None
        raw_payload = row.get("raw_payload")
        if isinstance(raw_payload, dict) and "normalized_payload" in raw_payload:
            return raw_payload.get("normalized_payload") or {}
        return raw_payload

    def _iter_previews(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [item for item in (self._serialize(raw) for raw in value.values()) if isinstance(item, dict)]
        if isinstance(value, list):
            return [item for item in (self._serialize(raw) for raw in value) if isinstance(item, dict)]
        return []

    def _iter_items(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [item for item in (self._serialize(raw) for raw in value.values()) if isinstance(item, dict)]
        if isinstance(value, list):
            return [item for item in (self._serialize(raw) for raw in value) if isinstance(item, dict)]
        return []

    def _serialize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {key: self._serialize(getattr(value, key, None)) for key in value.__dataclass_fields__}  # type: ignore[attr-defined]
        if isinstance(value, dict):
            return {str(key): self._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        return value

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        text = str(value).strip()
        return text or None

    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _decimal_text(value: Any) -> str | None:
        if value is None or value == "":
            return None
        try:
            return str(Decimal(str(value)))
        except Exception:
            return None

    @classmethod
    def _decimal_or_none(cls, value: Any) -> Decimal | None:
        text = cls._decimal_text(value)
        return Decimal(text) if text is not None else None

    @classmethod
    def _text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [text for item in value if (text := cls._text(item))]
        text = cls._text(value)
        return [text] if text else []

    @staticmethod
    def _date_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        return text[:10] if text else None

    @classmethod
    def _datetime(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        text = cls._text(value)
        if text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _max_suffix(values: dict[str, Any]) -> int:
        maximum = 0
        for key in values:
            try:
                maximum = max(maximum, int(str(key).rsplit("_", 1)[-1]))
            except ValueError:
                continue
        return maximum
