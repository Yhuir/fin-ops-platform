from __future__ import annotations

import re
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator
from uuid import uuid4

from fin_ops_platform.domain.enums import BatchStatus, BatchType, ImportDecision, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import (
    BankTransaction,
    Counterparty,
    ImportedBatch,
    ImportedBatchRowResult,
    Invoice,
)
from fin_ops_platform.services.etc_batch_invoice_link_service import EtcBatchInvoiceLinkService
from fin_ops_platform.services.object_dedup_decision_service import ObjectDedupDecisionService
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
WHITESPACE_RE = re.compile(r"\s+")
PLACEHOLDER_EMPTY_VALUES = {"", "--", "—", "-", "——", "nan", "NaN", "None"}
BANK_TEXT_FIELD_LABELS = ("摘要", "备注", "用途", "交易用途", "客户附言", "附言")


def _month_date_range(month: str) -> tuple[str, str] | None:
    normalized = str(month or "").strip()[:7]
    if not re.match(r"^\d{4}-\d{2}$", normalized):
        return None
    start = date.fromisoformat(f"{normalized}-01")
    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    end = next_month - timedelta(days=1)
    return start.isoformat(), end.isoformat()


@dataclass(slots=True)
class ImportPreview:
    batch: ImportedBatch
    row_results: list[ImportedBatchRowResult]
    normalized_rows: list[dict[str, Any]]

    @property
    def id(self) -> str:
        return self.batch.id

    @property
    def success_count(self) -> int:
        return self.batch.success_count

    @property
    def error_count(self) -> int:
        return self.batch.error_count

    @property
    def duplicate_count(self) -> int:
        return self.batch.duplicate_count

    @property
    def suspected_duplicate_count(self) -> int:
        return self.batch.suspected_duplicate_count

    @property
    def updated_count(self) -> int:
        return self.batch.updated_count

    @property
    def status(self) -> BatchStatus:
        return self.batch.status


@dataclass(frozen=True, slots=True)
class EtcInvoiceUpsertResult:
    invoice: Invoice | None
    changed: bool


class _ImportObjectIdentityRepository:
    def __init__(self, import_service: "ImportNormalizationService") -> None:
        self._import_service = import_service

    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        return self._import_service._find_invoice_by_identity(
            source_unique_key=canonical_key,
            data_fingerprint=suspected_key,
        )

    def find_invoices_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[Invoice]:
        return self._import_service._find_invoices_by_identity(
            source_unique_key=canonical_key,
            data_fingerprint=suspected_key,
        )

    def find_bank_transaction_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> BankTransaction | None:
        return self._import_service._find_transaction_by_identity(
            source_unique_key=canonical_key,
            data_fingerprint=suspected_key,
        )

    def find_bank_transactions_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[BankTransaction]:
        return self._import_service._find_transactions_by_identity(
            source_unique_key=canonical_key,
            data_fingerprint=suspected_key,
        )

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        return self.find_invoice_by_identity(canonical_key=canonical_key) is not None


class ImportNormalizationService:
    def __init__(
        self,
        *,
        existing_invoices: list[Invoice] | None = None,
        existing_transactions: list[BankTransaction] | None = None,
        id_registry: Any | None = None,
        fact_repository: Any | None = None,
        etc_batch_invoice_link_service: Any | None = None,
        identity_policy: FinancialObjectIdentityPolicy | None = None,
        dedup_decision_service: ObjectDedupDecisionService | None = None,
    ) -> None:
        self._batch_counter = 0
        self._invoice_counter = len(existing_invoices or [])
        self._txn_counter = len(existing_transactions or [])
        self._counterparty_counter = 0
        self._id_registry = id_registry
        self._fact_repository = fact_repository
        self._etc_batch_invoice_link_service = etc_batch_invoice_link_service
        if self._etc_batch_invoice_link_service is None and hasattr(fact_repository, "upsert_etc_batch_invoice_link"):
            self._etc_batch_invoice_link_service = EtcBatchInvoiceLinkService(repository=fact_repository)
        self._object_identity_policy = identity_policy or FinancialObjectIdentityPolicy()

        self._batches: dict[str, ImportPreview] = {}
        self._invoices_by_id: dict[str, Invoice] = {}
        self._transactions_by_id: dict[str, BankTransaction] = {}
        self._counterparties_by_normalized_name: dict[str, Counterparty] = {}

        self._invoice_unique_index: dict[str, str] = {}
        self._invoice_fingerprint_index: dict[str, str] = {}
        self._invoice_identity_cache: dict[tuple[str, str], Invoice] | None = None
        self._transaction_unique_index: dict[str, str] = {}
        self._transaction_fingerprint_index: dict[str, str] = {}
        self._transaction_identity_cache: dict[tuple[str, str], list[BankTransaction]] | None = None

        for invoice in existing_invoices or []:
            self._register_invoice(invoice)
        for transaction in existing_transactions or []:
            self._register_transaction(transaction)
        self._object_identity_repository = _ImportObjectIdentityRepository(self)
        self._dedup_decision_service = dedup_decision_service or ObjectDedupDecisionService(
            identity_policy=self._object_identity_policy,
            object_identity_repository=self._object_identity_repository,
        )

    def oa_attachment_invoice_row_id(
        self,
        oa_row_id: str,
        index: int,
        attachment_invoice: dict[str, Any] | None = None,
    ) -> str:
        return self._object_identity_policy.oa_attachment_invoice_row_id(
            oa_row_id,
            index,
            attachment_invoice,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        id_registry: Any | None = None,
        fact_repository: Any | None = None,
    ) -> ImportNormalizationService:
        service = cls(
            existing_invoices=list((snapshot or {}).get("invoices", [])),
            existing_transactions=list((snapshot or {}).get("transactions", [])),
            id_registry=id_registry,
            fact_repository=fact_repository,
        )
        if not snapshot:
            return service
        service._batch_counter = int(snapshot.get("batch_counter", 0))
        service._invoice_counter = int(snapshot.get("invoice_counter", service._invoice_counter))
        service._txn_counter = int(snapshot.get("txn_counter", service._txn_counter))
        service._counterparty_counter = int(snapshot.get("counterparty_counter", service._counterparty_counter))
        service._batches = dict(snapshot.get("batches", {}))
        return service

    def snapshot(self) -> dict[str, Any]:
        return {
            "batch_counter": self._batch_counter,
            "invoice_counter": self._invoice_counter,
            "txn_counter": self._txn_counter,
            "counterparty_counter": self._counterparty_counter,
            "batches": self._batches,
            "invoices": self.list_invoices(),
            "transactions": self.list_transactions(),
        }

    def persistence_snapshot_for_batches(
        self,
        batch_ids: list[str],
        *,
        include_facts: bool = True,
    ) -> dict[str, Any]:
        selected_ids = {str(batch_id).strip() for batch_id in batch_ids if str(batch_id).strip()}
        selected_batches = {
            batch_id: self._batches[batch_id]
            for batch_id in selected_ids
            if batch_id in self._batches
        }
        snapshot: dict[str, Any] = {
            "batch_counter": self._batch_counter,
            "invoice_counter": self._invoice_counter,
            "txn_counter": self._txn_counter,
            "counterparty_counter": self._counterparty_counter,
            "batches": selected_batches,
        }
        if not include_facts:
            return snapshot
        invoice_ids: set[str] = set()
        transaction_ids: set[str] = set()
        for preview in selected_batches.values():
            for row in preview.row_results:
                linked_id = str(row.linked_object_id or "").strip()
                if not linked_id:
                    continue
                if row.linked_object_type == "invoice":
                    invoice_ids.add(linked_id)
                elif (
                    row.linked_object_type == "bank_transaction"
                    and row.decision in {ImportDecision.CREATED, ImportDecision.STATUS_UPDATED}
                ):
                    transaction_ids.add(linked_id)
        snapshot["invoices"] = [self._invoices_by_id[invoice_id] for invoice_id in sorted(invoice_ids)]
        snapshot["transactions"] = [
            self._transactions_by_id[transaction_id]
            for transaction_id in sorted(transaction_ids)
        ]
        return snapshot

    def preview_import(
        self,
        *,
        batch_type: BatchType,
        source_name: str,
        imported_by: str,
        rows: list[dict[str, Any]],
    ) -> ImportPreview:
        row_results: list[ImportedBatchRowResult] = []
        normalized_rows: list[dict[str, Any]] = []

        batch_id = self._next_batch_id()
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            prepared_rows = [
                (index, raw_row, *self._normalize_invoice_row(batch_type=batch_type, raw_row=raw_row))
                for index, raw_row in enumerate(rows, start=1)
            ]
            with self._invoice_identity_cache_for([normalized for _, _, normalized, _errors in prepared_rows]):
                for index, raw_row, normalized, errors in prepared_rows:
                    row_result = self._preview_invoice_row_from_normalized(
                        batch_id=batch_id,
                        row_no=index,
                        raw_row=raw_row,
                        normalized=normalized,
                        errors=errors,
                    )
                    normalized_rows.append(normalized)
                    row_results.append(row_result)
        else:
            prepared_rows = [
                (index, raw_row, *self._normalize_transaction_row(raw_row))
                for index, raw_row in enumerate(rows, start=1)
            ]
            with self._transaction_identity_cache_for(
                [normalized for _, _, normalized, _errors in prepared_rows]
            ):
                for index, raw_row, normalized, errors in prepared_rows:
                    row_result = self._preview_transaction_row_from_normalized(
                        batch_id=batch_id,
                        row_no=index,
                        raw_row=raw_row,
                        normalized=normalized,
                        errors=errors,
                    )
                    normalized_rows.append(normalized)
                    row_results.append(row_result)

        batch = ImportedBatch(
            id=batch_id,
            batch_type=batch_type,
            source_name=source_name,
            imported_by=imported_by,
            row_count=len(rows),
            success_count=self._count_decisions(row_results, ImportDecision.CREATED, ImportDecision.STATUS_UPDATED),
            error_count=self._count_decisions(row_results, ImportDecision.ERROR),
            status=BatchStatus.PENDING,
            duplicate_count=self._count_decisions(row_results, ImportDecision.DUPLICATE_SKIPPED),
            suspected_duplicate_count=self._count_decisions(row_results, ImportDecision.SUSPECTED_DUPLICATE),
            updated_count=self._count_decisions(row_results, ImportDecision.STATUS_UPDATED),
        )
        preview = ImportPreview(batch=batch, row_results=row_results, normalized_rows=normalized_rows)
        self._batches[batch_id] = preview
        return preview

    def confirm_import(self, batch_id: str) -> ImportedBatch:
        preview = self._batches[batch_id]
        if preview.batch.status != BatchStatus.PENDING:
            return preview.batch
        rollback = {
            "preview": deepcopy(preview),
            "invoices": deepcopy(self._invoices_by_id),
            "transactions": deepcopy(self._transactions_by_id),
            "counterparties": deepcopy(self._counterparties_by_normalized_name),
            "invoice_unique_index": dict(self._invoice_unique_index),
            "invoice_fingerprint_index": dict(self._invoice_fingerprint_index),
            "transaction_unique_index": dict(self._transaction_unique_index),
            "transaction_fingerprint_index": dict(self._transaction_fingerprint_index),
            "invoice_counter": self._invoice_counter,
            "txn_counter": self._txn_counter,
            "counterparty_counter": self._counterparty_counter,
        }
        try:
            with self._invoice_identity_cache_for(
                preview.normalized_rows,
                enabled=preview.batch.batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE),
            ):
                with self._transaction_identity_cache_for(
                    preview.normalized_rows,
                    enabled=preview.batch.batch_type == BatchType.BANK_TRANSACTION,
                ):
                    for row_result, normalized in zip(preview.row_results, preview.normalized_rows, strict=True):
                        self._refresh_row_decision_before_confirm(preview.batch.batch_type, row_result, normalized)
                        if row_result.decision == ImportDecision.CREATED:
                            self._persist_created_row(preview.batch.batch_type, row_result, normalized)
                        elif row_result.decision == ImportDecision.STATUS_UPDATED:
                            self._persist_updated_row(preview.batch.batch_type, row_result, normalized)
                        elif row_result.decision == ImportDecision.DUPLICATE_SKIPPED:
                            self._persist_duplicate_row(preview.batch.batch_type, row_result, normalized)

            preview.batch.success_count = self._count_decisions(preview.row_results, ImportDecision.CREATED, ImportDecision.STATUS_UPDATED)
            preview.batch.duplicate_count = self._count_decisions(preview.row_results, ImportDecision.DUPLICATE_SKIPPED)
            preview.batch.suspected_duplicate_count = self._count_decisions(preview.row_results, ImportDecision.SUSPECTED_DUPLICATE)
            preview.batch.updated_count = self._count_decisions(preview.row_results, ImportDecision.STATUS_UPDATED)
            preview.batch.error_count = self._count_decisions(preview.row_results, ImportDecision.ERROR)
            has_issues = preview.error_count > 0 or preview.suspected_duplicate_count > 0
            preview.batch.status = BatchStatus.COMPLETED_WITH_ERRORS if has_issues else BatchStatus.COMPLETED
            self._batches[batch_id] = preview
            return preview.batch
        except Exception:
            self._batches[batch_id] = rollback["preview"]
            self._invoices_by_id = rollback["invoices"]
            self._transactions_by_id = rollback["transactions"]
            self._counterparties_by_normalized_name = rollback["counterparties"]
            self._invoice_unique_index = rollback["invoice_unique_index"]
            self._invoice_fingerprint_index = rollback["invoice_fingerprint_index"]
            self._transaction_unique_index = rollback["transaction_unique_index"]
            self._transaction_fingerprint_index = rollback["transaction_fingerprint_index"]
            self._invoice_counter = rollback["invoice_counter"]
            self._txn_counter = rollback["txn_counter"]
            self._counterparty_counter = rollback["counterparty_counter"]
            raise

    def discard_preview(self, batch_id: str) -> ImportedBatch:
        preview = self._batches[batch_id]
        if preview.batch.status == BatchStatus.REVERTED:
            return preview.batch
        if preview.batch.status != BatchStatus.PENDING:
            raise ValueError("only pending import previews can be reverted")
        preview.batch.status = BatchStatus.REVERTED
        self._batches[batch_id] = preview
        return preview.batch

    def _refresh_row_decision_before_confirm(
        self,
        batch_type: BatchType,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        if row_result.decision != ImportDecision.CREATED:
            return
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            self._refresh_invoice_row_decision_before_confirm(row_result, normalized)
        else:
            decision, linked_object_type, linked_object_id = self.current_import_decision_for_normalized_row(
                batch_type=batch_type,
                normalized=normalized,
            )
            if decision in (ImportDecision.DUPLICATE_SKIPPED, ImportDecision.SUSPECTED_DUPLICATE):
                row_result.decision = decision
                row_result.linked_object_type = linked_object_type
                row_result.linked_object_id = linked_object_id
                row_result.decision_reason = (
                    "Bank transaction identity matched an existing transaction during confirm."
                    if decision == ImportDecision.DUPLICATE_SKIPPED
                    else "Bank transaction fingerprint matched during confirm; review before importing."
                )

    def _refresh_invoice_row_decision_before_confirm(
        self,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        source_unique_key = normalized.get("source_unique_key")
        decision = self._dedup_decision_service.decide_invoice_confirm(normalized)
        existing = decision.matched_object if isinstance(decision.matched_object, Invoice) else None
        if source_unique_key and existing is not None:
            normalized["previous_invoice_status_from_source"] = existing.invoice_status_from_source
            normalized["previous_source_batch_id"] = existing.source_batch_id
        if decision.linked_object_id:
            row_result.linked_object_type = decision.linked_object_type
            row_result.linked_object_id = decision.linked_object_id
            row_result.decision = ImportDecision(decision.decision)
            row_result.decision_reason = decision.decision_reason

    def get_batch(self, batch_id: str) -> ImportPreview:
        return self._batches[batch_id]

    def list_batches(self) -> list[ImportPreview]:
        return list(self._batches.values())

    def list_invoices(
        self,
        *,
        month: str | None = None,
        invoice_type: InvoiceType | str | None = None,
    ) -> list[Invoice]:
        normalized_month = str(month).strip() if month not in (None, "") else ""
        normalized_invoice_type = self._normalize_invoice_type(invoice_type)
        if normalized_month or normalized_invoice_type is not None:
            repository_rows = self._list_repository_invoices(
                month=normalized_month or "all",
                invoice_type=normalized_invoice_type,
            )
            if repository_rows is not None:
                return repository_rows
        invoices = list(self._invoices_by_id.values())
        if normalized_month and normalized_month != "all":
            invoices = [
                invoice
                for invoice in invoices
                if invoice.invoice_date and invoice.invoice_date.startswith(normalized_month[:7])
            ]
        if normalized_invoice_type is not None:
            invoices = [invoice for invoice in invoices if invoice.invoice_type == normalized_invoice_type]
        return invoices

    def get_invoice(self, invoice_id: str) -> Invoice:
        if invoice_id in self._invoices_by_id:
            return self._invoices_by_id[invoice_id]
        getter = getattr(self._fact_repository, "get_invoice", None)
        if callable(getter):
            invoice = getter(invoice_id)
            if isinstance(invoice, Invoice):
                return invoice
        raise KeyError(invoice_id)

    def list_counterparties(self) -> list[Counterparty]:
        return list(self._counterparties_by_normalized_name.values())

    def find_counterparty_by_name(
        self,
        name: str,
        *,
        create_if_missing: bool = False,
    ) -> Counterparty | None:
        normalized_name = normalize_name(name)
        counterparty = self._counterparties_by_normalized_name.get(normalized_name)
        if counterparty is None and create_if_missing:
            counterparty = self._get_or_create_counterparty(name)
        return counterparty

    def list_transactions(self, *, month: str | None = None) -> list[BankTransaction]:
        normalized_month = str(month).strip() if month not in (None, "") else ""
        if normalized_month:
            repository_rows = self._list_repository_transactions(month=normalized_month)
            if repository_rows is not None:
                return repository_rows
            if normalized_month != "all":
                return [
                    transaction
                    for transaction in self._transactions_by_id.values()
                    if transaction.txn_date and transaction.txn_date.startswith(normalized_month[:7])
                ]
        return list(self._transactions_by_id.values())

    def get_transaction(self, transaction_id: str) -> BankTransaction:
        if transaction_id in self._transactions_by_id:
            return self._transactions_by_id[transaction_id]
        for method_name in ("get_transaction", "get_bank_transaction"):
            getter = getattr(self._fact_repository, method_name, None)
            if not callable(getter):
                continue
            transaction = getter(transaction_id)
            if isinstance(transaction, BankTransaction):
                return transaction
        raise KeyError(transaction_id)

    def bank_transaction_matches_strict_statement_evidence(
        self,
        *,
        transaction_id: str,
        normalized: dict[str, Any],
    ) -> bool:
        try:
            transaction = self.get_transaction(transaction_id)
        except KeyError:
            return False
        incoming_identity = self._object_identity_policy.identify_bank_transaction_mapping(
            normalized
        )
        existing_identity = self._object_identity_policy.identify_bank_transaction(
            transaction
        )
        required_components = ("account_no", "trade_time", "direction", "amount")
        incoming_components = tuple(
            incoming_identity.components.get(field_name)
            for field_name in required_components
        )
        existing_components = tuple(
            existing_identity.components.get(field_name)
            for field_name in required_components
        )
        incoming_balance = self._parse_decimal(normalized.get("balance"))
        existing_balance = self._parse_decimal(transaction.balance)
        incoming_currency = self._canonical_currency(normalized.get("currency"))
        existing_currency = self._canonical_currency(transaction.currency)
        return (
            all(incoming_components)
            and all(existing_components)
            and incoming_components == existing_components
            and incoming_balance is not None
            and incoming_balance == existing_balance
            and incoming_currency is not None
            and incoming_currency == existing_currency
        )

    def list_transactions_by_ids(self, transaction_ids: list[str]) -> list[BankTransaction]:
        normalized_ids = list(
            dict.fromkeys(
                str(transaction_id).strip()
                for transaction_id in list(transaction_ids or [])
                if str(transaction_id).strip()
            )
        )
        if not normalized_ids:
            return []
        transactions_by_id = {
            transaction_id: self._transactions_by_id[transaction_id]
            for transaction_id in normalized_ids
            if transaction_id in self._transactions_by_id
        }
        missing_ids = [transaction_id for transaction_id in normalized_ids if transaction_id not in transactions_by_id]
        list_by_ids = getattr(self._fact_repository, "list_bank_transactions_by_ids", None)
        if missing_ids and callable(list_by_ids):
            for transaction in list(list_by_ids(missing_ids) or []):
                if not isinstance(transaction, BankTransaction):
                    continue
                transaction_id = str(transaction.id or "").strip()
                if transaction_id:
                    transactions_by_id[transaction_id] = transaction
        return [transactions_by_id[transaction_id] for transaction_id in normalized_ids if transaction_id in transactions_by_id]

    def _list_repository_invoices(
        self,
        *,
        month: str,
        invoice_type: InvoiceType | None = None,
    ) -> list[Invoice] | None:
        list_page = getattr(self._fact_repository, "list_invoices_page", None)
        if not callable(list_page):
            return None
        page = 1
        page_size = 500
        rows: list[Invoice] = []
        query_month = None if month == "all" else month[:7]
        while True:
            page_rows, total = list_page(
                page=page,
                page_size=page_size,
                month=query_month,
                invoice_type=invoice_type.value if invoice_type is not None else None,
            )
            typed_rows = [row for row in list(page_rows or []) if isinstance(row, Invoice)]
            if invoice_type is not None:
                typed_rows = [row for row in typed_rows if row.invoice_type == invoice_type]
            rows.extend(typed_rows)
            if len(rows) >= int(total or 0) or len(page_rows or []) < page_size:
                break
            page += 1
        return rows

    @staticmethod
    def _normalize_invoice_type(value: InvoiceType | str | None) -> InvoiceType | None:
        if value in (None, ""):
            return None
        if isinstance(value, InvoiceType):
            return value
        return InvoiceType(str(value))

    def _list_repository_transactions(self, *, month: str) -> list[BankTransaction] | None:
        list_page = getattr(self._fact_repository, "list_bank_transactions_page", None)
        if not callable(list_page):
            return None
        date_from: str | None = None
        date_to: str | None = None
        if month != "all":
            month_range = _month_date_range(month)
            if month_range is not None:
                date_from, date_to = month_range
        page = 1
        page_size = 500
        rows: list[BankTransaction] = []
        while True:
            page_rows, total = list_page(page=page, page_size=page_size, date_from=date_from, date_to=date_to)
            typed_rows = [row for row in list(page_rows or []) if isinstance(row, BankTransaction)]
            rows.extend(typed_rows)
            if len(rows) >= int(total or 0) or len(page_rows or []) < page_size:
                break
            page += 1
        return rows

    def _find_invoice_by_identity(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> Invoice | None:
        if source_unique_key and source_unique_key in self._invoice_unique_index:
            return self._invoices_by_id[self._invoice_unique_index[source_unique_key]]
        if not source_unique_key and data_fingerprint and data_fingerprint in self._invoice_fingerprint_index:
            return self._invoices_by_id[self._invoice_fingerprint_index[data_fingerprint]]
        cached = self._find_cached_invoice_identity(
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
        )
        if self._invoice_identity_cache is not None:
            return cached
        finder = getattr(self._fact_repository, "find_invoice_identity", None)
        if not callable(finder):
            return None
        invoice = finder(
            source_unique_key=str(source_unique_key) if source_unique_key else None,
            data_fingerprint=str(data_fingerprint) if not source_unique_key and data_fingerprint else None,
        )
        return invoice if isinstance(invoice, Invoice) else None

    def _find_invoices_by_identity(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> list[Invoice]:
        matches: list[Invoice] = []
        seen_ids: set[str] = set()

        def add(invoice: Invoice | None) -> None:
            if invoice is None or invoice.id in seen_ids:
                return
            seen_ids.add(invoice.id)
            matches.append(invoice)

        if source_unique_key:
            normalized_key = str(source_unique_key)
            for invoice in self._invoices_by_id.values():
                if normalized_key in {
                    str(getattr(invoice, "source_unique_key", "") or ""),
                    str(getattr(invoice, "digital_invoice_no", "") or ""),
                }:
                    add(invoice)
        elif data_fingerprint:
            normalized_fingerprint = str(data_fingerprint)
            for invoice in self._invoices_by_id.values():
                if str(getattr(invoice, "data_fingerprint", "") or "") == normalized_fingerprint:
                    add(invoice)

        if self._invoice_identity_cache is not None:
            add(
                self._find_cached_invoice_identity(
                    source_unique_key=source_unique_key,
                    data_fingerprint=data_fingerprint,
                )
            )
            return matches

        finder_many = getattr(self._fact_repository, "find_invoices_by_identity", None)
        if callable(finder_many):
            for invoice in list(
                finder_many(
                    canonical_key=str(source_unique_key) if source_unique_key else None,
                    suspected_key=str(data_fingerprint) if not source_unique_key and data_fingerprint else None,
                )
                or []
            ):
                if isinstance(invoice, Invoice):
                    add(invoice)
            return matches

        finder = getattr(self._fact_repository, "find_invoice_identity", None)
        if callable(finder):
            invoice = finder(
                source_unique_key=str(source_unique_key) if source_unique_key else None,
                data_fingerprint=str(data_fingerprint) if not source_unique_key and data_fingerprint else None,
            )
            if isinstance(invoice, Invoice):
                add(invoice)
        return matches

    @contextmanager
    def _invoice_identity_cache_for(
        self,
        normalized_rows: list[dict[str, Any]],
        *,
        enabled: bool = True,
    ) -> Iterator[None]:
        previous_cache = self._invoice_identity_cache
        if not enabled:
            yield
            return
        self._invoice_identity_cache = self._build_invoice_identity_cache(normalized_rows)
        try:
            yield
        finally:
            self._invoice_identity_cache = previous_cache

    def _build_invoice_identity_cache(self, normalized_rows: list[dict[str, Any]]) -> dict[tuple[str, str], Invoice]:
        canonical_keys = sorted(
            {
                str(row.get("source_unique_key") or "").strip()
                for row in normalized_rows
                if str(row.get("source_unique_key") or "").strip()
            }
        )
        suspected_keys = sorted(
            {
                str(row.get("data_fingerprint") or "").strip()
                for row in normalized_rows
                if not str(row.get("source_unique_key") or "").strip()
                and str(row.get("data_fingerprint") or "").strip()
            }
        )
        cache: dict[tuple[str, str], Invoice] = {}
        finder_many = getattr(self._fact_repository, "find_invoices_by_identity_keys", None)
        if callable(finder_many) and (canonical_keys or suspected_keys):
            for invoice in list(finder_many(canonical_keys=canonical_keys, suspected_keys=suspected_keys) or []):
                if isinstance(invoice, Invoice):
                    self._add_invoice_to_identity_cache(cache, invoice)
        for invoice in self._invoices_by_id.values():
            self._add_invoice_to_identity_cache(cache, invoice)
        return cache

    def _add_invoice_to_identity_cache(self, cache: dict[tuple[str, str], Invoice], invoice: Invoice) -> None:
        for key_type, value in (
            ("canonical", getattr(invoice, "source_unique_key", None)),
            ("canonical", getattr(invoice, "digital_invoice_no", None)),
            ("suspected", getattr(invoice, "data_fingerprint", None)),
        ):
            text = str(value or "").strip()
            if text:
                cache.setdefault((key_type, text), invoice)

    def _find_cached_invoice_identity(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> Invoice | None:
        cache = self._invoice_identity_cache
        if cache is None:
            return None
        if source_unique_key:
            return cache.get(("canonical", str(source_unique_key)))
        if data_fingerprint:
            return cache.get(("suspected", str(data_fingerprint)))
        return None

    def _find_transaction_by_identity(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None = None,
    ) -> BankTransaction | None:
        if source_unique_key and source_unique_key in self._transaction_unique_index:
            return self._transactions_by_id[self._transaction_unique_index[source_unique_key]]
        if data_fingerprint and data_fingerprint in self._transaction_fingerprint_index:
            return self._transactions_by_id[self._transaction_fingerprint_index[data_fingerprint]]
        cached = self._find_cached_transaction_identities(
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
        )
        if self._transaction_identity_cache is not None:
            return cached[0] if cached else None
        identity_finder = getattr(self._fact_repository, "find_bank_transaction_by_identity", None)
        if callable(identity_finder):
            transaction = identity_finder(
                canonical_key=str(source_unique_key) if source_unique_key else None,
                suspected_key=str(data_fingerprint) if not source_unique_key and data_fingerprint else None,
            )
            return transaction if isinstance(transaction, BankTransaction) else None
        finder = getattr(self._fact_repository, "find_transaction_identity", None)
        if not callable(finder) or not source_unique_key:
            return None
        transaction = finder(source_unique_key=str(source_unique_key))
        return transaction if isinstance(transaction, BankTransaction) else None

    def _find_transactions_by_identity(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> list[BankTransaction]:
        matches: list[BankTransaction] = []
        seen_ids: set[str] = set()

        def add(transaction: BankTransaction | None) -> None:
            if transaction is None or transaction.id in seen_ids:
                return
            seen_ids.add(transaction.id)
            matches.append(transaction)

        for transaction in self._transactions_by_id.values():
            if source_unique_key and str(transaction.source_unique_key or "") == str(source_unique_key):
                add(transaction)
            elif data_fingerprint and str(transaction.data_fingerprint or "") == str(data_fingerprint):
                add(transaction)

        if self._transaction_identity_cache is not None:
            for transaction in self._find_cached_transaction_identities(
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
            ):
                add(transaction)
            return matches

        finder_many = getattr(self._fact_repository, "find_bank_transactions_by_identity", None)
        if callable(finder_many):
            for transaction in list(
                finder_many(
                    canonical_key=str(source_unique_key) if source_unique_key else None,
                    suspected_key=str(data_fingerprint) if not source_unique_key and data_fingerprint else None,
                )
                or []
            ):
                if isinstance(transaction, BankTransaction):
                    add(transaction)
            return matches

        add(
            self._find_transaction_by_identity(
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
            )
        )
        return matches

    @contextmanager
    def _transaction_identity_cache_for(
        self,
        normalized_rows: list[dict[str, Any]],
        *,
        enabled: bool = True,
    ) -> Iterator[None]:
        previous_cache = self._transaction_identity_cache
        if not enabled:
            yield
            return
        self._transaction_identity_cache = self._build_transaction_identity_cache(normalized_rows)
        try:
            yield
        finally:
            self._transaction_identity_cache = previous_cache

    def _build_transaction_identity_cache(
        self,
        normalized_rows: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[BankTransaction]]:
        canonical_keys = sorted(
            {
                str(row.get("source_unique_key") or "").strip()
                for row in normalized_rows
                if str(row.get("source_unique_key") or "").strip()
            }
        )
        suspected_keys = sorted(
            {
                str(row.get("data_fingerprint") or "").strip()
                for row in normalized_rows
                if str(row.get("data_fingerprint") or "").strip()
            }
        )
        cache: dict[tuple[str, str], list[BankTransaction]] = {}
        finder_many = getattr(self._fact_repository, "find_bank_transactions_by_identity_keys", None)
        if callable(finder_many) and (canonical_keys or suspected_keys):
            for transaction in list(
                finder_many(canonical_keys=canonical_keys, suspected_keys=suspected_keys) or []
            ):
                if isinstance(transaction, BankTransaction):
                    self._add_transaction_to_identity_cache(cache, transaction)
        for transaction in self._transactions_by_id.values():
            self._add_transaction_to_identity_cache(cache, transaction)
        return cache

    @staticmethod
    def _add_transaction_to_identity_cache(
        cache: dict[tuple[str, str], list[BankTransaction]],
        transaction: BankTransaction,
    ) -> None:
        for key_type, value in (
            ("canonical", getattr(transaction, "source_unique_key", None)),
            ("suspected", getattr(transaction, "data_fingerprint", None)),
        ):
            text = str(value or "").strip()
            if not text:
                continue
            matches = cache.setdefault((key_type, text), [])
            if all(existing.id != transaction.id for existing in matches):
                matches.append(transaction)

    def _find_cached_transaction_identities(
        self,
        *,
        source_unique_key: str | None,
        data_fingerprint: str | None,
    ) -> list[BankTransaction]:
        cache = self._transaction_identity_cache
        if cache is None:
            return []
        if source_unique_key:
            return list(cache.get(("canonical", str(source_unique_key)), []))
        if data_fingerprint:
            return list(cache.get(("suspected", str(data_fingerprint)), []))
        return []

    def _ensure_invoice_loaded(self, invoice_id: str | None) -> Invoice | None:
        normalized_invoice_id = str(invoice_id or "").strip()
        if not normalized_invoice_id:
            return None
        invoice = self._invoices_by_id.get(normalized_invoice_id)
        if invoice is not None:
            return invoice
        loader = getattr(self._fact_repository, "get_invoice", None)
        if not callable(loader):
            return None
        loaded = loader(normalized_invoice_id)
        if isinstance(loaded, Invoice):
            self._register_invoice(loaded)
            return loaded
        return None

    def current_import_decision_for_normalized_row(
        self,
        *,
        batch_type: BatchType,
        normalized: dict[str, Any],
    ) -> tuple[ImportDecision | None, str | None, str | None]:
        source_unique_key = normalized.get("source_unique_key")
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            decision = self._dedup_decision_service.decide_invoice_import(normalized)
        else:
            decision = self._dedup_decision_service.decide_bank_transaction_import(normalized)
        return ImportDecision(decision.decision), decision.linked_object_type, decision.linked_object_id

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        return self._dedup_decision_service.canonical_invoice_key_exists(canonical_key)

    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        return self._object_identity_repository.find_invoice_by_identity(
            canonical_key=canonical_key,
            suspected_key=suspected_key,
        )

    def find_invoices_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[Invoice]:
        return self._object_identity_repository.find_invoices_by_identity(
            canonical_key=canonical_key,
            suspected_key=suspected_key,
        )

    def has_imported_records(self) -> bool:
        return bool(self._invoices_by_id or self._transactions_by_id)

    def upsert_etc_invoice(self, etc_invoice: Any) -> EtcInvoiceUpsertResult:
        normalized = self._normalize_etc_invoice(etc_invoice)
        decision = self._dedup_decision_service.decide_invoice_import(normalized)
        linked_invoice_id = decision.linked_object_id

        if linked_invoice_id is not None:
            invoice = self._ensure_invoice_loaded(linked_invoice_id)
            if invoice is None and isinstance(decision.matched_object, Invoice):
                invoice = decision.matched_object
                self._register_invoice(invoice)
            if invoice is None:
                raise KeyError(linked_invoice_id)
            previous_state = self._etc_invoice_merge_state(invoice)
            self._merge_invoice_from_etc_normalized(invoice, normalized)
            return EtcInvoiceUpsertResult(
                invoice=invoice,
                changed=self._etc_invoice_merge_state(invoice) != previous_state,
            )

        return EtcInvoiceUpsertResult(invoice=None, changed=False)

    def upsert_oa_attachment_invoice(
        self,
        attachment_invoice: dict[str, Any],
        *,
        oa_form_id: str | None = None,
        oa_row_id: str | None = None,
        source_workbench_row_id: str | None = None,
        allow_create: bool = False,
    ) -> Invoice | None:
        normalized = self._normalize_oa_attachment_invoice(
            attachment_invoice,
            oa_form_id=oa_form_id,
            oa_row_id=oa_row_id,
            source_workbench_row_id=source_workbench_row_id,
        )
        if normalized is None:
            return None
        decision = self._dedup_decision_service.decide_oa_attachment_invoice_import(normalized)
        linked_invoice_id = decision.linked_object_id

        if linked_invoice_id is not None:
            invoice = self._ensure_invoice_loaded(linked_invoice_id)
            if invoice is None and isinstance(decision.matched_object, Invoice):
                invoice = decision.matched_object
                self._register_invoice(invoice)
            if invoice is None:
                raise KeyError(linked_invoice_id)
            self._merge_invoice_from_oa_attachment_normalized(invoice, normalized)
            return invoice

        if not allow_create or not decision.identity.canonical_key:
            return None
        normalized["source_unique_key"] = decision.identity.canonical_key
        normalized["data_fingerprint"] = decision.identity.suspected_key
        invoice = self._build_oa_attachment_invoice_from_normalized(normalized)
        self._register_invoice(invoice)
        return invoice

    def _preview_invoice_row(
        self,
        *,
        batch_id: str,
        row_no: int,
        batch_type: BatchType,
        raw_row: dict[str, Any],
    ) -> tuple[dict[str, Any], ImportedBatchRowResult]:
        normalized, errors = self._normalize_invoice_row(batch_type=batch_type, raw_row=raw_row)
        return normalized, self._preview_invoice_row_from_normalized(
            batch_id=batch_id,
            row_no=row_no,
            raw_row=raw_row,
            normalized=normalized,
            errors=errors,
        )

    def _normalize_invoice_row(
        self,
        *,
        batch_type: BatchType,
        raw_row: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        normalized_name = normalize_name(raw_row.get("counterparty_name", ""))
        normalized: dict[str, Any] = {
            "counterparty_name": raw_row.get("counterparty_name", ""),
            "normalized_counterparty_name": normalized_name,
            "invoice_code": self._string_or_none(raw_row.get("invoice_code")),
            "invoice_no": self._string_or_none(raw_row.get("invoice_no")),
            "digital_invoice_no": self._string_or_none(raw_row.get("digital_invoice_no")),
            "invoice_status_from_source": self._string_or_none(raw_row.get("invoice_status_from_source")),
            "seller_tax_no": self._string_or_none(raw_row.get("seller_tax_no")),
            "seller_name": self._string_or_none(raw_row.get("seller_name")),
            "buyer_tax_no": self._string_or_none(raw_row.get("buyer_tax_no")),
            "buyer_name": self._string_or_none(raw_row.get("buyer_name")),
            "tax_rate": self._string_or_none(raw_row.get("tax_rate")),
            "tax_classification_code": self._string_or_none(raw_row.get("tax_classification_code")),
            "specific_business_type": self._string_or_none(raw_row.get("specific_business_type")),
            "taxable_item_name": self._string_or_none(raw_row.get("taxable_item_name")),
            "specification_model": self._string_or_none(raw_row.get("specification_model")),
            "unit": self._string_or_none(raw_row.get("unit")),
            "invoice_source": self._string_or_none(raw_row.get("invoice_source")),
            "invoice_kind": self._string_or_none(raw_row.get("invoice_kind")),
            "is_positive_invoice": self._string_or_none(raw_row.get("is_positive_invoice")),
            "risk_level": self._string_or_none(raw_row.get("risk_level")),
            "issuer": self._string_or_none(raw_row.get("issuer")),
            "remark": self._string_or_none(raw_row.get("remark")),
            "project_id": self._string_or_none(raw_row.get("project_id")),
            "oa_form_id": self._string_or_none(raw_row.get("oa_form_id")),
            "pending_invoice_request_key": self._string_or_none(raw_row.get("pending_invoice_request_key")),
            "pending_invoice_bank_transaction_id": self._string_or_none(raw_row.get("pending_invoice_bank_transaction_id")),
            "tags": self._normalize_tags(raw_row.get("tags")),
        }
        errors: list[str] = []

        if not normalized_name:
            errors.append("counterparty_name is required")

        invoice_date = self._parse_date(raw_row.get("invoice_date"))
        if invoice_date is None:
            errors.append("invoice_date is invalid")
        else:
            normalized["invoice_date"] = invoice_date

        amount = self._parse_decimal(raw_row.get("amount"))
        if amount is None:
            errors.append("amount is invalid")
        else:
            normalized["amount"] = self._format_decimal(amount)
            normalized["signed_amount"] = self._format_decimal(amount)

        for source_key in ("tax_amount", "total_with_tax", "quantity", "unit_price"):
            parsed_value = self._parse_decimal(raw_row.get(source_key))
            if parsed_value is not None:
                normalized[source_key] = self._format_decimal(parsed_value)

        identity = self._object_identity_policy.identify_invoice_mapping(normalized)
        source_unique_key = identity.canonical_key
        data_fingerprint = identity.suspected_key
        normalized["source_unique_key"] = source_unique_key
        normalized["data_fingerprint"] = data_fingerprint
        normalized["invoice_type"] = InvoiceType.OUTPUT.value if batch_type == BatchType.OUTPUT_INVOICE else InvoiceType.INPUT.value
        if self._row_indicates_etc(normalized):
            self._append_unique_tag(normalized["tags"], "ETC")
        return normalized, errors

    def _preview_invoice_row_from_normalized(
        self,
        *,
        batch_id: str,
        row_no: int,
        raw_row: dict[str, Any],
        normalized: dict[str, Any],
        errors: list[str],
    ) -> ImportedBatchRowResult:
        source_unique_key = normalized.get("source_unique_key")
        data_fingerprint = normalized.get("data_fingerprint")
        if errors:
            return ImportedBatchRowResult(
                id=self._row_id(batch_id, row_no),
                batch_id=batch_id,
                row_no=row_no,
                source_record_type="invoice",
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
                decision=ImportDecision.ERROR,
                decision_reason="; ".join(errors),
                raw_payload=dict(raw_row),
            )

        dedup_decision = self._dedup_decision_service.decide_invoice_import(normalized)
        linked_invoice_id = dedup_decision.linked_object_id
        decision = ImportDecision(dedup_decision.decision)
        reason = dedup_decision.decision_reason
        existing = dedup_decision.matched_object if isinstance(dedup_decision.matched_object, Invoice) else None
        if source_unique_key and existing is not None:
            normalized["previous_invoice_status_from_source"] = existing.invoice_status_from_source
            normalized["previous_source_batch_id"] = existing.source_batch_id

        return ImportedBatchRowResult(
            id=self._row_id(batch_id, row_no),
            batch_id=batch_id,
            row_no=row_no,
            source_record_type="invoice",
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
            decision=decision,
            decision_reason=reason,
            linked_object_type="invoice" if linked_invoice_id else None,
            linked_object_id=linked_invoice_id,
            raw_payload=dict(raw_row),
        )

    def _preview_transaction_row(
        self,
        *,
        batch_id: str,
        row_no: int,
        raw_row: dict[str, Any],
    ) -> tuple[dict[str, Any], ImportedBatchRowResult]:
        normalized, errors = self._normalize_transaction_row(raw_row)
        return normalized, self._preview_transaction_row_from_normalized(
            batch_id=batch_id,
            row_no=row_no,
            raw_row=raw_row,
            normalized=normalized,
            errors=errors,
        )

    def _normalize_transaction_row(
        self,
        raw_row: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        normalized_name = normalize_name(raw_row.get("counterparty_name", ""))
        normalized: dict[str, Any] = {
            "account_no": self._string_or_none(raw_row.get("account_no")),
            "counterparty_name_raw": raw_row.get("counterparty_name", ""),
            "normalized_counterparty_name": normalized_name,
            "summary": self._string_or_none(raw_row.get("summary")),
            "bank_serial_no": self._string_or_none(raw_row.get("bank_serial_no")),
            "voucher_no": self._string_or_none(raw_row.get("voucher_no")),
            "enterprise_serial_no": self._string_or_none(raw_row.get("enterprise_serial_no")),
            "trade_time": self._string_or_none(raw_row.get("trade_time")),
            "pay_receive_time": self._string_or_none(raw_row.get("pay_receive_time")),
            "account_name": self._string_or_none(raw_row.get("account_name")),
            "currency": self._string_or_none(raw_row.get("currency")) or "CNY",
            "counterparty_account_no": self._string_or_none(raw_row.get("counterparty_account_no")),
            "counterparty_bank_name": self._string_or_none(raw_row.get("counterparty_bank_name")),
            "remark": self._string_or_none(raw_row.get("remark")),
            "bank_text_fields": self._normalize_bank_text_fields(raw_row),
            "account_detail_no": self._string_or_none(raw_row.get("account_detail_no")),
            "voucher_kind": self._string_or_none(raw_row.get("voucher_kind")),
            "project_id": self._string_or_none(raw_row.get("project_id")),
            "imported_bank_name": self._string_or_none(raw_row.get("selected_bank_name")),
            "imported_bank_last4": self._string_or_none(raw_row.get("selected_bank_last4")),
        }
        errors: list[str] = []

        account_no = normalized["account_no"]
        if not account_no:
            errors.append("account_no is required")
        if not normalized_name:
            errors.append("counterparty_name is required")

        txn_date = self._parse_date(raw_row.get("txn_date"))
        if txn_date is not None:
            normalized["txn_date"] = txn_date

        booked_date = self._parse_date(raw_row.get("booked_date"))
        if booked_date is not None:
            normalized["booked_date"] = booked_date

        debit_amount = self._parse_decimal(raw_row.get("debit_amount"))
        credit_amount = self._parse_decimal(raw_row.get("credit_amount"))
        balance = self._parse_decimal(raw_row.get("balance"))
        if balance is not None:
            normalized["balance"] = self._format_decimal(balance)
        direction: TransactionDirection | None = None
        amount: Decimal | None = None
        signed_amount: Decimal | None = None
        if debit_amount is not None and debit_amount > ZERO and (credit_amount is None or credit_amount == ZERO):
            direction = TransactionDirection.OUTFLOW
            amount = debit_amount
            signed_amount = -debit_amount
        elif credit_amount is not None and credit_amount > ZERO and (debit_amount is None or debit_amount == ZERO):
            direction = TransactionDirection.INFLOW
            amount = credit_amount
            signed_amount = credit_amount
        else:
            errors.append("exactly one of debit_amount or credit_amount must be a positive amount")

        if direction:
            normalized["txn_direction"] = direction.value
        if amount is not None:
            normalized["amount"] = self._format_decimal(amount)
        if signed_amount is not None:
            normalized["signed_amount"] = self._format_decimal(signed_amount)

        identity = self._object_identity_policy.identify_bank_transaction_mapping(normalized)
        if not txn_date and identity.components.get("trade_time"):
            normalized["txn_date"] = identity.components["trade_time"][:10]
        source_unique_key = identity.canonical_key
        data_fingerprint = identity.suspected_key
        normalized["source_unique_key"] = source_unique_key
        normalized["data_fingerprint"] = data_fingerprint

        return normalized, errors

    def _preview_transaction_row_from_normalized(
        self,
        *,
        batch_id: str,
        row_no: int,
        raw_row: dict[str, Any],
        normalized: dict[str, Any],
        errors: list[str],
    ) -> ImportedBatchRowResult:
        identity = self._object_identity_policy.identify_bank_transaction_mapping(normalized)
        source_unique_key = identity.canonical_key
        data_fingerprint = identity.suspected_key
        row_display_fields = self._transaction_row_result_display_fields(normalized, identity)

        if errors:
            return ImportedBatchRowResult(
                id=self._row_id(batch_id, row_no),
                batch_id=batch_id,
                row_no=row_no,
                source_record_type="bank_transaction",
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
                decision=ImportDecision.ERROR,
                decision_reason="; ".join(errors),
                raw_payload=dict(raw_row),
                **row_display_fields,
            )

        dedup_decision = self._dedup_decision_service.decide_bank_transaction_import(normalized)
        identity = dedup_decision.identity
        source_unique_key = identity.canonical_key
        data_fingerprint = identity.suspected_key
        normalized["source_unique_key"] = source_unique_key
        normalized["data_fingerprint"] = data_fingerprint
        row_display_fields = self._transaction_row_result_display_fields(normalized, identity)
        linked_txn_id = dedup_decision.linked_object_id
        decision = ImportDecision(dedup_decision.decision)
        reason = dedup_decision.decision_reason

        return ImportedBatchRowResult(
            id=self._row_id(batch_id, row_no),
            batch_id=batch_id,
            row_no=row_no,
            source_record_type="bank_transaction",
            source_unique_key=source_unique_key,
            data_fingerprint=data_fingerprint,
            decision=decision,
            decision_reason=reason,
            linked_object_type="bank_transaction" if linked_txn_id else None,
            linked_object_id=linked_txn_id,
            raw_payload=dict(raw_row),
            **row_display_fields,
        )

    def _persist_created_row(
        self,
        batch_type: BatchType,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            invoice = self._build_invoice_from_normalized(batch_type, row_result.batch_id, normalized)
            self._link_submitted_etc_metadata_if_present(invoice, normalized)
            self._register_invoice(invoice)
            row_result.linked_object_type = "invoice"
            row_result.linked_object_id = invoice.id
        else:
            transaction = self._build_transaction_from_normalized(row_result.batch_id, normalized)
            self._register_transaction(transaction)
            row_result.linked_object_type = "bank_transaction"
            row_result.linked_object_id = transaction.id

    def _persist_updated_row(
        self,
        batch_type: BatchType,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        if batch_type not in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            return
        invoice = self._ensure_invoice_loaded(row_result.linked_object_id)
        if invoice is None:
            return
        invoice.invoice_status_from_source = normalized.get("invoice_status_from_source")
        invoice.source_batch_id = row_result.batch_id
        self._merge_invoice_from_normalized(invoice, row_result.batch_id, normalized)
        self._link_submitted_etc_metadata_if_present(invoice, normalized)

    def _persist_duplicate_row(
        self,
        batch_type: BatchType,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        if batch_type not in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            return
        if row_result.linked_object_type != "invoice" or not row_result.linked_object_id:
            return
        invoice = self._ensure_invoice_loaded(row_result.linked_object_id)
        if invoice is None:
            return
        self._merge_invoice_from_normalized(invoice, row_result.batch_id, normalized)
        self._link_submitted_etc_metadata_if_present(invoice, normalized)

    def _build_invoice_from_normalized(
        self,
        batch_type: BatchType,
        batch_id: str,
        normalized: dict[str, Any],
    ) -> Invoice:
        invoice_type = InvoiceType.OUTPUT if batch_type == BatchType.OUTPUT_INVOICE else InvoiceType.INPUT
        counterparty = self._get_or_create_counterparty(normalized["counterparty_name"])
        invoice_id = self._next_invoice_id()
        amount = Decimal(normalized["amount"])
        return Invoice(
            id=invoice_id,
            invoice_type=invoice_type,
            invoice_no=normalized.get("digital_invoice_no") or normalized.get("invoice_no") or f"generated-{invoice_id.rsplit('_', 1)[-1]}",
            invoice_code=normalized.get("invoice_code"),
            digital_invoice_no=normalized.get("digital_invoice_no"),
            counterparty=counterparty,
            amount=amount,
            signed_amount=Decimal(normalized["signed_amount"]),
            invoice_date=normalized["invoice_date"],
            invoice_status_from_source=normalized.get("invoice_status_from_source"),
            seller_tax_no=normalized.get("seller_tax_no"),
            seller_name=normalized.get("seller_name"),
            buyer_tax_no=normalized.get("buyer_tax_no"),
            buyer_name=normalized.get("buyer_name"),
            tax_rate=normalized.get("tax_rate"),
            tax_amount=Decimal(normalized["tax_amount"]) if normalized.get("tax_amount") else None,
            total_with_tax=Decimal(normalized["total_with_tax"]) if normalized.get("total_with_tax") else None,
            tax_classification_code=normalized.get("tax_classification_code"),
            specific_business_type=normalized.get("specific_business_type"),
            taxable_item_name=normalized.get("taxable_item_name"),
            specification_model=normalized.get("specification_model"),
            unit=normalized.get("unit"),
            quantity=Decimal(normalized["quantity"]) if normalized.get("quantity") else None,
            unit_price=Decimal(normalized["unit_price"]) if normalized.get("unit_price") else None,
            invoice_source=normalized.get("invoice_source"),
            invoice_kind=normalized.get("invoice_kind"),
            is_positive_invoice=normalized.get("is_positive_invoice"),
            risk_level=normalized.get("risk_level"),
            issuer=normalized.get("issuer"),
            remark=normalized.get("remark"),
            project_id=normalized.get("project_id"),
            source_unique_key=normalized.get("source_unique_key"),
            data_fingerprint=normalized.get("data_fingerprint"),
            source_batch_id=batch_id,
            oa_form_id=normalized.get("oa_form_id"),
            tags=list(normalized.get("tags") or []),
            source_links=[self._build_invoice_source_link(batch_id, normalized)],
        )

    def _build_transaction_from_normalized(self, batch_id: str, normalized: dict[str, Any]) -> BankTransaction:
        transaction_id = self._next_transaction_id()
        counterparty = self._get_or_create_counterparty(normalized["counterparty_name_raw"])
        return BankTransaction(
            id=transaction_id,
            account_no=normalized["account_no"],
            txn_direction=TransactionDirection(normalized["txn_direction"]),
            counterparty_name_raw=normalized["counterparty_name_raw"],
            amount=Decimal(normalized["amount"]),
            signed_amount=Decimal(normalized["signed_amount"]),
            bank_serial_no=normalized.get("bank_serial_no"),
            source_unique_key=normalized.get("source_unique_key"),
            data_fingerprint=normalized.get("data_fingerprint"),
            txn_date=normalized["txn_date"],
            trade_time=normalized.get("trade_time"),
            pay_receive_time=normalized.get("pay_receive_time"),
            counterparty_id=counterparty.id,
            summary=normalized.get("summary"),
            account_name=normalized.get("account_name"),
            balance=Decimal(normalized["balance"]) if normalized.get("balance") else None,
            currency=normalized.get("currency"),
            counterparty_account_no=normalized.get("counterparty_account_no"),
            counterparty_bank_name=normalized.get("counterparty_bank_name"),
            booked_date=normalized.get("booked_date"),
            remark=normalized.get("remark"),
            bank_text_fields=list(normalized.get("bank_text_fields") or []),
            account_detail_no=normalized.get("account_detail_no"),
            enterprise_serial_no=normalized.get("enterprise_serial_no"),
            voucher_kind=normalized.get("voucher_kind"),
            voucher_no=normalized.get("voucher_no"),
            project_id=normalized.get("project_id"),
            source_batch_id=batch_id,
            imported_bank_name=normalized.get("imported_bank_name"),
            imported_bank_last4=normalized.get("imported_bank_last4"),
        )

    def _register_invoice(self, invoice: Invoice) -> None:
        self._ensure_invoice_metadata_fields(invoice)
        if not invoice.source_unique_key:
            invoice.source_unique_key = self._object_identity_policy.identify_invoice(invoice).canonical_key
        self._clear_weak_invoice_fingerprint_when_canonical(invoice)
        self._invoices_by_id[invoice.id] = invoice
        self._get_or_create_counterparty(invoice.counterparty.name, existing=invoice.counterparty)
        if invoice.source_unique_key:
            self._invoice_unique_index[invoice.source_unique_key] = invoice.id
        if invoice.data_fingerprint:
            self._invoice_fingerprint_index[invoice.data_fingerprint] = invoice.id

    def _register_transaction(self, transaction: BankTransaction) -> None:
        self._ensure_transaction_metadata_fields(transaction)
        canonical_key = self._object_identity_policy.identify_bank_transaction(transaction).canonical_key
        position_key = self._object_identity_policy.identify_bank_transaction_position(transaction).canonical_key
        allowed_keys = {key for key in (canonical_key, position_key) if key}
        if transaction.source_unique_key not in allowed_keys and canonical_key:
            transaction.source_unique_key = canonical_key
        self._transactions_by_id[transaction.id] = transaction
        if transaction.source_unique_key:
            self._transaction_unique_index[transaction.source_unique_key] = transaction.id
        if transaction.data_fingerprint:
            self._transaction_fingerprint_index[transaction.data_fingerprint] = transaction.id
        if self._transaction_identity_cache is not None:
            self._add_transaction_to_identity_cache(self._transaction_identity_cache, transaction)

    def _remove_invoice(self, invoice_id: str) -> None:
        invoice = self._invoices_by_id.pop(invoice_id, None)
        if invoice is None:
            return
        if invoice.source_unique_key:
            self._invoice_unique_index.pop(invoice.source_unique_key, None)
        if invoice.data_fingerprint:
            self._invoice_fingerprint_index.pop(invoice.data_fingerprint, None)

    def _remove_transaction(self, transaction_id: str) -> None:
        transaction = self._transactions_by_id.pop(transaction_id, None)
        if transaction is None:
            return
        if transaction.source_unique_key:
            self._transaction_unique_index.pop(transaction.source_unique_key, None)
        if transaction.data_fingerprint:
            self._transaction_fingerprint_index.pop(transaction.data_fingerprint, None)
        if self._transaction_identity_cache is not None:
            for key, matches in list(self._transaction_identity_cache.items()):
                retained = [existing for existing in matches if existing.id != transaction_id]
                if retained:
                    self._transaction_identity_cache[key] = retained
                else:
                    self._transaction_identity_cache.pop(key, None)

    def _get_or_create_counterparty(self, raw_name: str, *, existing: Counterparty | None = None) -> Counterparty:
        normalized_name = normalize_name(raw_name if existing is None else existing.name)
        if normalized_name in self._counterparties_by_normalized_name:
            return self._counterparties_by_normalized_name[normalized_name]
        if existing is not None:
            self._counterparties_by_normalized_name[normalized_name] = existing
            return existing

        self._counterparty_counter += 1
        counterparty = Counterparty(
            id=f"cp_imported_{self._counterparty_counter:04d}",
            name=clean_string(raw_name),
            normalized_name=normalized_name,
            counterparty_type="unknown",
        )
        self._counterparties_by_normalized_name[normalized_name] = counterparty
        return counterparty

    def _build_invoice_unique_key(self, normalized: dict[str, Any]) -> str | None:
        return self._object_identity_policy.identify_invoice_mapping(normalized).canonical_key

    def _normalize_etc_invoice(self, etc_invoice: Any) -> dict[str, Any]:
        invoice_number = self._string_or_none(getattr(etc_invoice, "invoice_number", None))
        seller_name = self._string_or_none(getattr(etc_invoice, "seller_name", None))
        buyer_name = self._string_or_none(getattr(etc_invoice, "buyer_name", None))
        amount_without_tax = self._parse_decimal(getattr(etc_invoice, "amount_without_tax", None))
        total_amount = self._parse_decimal(getattr(etc_invoice, "total_amount", None))
        amount = amount_without_tax if amount_without_tax is not None else total_amount or ZERO
        normalized: dict[str, Any] = {
            "counterparty_name": seller_name or invoice_number or "ETC发票",
            "normalized_counterparty_name": normalize_name(seller_name or invoice_number or "ETC发票"),
            "invoice_no": invoice_number,
            "digital_invoice_no": invoice_number,
            "invoice_date": self._string_or_none(getattr(etc_invoice, "issue_date", None)),
            "amount": self._format_decimal(amount),
            "signed_amount": self._format_decimal(amount),
            "seller_tax_no": self._string_or_none(getattr(etc_invoice, "seller_tax_no", None)),
            "seller_name": seller_name,
            "buyer_tax_no": self._string_or_none(getattr(etc_invoice, "buyer_tax_no", None)),
            "buyer_name": buyer_name,
            "tax_amount": self._format_decimal(self._parse_decimal(getattr(etc_invoice, "tax_amount", None)) or ZERO),
            "total_with_tax": self._format_decimal(total_amount if total_amount is not None else amount),
            "tax_rate": self._string_or_none(getattr(etc_invoice, "tax_rate", None)),
            "invoice_source": "ETC导入",
            "invoice_kind": "ETC发票",
            "tags": ["ETC"],
            "invoice_type": InvoiceType.INPUT.value,
            "etc_invoice_id": self._string_or_none(getattr(etc_invoice, "id", None)),
            "etc_import_batch_id": self._string_or_none(getattr(etc_invoice, "import_batch_id", None)),
            "etc_submission_batch_id": self._string_or_none(getattr(etc_invoice, "current_batch_id", None) or getattr(etc_invoice, "last_batch_id", None)),
            "etc_submission_status": self._string_or_none(getattr(getattr(etc_invoice, "status", None), "value", None) or getattr(etc_invoice, "status", None)),
            "source_batch_id": self._string_or_none(getattr(etc_invoice, "import_batch_id", None)),
            "source_unique_key": None,
            "data_fingerprint": None,
        }
        identity = self._object_identity_policy.identify_etc_invoice_mapping(normalized)
        normalized["source_unique_key"] = identity.canonical_key
        normalized["data_fingerprint"] = identity.suspected_key
        normalized["workbench_visibility"] = (
            "hidden_after_etc_submission"
            if normalized.get("etc_submission_status") == "submitted"
            else "visible"
        )
        return normalized

    def _normalize_oa_attachment_invoice(
        self,
        attachment_invoice: dict[str, Any],
        *,
        oa_form_id: str | None,
        oa_row_id: str | None,
        source_workbench_row_id: str | None,
    ) -> dict[str, Any] | None:
        if not isinstance(attachment_invoice, dict):
            return None
        if not self._is_promotable_oa_attachment_invoice(attachment_invoice):
            return None

        issue_date = self._parse_date(
            attachment_invoice.get("issue_date") or attachment_invoice.get("invoice_date")
        )
        amount = self._parse_decimal(
            attachment_invoice.get("net_amount")
            or attachment_invoice.get("amount")
            or attachment_invoice.get("total_with_tax")
        )
        if issue_date is None or amount is None:
            return None
        tax_amount = self._parse_decimal(attachment_invoice.get("tax_amount"))
        total_with_tax = self._parse_decimal(attachment_invoice.get("total_with_tax")) or amount
        quantity = self._parse_decimal(attachment_invoice.get("quantity"))
        unit_price = self._parse_decimal(attachment_invoice.get("unit_price"))
        invoice_type = self._normalize_invoice_type_value(attachment_invoice.get("invoice_type"))
        seller_name = self._string_or_none(attachment_invoice.get("seller_name"))
        buyer_name = self._string_or_none(attachment_invoice.get("buyer_name"))
        counterparty_name = (
            seller_name
            if invoice_type == InvoiceType.INPUT
            else buyer_name
        ) or seller_name or buyer_name or self._string_or_none(attachment_invoice.get("counterparty_name")) or "OA附件发票"
        raw_invoice_no = self._string_or_none(attachment_invoice.get("invoice_no"))
        raw_digital_invoice_no = self._string_or_none(attachment_invoice.get("digital_invoice_no"))
        if not raw_digital_invoice_no and raw_invoice_no and raw_invoice_no.isdigit() and len(raw_invoice_no) == 20:
            raw_digital_invoice_no = raw_invoice_no
        normalized: dict[str, Any] = {
            "counterparty_name": counterparty_name,
            "normalized_counterparty_name": normalize_name(counterparty_name),
            "invoice_code": self._string_or_none(attachment_invoice.get("invoice_code")),
            "invoice_no": raw_invoice_no,
            "digital_invoice_no": raw_digital_invoice_no,
            "invoice_date": issue_date,
            "amount": self._format_decimal(amount),
            "signed_amount": self._format_decimal(amount),
            "seller_tax_no": self._string_or_none(attachment_invoice.get("seller_tax_no")),
            "seller_name": seller_name,
            "buyer_tax_no": self._string_or_none(attachment_invoice.get("buyer_tax_no")),
            "buyer_name": buyer_name,
            "tax_rate": self._string_or_none(attachment_invoice.get("tax_rate")),
            "tax_amount": self._format_decimal(tax_amount) if tax_amount is not None else None,
            "total_with_tax": self._format_decimal(total_with_tax),
            "tax_classification_code": self._string_or_none(attachment_invoice.get("tax_classification_code")),
            "specific_business_type": self._string_or_none(attachment_invoice.get("specific_business_type")),
            "taxable_item_name": self._string_or_none(attachment_invoice.get("taxable_item_name")),
            "specification_model": self._string_or_none(attachment_invoice.get("specification_model")),
            "unit": self._string_or_none(attachment_invoice.get("unit")),
            "quantity": self._format_decimal(quantity) if quantity is not None else None,
            "unit_price": self._format_decimal(unit_price) if unit_price is not None else None,
            "invoice_source": "OA附件解析",
            "invoice_kind": self._string_or_none(attachment_invoice.get("invoice_kind")),
            "is_positive_invoice": self._string_or_none(attachment_invoice.get("is_positive_invoice")),
            "risk_level": self._string_or_none(attachment_invoice.get("risk_level")),
            "issuer": self._string_or_none(attachment_invoice.get("issuer")),
            "remark": self._string_or_none(attachment_invoice.get("remark")),
            "project_id": self._string_or_none(attachment_invoice.get("project_id")),
            "invoice_type": invoice_type.value,
            "oa_form_id": self._string_or_none(oa_form_id or attachment_invoice.get("oa_form_id") or oa_row_id),
            "derived_from_oa_id": self._string_or_none(oa_row_id or attachment_invoice.get("derived_from_oa_id")),
            "source_workbench_row_id": self._string_or_none(source_workbench_row_id or attachment_invoice.get("source_workbench_row_id")),
            "source_attachment_key": self._string_or_none(attachment_invoice.get("source_attachment_key")),
            "source_attachment_name": self._string_or_none(
                attachment_invoice.get("source_attachment_name")
                or attachment_invoice.get("attachment_name")
                or attachment_invoice.get("fileName")
                or attachment_invoice.get("filename")
            ),
            "source_expense_item_id": self._string_or_none(attachment_invoice.get("source_expense_item_id")),
            "source_expense_row_index": self._string_or_none(attachment_invoice.get("source_expense_row_index")),
            "source_region_key": self._string_or_none(attachment_invoice.get("source_region_key")),
            "evidence_type": self._string_or_none(attachment_invoice.get("evidence_type")),
            "document_kind": self._string_or_none(attachment_invoice.get("document_kind")),
            "source_unique_key": None,
            "data_fingerprint": None,
            "tags": ["OA附件"],
            "workbench_visibility": "visible",
        }
        identity = self._object_identity_policy.identify_oa_attachment_invoice(
            normalized,
            source_row_id=normalized.get("source_workbench_row_id") or normalized.get("source_attachment_key"),
        )
        if identity.canonical_key_kind not in {"digital_invoice_no", "invoice_code_no"} or not identity.canonical_key:
            return None
        normalized["source_unique_key"] = identity.canonical_key
        normalized["data_fingerprint"] = identity.suspected_key
        return normalized

    def _build_oa_attachment_invoice_from_normalized(self, normalized: dict[str, Any]) -> Invoice:
        counterparty = self._get_or_create_counterparty(normalized["counterparty_name"])
        invoice_id = normalized.get("source_workbench_row_id") or self._next_invoice_id()
        amount = Decimal(normalized["amount"])
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType(normalized.get("invoice_type") or InvoiceType.INPUT.value),
            invoice_no=normalized.get("digital_invoice_no") or normalized.get("invoice_no") or invoice_id,
            digital_invoice_no=normalized.get("digital_invoice_no"),
            invoice_code=normalized.get("invoice_code"),
            counterparty=counterparty,
            amount=amount,
            signed_amount=Decimal(normalized["signed_amount"]),
            invoice_date=normalized.get("invoice_date"),
            seller_tax_no=normalized.get("seller_tax_no"),
            seller_name=normalized.get("seller_name"),
            buyer_tax_no=normalized.get("buyer_tax_no"),
            buyer_name=normalized.get("buyer_name"),
            tax_rate=normalized.get("tax_rate"),
            tax_amount=Decimal(normalized["tax_amount"]) if normalized.get("tax_amount") else None,
            total_with_tax=Decimal(normalized["total_with_tax"]) if normalized.get("total_with_tax") else None,
            tax_classification_code=normalized.get("tax_classification_code"),
            specific_business_type=normalized.get("specific_business_type"),
            taxable_item_name=normalized.get("taxable_item_name"),
            specification_model=normalized.get("specification_model"),
            unit=normalized.get("unit"),
            quantity=Decimal(normalized["quantity"]) if normalized.get("quantity") else None,
            unit_price=Decimal(normalized["unit_price"]) if normalized.get("unit_price") else None,
            invoice_source=normalized.get("invoice_source"),
            invoice_kind=normalized.get("invoice_kind"),
            is_positive_invoice=normalized.get("is_positive_invoice"),
            risk_level=normalized.get("risk_level"),
            issuer=normalized.get("issuer"),
            remark=normalized.get("remark"),
            project_id=normalized.get("project_id"),
            source_unique_key=normalized.get("source_unique_key"),
            data_fingerprint=normalized.get("data_fingerprint"),
            oa_form_id=normalized.get("oa_form_id"),
            tags=list(normalized.get("tags") or []),
            source_links=[self._build_oa_attachment_invoice_source_link(normalized)],
            workbench_visibility=normalized.get("workbench_visibility") or "visible",
        )

    def _merge_invoice_from_oa_attachment_normalized(self, invoice: Invoice, normalized: dict[str, Any]) -> None:
        self._ensure_invoice_metadata_fields(invoice)
        for tag in normalized.get("tags") or []:
            self._append_unique_tag(invoice.tags, str(tag))
        self._append_invoice_source_link(invoice, self._build_oa_attachment_invoice_source_link(normalized))
        if not invoice.oa_form_id:
            invoice.oa_form_id = normalized.get("oa_form_id")
        for field_name in (
            "invoice_code",
            "digital_invoice_no",
            "invoice_date",
            "seller_tax_no",
            "seller_name",
            "buyer_tax_no",
            "buyer_name",
            "tax_rate",
            "tax_classification_code",
            "specific_business_type",
            "taxable_item_name",
            "specification_model",
            "unit",
            "invoice_source",
            "invoice_kind",
            "is_positive_invoice",
            "risk_level",
            "issuer",
            "remark",
            "project_id",
        ):
            incoming = normalized.get(field_name)
            if incoming and not getattr(invoice, field_name):
                setattr(invoice, field_name, incoming)
        for field_name in ("tax_amount", "total_with_tax", "quantity", "unit_price"):
            incoming = normalized.get(field_name)
            if incoming and getattr(invoice, field_name) is None:
                setattr(invoice, field_name, Decimal(incoming))
        if not invoice.source_unique_key:
            invoice.source_unique_key = normalized.get("source_unique_key")
            if invoice.source_unique_key:
                self._invoice_unique_index[invoice.source_unique_key] = invoice.id
        self._clear_weak_invoice_fingerprint_when_canonical(invoice)

    def _build_oa_attachment_invoice_source_link(self, normalized: dict[str, Any]) -> dict[str, str]:
        source_link = {
            "source_type": "oa_attachment_invoice",
            "source_id": normalized.get("source_attachment_key")
            or normalized.get("source_workbench_row_id")
            or normalized.get("source_unique_key")
            or "",
            "batch_id": "",
            "created_at": datetime.now(UTC).isoformat(),
        }
        for key in (
            "source_workbench_row_id",
            "derived_from_oa_id",
            "source_attachment_key",
            "source_attachment_name",
            "source_expense_item_id",
            "source_expense_row_index",
            "source_region_key",
            "evidence_type",
            "document_kind",
        ):
            value = str(normalized.get(key) or "").strip()
            if value:
                source_link[key] = value
        return source_link

    def _is_promotable_oa_attachment_invoice(self, attachment_invoice: dict[str, Any]) -> bool:
        evidence_type = str(attachment_invoice.get("evidence_type") or "").strip()
        if evidence_type in {"payment_receipt", "non_tax_receipt"}:
            return False
        if evidence_type and evidence_type not in {"tax_invoice", "machine_invoice"}:
            return False
        return self._object_identity_policy.is_oa_attachment_invoice_evidence(attachment_invoice)

    @staticmethod
    def _normalize_invoice_type_value(value: Any) -> InvoiceType:
        text = str(value or "").strip().lower()
        if "销" in text or text == InvoiceType.OUTPUT.value or "output" in text:
            return InvoiceType.OUTPUT
        return InvoiceType.INPUT

    def _merge_invoice_from_etc_normalized(self, invoice: Invoice, normalized: dict[str, Any]) -> None:
        self._ensure_invoice_metadata_fields(invoice)
        for tag in normalized.get("tags") or []:
            self._append_unique_tag(invoice.tags, str(tag))
        self._append_invoice_source_link(invoice, self._build_etc_invoice_source_link(normalized))
        invoice.etc_invoice_id = normalized.get("etc_invoice_id") or invoice.etc_invoice_id
        invoice.etc_import_batch_id = normalized.get("etc_import_batch_id") or invoice.etc_import_batch_id
        invoice.etc_submission_batch_id = normalized.get("etc_submission_batch_id") or invoice.etc_submission_batch_id
        invoice.etc_submission_status = normalized.get("etc_submission_status") or invoice.etc_submission_status
        invoice.workbench_visibility = normalized.get("workbench_visibility") or invoice.workbench_visibility or "visible"
        invoice.source_batch_id = normalized.get("source_batch_id") or invoice.source_batch_id
        for field_name in (
            "digital_invoice_no",
            "invoice_date",
            "seller_tax_no",
            "seller_name",
            "buyer_tax_no",
            "buyer_name",
            "tax_rate",
            "invoice_source",
            "invoice_kind",
        ):
            incoming = normalized.get(field_name)
            if incoming and not getattr(invoice, field_name):
                setattr(invoice, field_name, incoming)
        for field_name in ("tax_amount", "total_with_tax"):
            incoming = normalized.get(field_name)
            if incoming and getattr(invoice, field_name) is None:
                setattr(invoice, field_name, Decimal(incoming))
        if not invoice.source_unique_key:
            invoice.source_unique_key = normalized.get("source_unique_key")
            if invoice.source_unique_key:
                self._invoice_unique_index[invoice.source_unique_key] = invoice.id
        self._clear_weak_invoice_fingerprint_when_canonical(invoice)

    @staticmethod
    def _etc_invoice_merge_state(invoice: Invoice) -> tuple[object, ...]:
        source_links = tuple(
            tuple(sorted((str(key), str(value)) for key, value in source_link.items()))
            if isinstance(source_link, dict)
            else str(source_link)
            for source_link in list(getattr(invoice, "source_links", []) or [])
        )
        return (
            tuple(str(tag) for tag in list(getattr(invoice, "tags", []) or [])),
            source_links,
            getattr(invoice, "etc_invoice_id", None),
            getattr(invoice, "etc_import_batch_id", None),
            getattr(invoice, "etc_submission_batch_id", None),
            getattr(invoice, "etc_submission_status", None),
            getattr(invoice, "workbench_visibility", None),
            getattr(invoice, "source_batch_id", None),
            getattr(invoice, "digital_invoice_no", None),
            getattr(invoice, "invoice_date", None),
            getattr(invoice, "seller_tax_no", None),
            getattr(invoice, "seller_name", None),
            getattr(invoice, "buyer_tax_no", None),
            getattr(invoice, "buyer_name", None),
            getattr(invoice, "tax_rate", None),
            getattr(invoice, "invoice_source", None),
            getattr(invoice, "invoice_kind", None),
            getattr(invoice, "tax_amount", None),
            getattr(invoice, "total_with_tax", None),
            getattr(invoice, "source_unique_key", None),
            getattr(invoice, "data_fingerprint", None),
        )

    def _link_submitted_etc_metadata_if_present(self, invoice: Invoice, normalized: dict[str, Any]) -> None:
        invoice_type = getattr(invoice, "invoice_type", None)
        invoice_type_value = getattr(invoice_type, "value", invoice_type)
        if str(invoice_type_value or "") != InvoiceType.INPUT.value:
            return
        finder = getattr(self._fact_repository, "find_submitted_etc_invoice_by_identity", None)
        if not callable(finder):
            return
        etc_invoice = finder(
            canonical_key=self._string_or_none(normalized.get("source_unique_key")),
            suspected_key=self._string_or_none(normalized.get("data_fingerprint")),
            invoice_no=self._string_or_none(normalized.get("invoice_no")),
            invoice_code=self._string_or_none(normalized.get("invoice_code")),
            digital_invoice_no=self._string_or_none(normalized.get("digital_invoice_no")),
        )
        if etc_invoice is None:
            return
        etc_normalized = self._normalize_etc_invoice(etc_invoice)
        if not self._submitted_etc_metadata_matches_formal_invoice(normalized, etc_normalized):
            return
        self._merge_invoice_from_etc_normalized(invoice, etc_normalized)
        self._record_submitted_etc_batch_invoice_link(invoice, etc_invoice, normalized, etc_normalized)

    def _record_submitted_etc_batch_invoice_link(
        self,
        invoice: Invoice,
        etc_invoice: Any,
        normalized: dict[str, Any],
        etc_normalized: dict[str, Any],
    ) -> None:
        link_service = self._etc_batch_invoice_link_service
        linker = getattr(link_service, "link_submitted_invoice", None)
        if not callable(linker):
            return
        linker(
            invoice=invoice,
            etc_invoice=etc_invoice,
            link_source="formal_invoice_import",
            confidence="strict",
            raw_payload={
                "match": "submitted_etc_identity",
                "formal_invoice_source_unique_key": normalized.get("source_unique_key"),
                "formal_invoice_no": normalized.get("digital_invoice_no") or normalized.get("invoice_no"),
                "etc_invoice_id": etc_normalized.get("etc_invoice_id"),
            },
        )

    def _submitted_etc_metadata_matches_formal_invoice(
        self,
        normalized: dict[str, Any],
        etc_normalized: dict[str, Any],
    ) -> bool:
        formal_number = self._string_or_none(normalized.get("digital_invoice_no") or normalized.get("invoice_no"))
        etc_number = self._string_or_none(etc_normalized.get("digital_invoice_no") or etc_normalized.get("invoice_no"))
        if not formal_number or formal_number != etc_number:
            return False
        if self._string_or_none(normalized.get("invoice_date")) != self._string_or_none(etc_normalized.get("invoice_date")):
            return False
        for field_name in ("tax_amount", "total_with_tax"):
            formal_amount = self._parse_decimal(normalized.get(field_name))
            etc_amount = self._parse_decimal(etc_normalized.get(field_name))
            if formal_amount is not None and etc_amount is not None and formal_amount != etc_amount:
                return False
        for field_name in ("seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no"):
            formal_value = self._string_or_none(normalized.get(field_name))
            etc_value = self._string_or_none(etc_normalized.get(field_name))
            if formal_value and etc_value and formal_value != etc_value:
                return False
        return True

    def _build_etc_invoice_source_link(self, normalized: dict[str, Any]) -> dict[str, str]:
        return {
            "source_type": "etc_invoice_import",
            "source_id": normalized.get("etc_invoice_id") or normalized.get("source_unique_key") or "",
            "batch_id": normalized.get("etc_import_batch_id") or "",
            "created_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _ensure_invoice_metadata_fields(invoice: Invoice) -> None:
        if not hasattr(invoice, "tags"):
            invoice.tags = []
        if not hasattr(invoice, "source_links"):
            invoice.source_links = []
        for field_name in (
            "etc_invoice_id",
            "etc_import_batch_id",
            "etc_submission_batch_id",
            "etc_submission_status",
        ):
            if not hasattr(invoice, field_name):
                setattr(invoice, field_name, None)
        if not hasattr(invoice, "workbench_visibility"):
            invoice.workbench_visibility = "visible"

    def _clear_weak_invoice_fingerprint_when_canonical(self, invoice: Invoice) -> None:
        if not invoice.source_unique_key or not invoice.data_fingerprint:
            return
        self._invoice_fingerprint_index.pop(invoice.data_fingerprint, None)
        invoice.data_fingerprint = None

    @staticmethod
    def _ensure_transaction_metadata_fields(transaction: BankTransaction) -> None:
        if not hasattr(transaction, "bank_text_fields"):
            transaction.bank_text_fields = []

    def _merge_invoice_from_normalized(self, invoice: Invoice, batch_id: str, normalized: dict[str, Any]) -> None:
        self._ensure_invoice_metadata_fields(invoice)
        for tag in normalized.get("tags") or []:
            self._append_unique_tag(invoice.tags, str(tag))
        self._append_invoice_source_link(invoice, self._build_invoice_source_link(batch_id, normalized))
        invoice.source_batch_id = batch_id
        if normalized.get("invoice_status_from_source"):
            invoice.invoice_status_from_source = normalized.get("invoice_status_from_source")
        for field_name in (
            "invoice_code",
            "digital_invoice_no",
            "invoice_date",
            "seller_tax_no",
            "seller_name",
            "buyer_tax_no",
            "buyer_name",
            "tax_rate",
            "tax_classification_code",
            "specific_business_type",
            "taxable_item_name",
            "specification_model",
            "unit",
            "invoice_source",
            "invoice_kind",
            "is_positive_invoice",
            "risk_level",
            "issuer",
            "remark",
            "project_id",
            "oa_form_id",
        ):
            incoming = normalized.get(field_name)
            if incoming and not getattr(invoice, field_name):
                setattr(invoice, field_name, incoming)
        for field_name in ("tax_amount", "total_with_tax", "quantity", "unit_price"):
            incoming = normalized.get(field_name)
            if incoming and getattr(invoice, field_name) is None:
                setattr(invoice, field_name, Decimal(incoming))
        if not invoice.source_unique_key:
            invoice.source_unique_key = normalized.get("source_unique_key")
            if invoice.source_unique_key:
                self._invoice_unique_index[invoice.source_unique_key] = invoice.id
        self._clear_weak_invoice_fingerprint_when_canonical(invoice)

    def _build_invoice_source_link(self, batch_id: str, normalized: dict[str, Any]) -> dict[str, str]:
        source_link = {
            "source_type": "manual_invoice_import",
            "source_id": normalized.get("source_unique_key") or normalized.get("data_fingerprint") or "",
            "batch_id": batch_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        request_key = str(normalized.get("pending_invoice_request_key") or "").strip()
        bank_transaction_id = str(normalized.get("pending_invoice_bank_transaction_id") or "").strip()
        if request_key:
            source_link["request_key"] = request_key
        if bank_transaction_id:
            source_link["bank_transaction_id"] = bank_transaction_id
        return source_link

    @staticmethod
    def _append_invoice_source_link(invoice: Invoice, source_link: dict[str, str]) -> None:
        for existing in invoice.source_links:
            if (
                existing.get("source_type") == source_link.get("source_type")
                and existing.get("source_id") == source_link.get("source_id")
                and existing.get("batch_id") == source_link.get("batch_id")
            ):
                incoming_item_id = str(source_link.get("source_expense_item_id") or "").strip()
                existing_item_id = str(existing.get("source_expense_item_id") or "").strip()
                if incoming_item_id and not existing_item_id:
                    for key in (
                        "source_workbench_row_id",
                        "derived_from_oa_id",
                        "source_attachment_key",
                        "source_attachment_name",
                        "source_expense_item_id",
                        "source_expense_row_index",
                        "source_region_key",
                        "evidence_type",
                        "document_kind",
                    ):
                        value = str(source_link.get(key) or "").strip()
                        if value:
                            existing[key] = value
                return
        invoice.source_links.append(source_link)

    @staticmethod
    def _append_unique_tag(tags: list[str], tag: str) -> None:
        clean_tag = tag.strip()
        if clean_tag and clean_tag not in tags:
            tags.append(clean_tag)

    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            tags = [str(item).strip() for item in value if str(item).strip()]
        else:
            tags = [part.strip() for part in re.split(r"[,，;；、\s]+", str(value)) if part.strip()]
        normalized: list[str] = []
        for tag in tags:
            cls._append_unique_tag(normalized, tag)
        return normalized

    @staticmethod
    def _row_indicates_etc(normalized: dict[str, Any]) -> bool:
        tags = {str(tag).strip().upper() for tag in normalized.get("tags") or []}
        invoice_source = str(normalized.get("invoice_source") or "").upper()
        invoice_kind = str(normalized.get("invoice_kind") or "").upper()
        return "ETC" in tags or "ETC" in invoice_source or "ETC" in invoice_kind

    @staticmethod
    def _transaction_row_result_display_fields(normalized: dict[str, Any], identity: Any) -> dict[str, str | None]:
        components = getattr(identity, "components", {}) or {}
        return {
            "identity_kind": (
                "stable"
                if getattr(identity, "canonical_key", None)
                else "suspected"
                if getattr(identity, "suspected_key", None)
                else None
            ),
            "account_no": normalized.get("account_no"),
            "trade_time": (
                components.get("trade_time")
                or normalized.get("trade_time")
                or normalized.get("pay_receive_time")
                or normalized.get("txn_date")
            ),
            "direction": normalized.get("txn_direction"),
            "amount": normalized.get("amount"),
            "counterparty_name": normalized.get("counterparty_name_raw"),
        }

    @staticmethod
    def _count_decisions(row_results: list[ImportedBatchRowResult], *decisions: ImportDecision) -> int:
        decision_set = set(decisions)
        return sum(1 for row in row_results if row.decision in decision_set)

    def _next_batch_id(self) -> str:
        self._batch_counter += 1
        return f"batch_import_{uuid4().hex}"

    @staticmethod
    def _row_id(batch_id: str, row_no: int) -> str:
        return f"batch_row:{batch_id}:{int(row_no):05d}"

    def _next_invoice_id(self) -> str:
        self._invoice_counter += 1
        return f"inv_imported_{uuid4().hex}"

    def _next_transaction_id(self) -> str:
        self._txn_counter += 1
        return f"txn_imported_{uuid4().hex}"

    @staticmethod
    def _parse_date(value: Any) -> str | None:
        if value is None:
            return None
        text = clean_string(value)
        if text in PLACEHOLDER_EMPTY_VALUES:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        text = str(value).strip()
        if text in PLACEHOLDER_EMPTY_VALUES:
            return None
        try:
            return Decimal(text.replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return f"{value.quantize(CENT)}"

    @staticmethod
    def _canonical_currency(value: Any) -> str | None:
        text = ImportNormalizationService._string_or_none(value)
        if text is None:
            return None
        normalized = "".join(text.upper().split())
        if normalized in {"CNY", "RMB", "人民币", "人民币元"}:
            return "CNY"
        return normalized or None

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = clean_string(value)
        if text in PLACEHOLDER_EMPTY_VALUES:
            return None
        return text

    @staticmethod
    def _normalize_bank_text_fields(raw_row: dict[str, Any]) -> list[dict[str, str]]:
        fields: list[dict[str, str]] = []
        seen_labels: set[str] = set()

        def add_field(label: Any, value: Any) -> None:
            clean_label = ImportNormalizationService._string_or_none(label)
            clean_value = ImportNormalizationService._string_or_none(value)
            if not clean_label or not clean_value or clean_label in seen_labels:
                return
            fields.append({"label": clean_label, "value": clean_value})
            seen_labels.add(clean_label)

        incoming = raw_row.get("bank_text_fields")
        if isinstance(incoming, dict):
            for label in BANK_TEXT_FIELD_LABELS:
                add_field(label, incoming.get(label))
            for label, value in incoming.items():
                add_field(label, value)
        elif isinstance(incoming, list):
            for item in incoming:
                if not isinstance(item, dict):
                    continue
                add_field(item.get("label"), item.get("value"))

        for label in BANK_TEXT_FIELD_LABELS:
            add_field(label, raw_row.get(label))

        return fields


def clean_string(value: Any) -> str:
    return str(value).strip()


def normalize_name(value: str) -> str:
    collapsed = WHITESPACE_RE.sub(" ", clean_string(value)).lower()
    return collapsed
