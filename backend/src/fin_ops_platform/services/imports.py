from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.domain.enums import BatchStatus, BatchType, ImportDecision, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import (
    BankTransaction,
    Counterparty,
    ImportedBatch,
    ImportedBatchRowResult,
    Invoice,
)


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
WHITESPACE_RE = re.compile(r"\s+")


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


class ImportNormalizationService:
    def __init__(
        self,
        *,
        existing_invoices: list[Invoice] | None = None,
        existing_transactions: list[BankTransaction] | None = None,
        id_registry: Any | None = None,
    ) -> None:
        self._batch_counter = 0
        self._row_counter = 0
        self._invoice_counter = len(existing_invoices or [])
        self._txn_counter = len(existing_transactions or [])
        self._counterparty_counter = 0
        self._id_registry = id_registry

        self._batches: dict[str, ImportPreview] = {}
        self._invoices_by_id: dict[str, Invoice] = {}
        self._transactions_by_id: dict[str, BankTransaction] = {}
        self._counterparties_by_normalized_name: dict[str, Counterparty] = {}

        self._invoice_unique_index: dict[str, str] = {}
        self._invoice_fingerprint_index: dict[str, str] = {}
        self._transaction_unique_index: dict[str, str] = {}
        self._transaction_fingerprint_index: dict[str, str] = {}

        for invoice in existing_invoices or []:
            self._register_invoice(invoice)
        for transaction in existing_transactions or []:
            self._register_transaction(transaction)

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        id_registry: Any | None = None,
    ) -> ImportNormalizationService:
        service = cls(
            existing_invoices=list((snapshot or {}).get("invoices", [])),
            existing_transactions=list((snapshot or {}).get("transactions", [])),
            id_registry=id_registry,
        )
        if not snapshot:
            return service
        service._batch_counter = int(snapshot.get("batch_counter", 0))
        service._row_counter = int(snapshot.get("row_counter", 0))
        service._invoice_counter = int(snapshot.get("invoice_counter", service._invoice_counter))
        service._txn_counter = int(snapshot.get("txn_counter", service._txn_counter))
        service._counterparty_counter = int(snapshot.get("counterparty_counter", service._counterparty_counter))
        service._batches = dict(snapshot.get("batches", {}))
        return service

    def snapshot(self) -> dict[str, Any]:
        return {
            "batch_counter": self._batch_counter,
            "row_counter": self._row_counter,
            "invoice_counter": self._invoice_counter,
            "txn_counter": self._txn_counter,
            "counterparty_counter": self._counterparty_counter,
            "batches": self._batches,
            "invoices": self.list_invoices(),
            "transactions": self.list_transactions(),
        }

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
        for index, raw_row in enumerate(rows, start=1):
            if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
                normalized, row_result = self._preview_invoice_row(
                    batch_id=batch_id,
                    row_no=index,
                    batch_type=batch_type,
                    raw_row=raw_row,
                )
            else:
                normalized, row_result = self._preview_transaction_row(
                    batch_id=batch_id,
                    row_no=index,
                    raw_row=raw_row,
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
        for row_result, normalized in zip(preview.row_results, preview.normalized_rows, strict=True):
            if row_result.decision == ImportDecision.CREATED:
                self._persist_created_row(preview.batch.batch_type, row_result, normalized)
            elif row_result.decision == ImportDecision.STATUS_UPDATED:
                self._persist_updated_row(preview.batch.batch_type, row_result, normalized)

        has_issues = preview.error_count > 0 or preview.suspected_duplicate_count > 0
        preview.batch.status = BatchStatus.COMPLETED_WITH_ERRORS if has_issues else BatchStatus.COMPLETED
        self._batches[batch_id] = preview
        return preview.batch

    def get_batch(self, batch_id: str) -> ImportPreview:
        return self._batches[batch_id]

    def list_batches(self) -> list[ImportPreview]:
        return list(self._batches.values())

    def list_invoices(self) -> list[Invoice]:
        return list(self._invoices_by_id.values())

    def get_invoice(self, invoice_id: str) -> Invoice:
        return self._invoices_by_id[invoice_id]

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

    def list_transactions(self) -> list[BankTransaction]:
        return list(self._transactions_by_id.values())

    def get_transaction(self, transaction_id: str) -> BankTransaction:
        return self._transactions_by_id[transaction_id]

    def has_imported_records(self) -> bool:
        return bool(self._invoices_by_id or self._transactions_by_id)

    def revert_import(self, batch_id: str) -> ImportedBatch:
        preview = self._batches[batch_id]
        if preview.batch.status == BatchStatus.REVERTED:
            return preview.batch

        for row_result, normalized in reversed(list(zip(preview.row_results, preview.normalized_rows, strict=True))):
            if row_result.decision == ImportDecision.CREATED and row_result.linked_object_id:
                if row_result.linked_object_type == "invoice":
                    self._remove_invoice(row_result.linked_object_id)
                elif row_result.linked_object_type == "bank_transaction":
                    self._remove_transaction(row_result.linked_object_id)
            elif row_result.decision == ImportDecision.STATUS_UPDATED and row_result.linked_object_id:
                invoice = self._invoices_by_id[row_result.linked_object_id]
                invoice.invoice_status_from_source = normalized.get("previous_invoice_status_from_source")
                invoice.source_batch_id = normalized.get("previous_source_batch_id")

        preview.batch.status = BatchStatus.REVERTED
        self._batches[batch_id] = preview
        return preview.batch

    def _preview_invoice_row(
        self,
        *,
        batch_id: str,
        row_no: int,
        batch_type: BatchType,
        raw_row: dict[str, Any],
    ) -> tuple[dict[str, Any], ImportedBatchRowResult]:
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

        source_unique_key = self._build_invoice_unique_key(normalized)
        data_fingerprint = None
        if normalized_name and invoice_date and amount is not None:
            data_fingerprint = self._build_invoice_fingerprint(normalized_name, invoice_date, amount)
        normalized["source_unique_key"] = source_unique_key
        normalized["data_fingerprint"] = data_fingerprint
        normalized["invoice_type"] = InvoiceType.OUTPUT.value if batch_type == BatchType.OUTPUT_INVOICE else InvoiceType.INPUT.value

        if errors:
            return normalized, ImportedBatchRowResult(
                id=self._next_row_id(),
                batch_id=batch_id,
                row_no=row_no,
                source_record_type="invoice",
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
                decision=ImportDecision.ERROR,
                decision_reason="; ".join(errors),
                raw_payload=dict(raw_row),
            )

        linked_invoice_id = None
        decision = ImportDecision.CREATED
        reason = "Ready to create new invoice."

        if source_unique_key and source_unique_key in self._invoice_unique_index:
            linked_invoice_id = self._invoice_unique_index[source_unique_key]
            existing = self._invoices_by_id[linked_invoice_id]
            normalized["previous_invoice_status_from_source"] = existing.invoice_status_from_source
            normalized["previous_source_batch_id"] = existing.source_batch_id
            incoming_status = normalized.get("invoice_status_from_source")
            if incoming_status and incoming_status != existing.invoice_status_from_source:
                decision = ImportDecision.STATUS_UPDATED
                reason = "Unique business key matched an existing invoice with a changed source status."
            else:
                decision = ImportDecision.DUPLICATE_SKIPPED
                reason = "Unique business key matched an existing invoice with no source status change."
        elif data_fingerprint and data_fingerprint in self._invoice_fingerprint_index:
            linked_invoice_id = self._invoice_fingerprint_index[data_fingerprint]
            decision = ImportDecision.SUSPECTED_DUPLICATE
            reason = "Fingerprint matched an existing invoice without a stable official unique key."

        return normalized, ImportedBatchRowResult(
            id=self._next_row_id(),
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
            "account_detail_no": self._string_or_none(raw_row.get("account_detail_no")),
            "voucher_kind": self._string_or_none(raw_row.get("voucher_kind")),
            "project_id": self._string_or_none(raw_row.get("project_id")),
        }
        errors: list[str] = []

        account_no = normalized["account_no"]
        if not account_no:
            errors.append("account_no is required")
        if not normalized_name:
            errors.append("counterparty_name is required")

        txn_date = self._parse_date(raw_row.get("txn_date"))
        if txn_date is None:
            errors.append("txn_date is invalid")
        else:
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

        source_unique_key = self._build_transaction_unique_key(normalized)
        data_fingerprint = None
        if account_no and normalized_name and txn_date and direction and amount is not None:
            data_fingerprint = self._build_transaction_fingerprint(account_no, normalized_name, txn_date, direction, amount)
        normalized["source_unique_key"] = source_unique_key
        normalized["data_fingerprint"] = data_fingerprint

        if errors:
            return normalized, ImportedBatchRowResult(
                id=self._next_row_id(),
                batch_id=batch_id,
                row_no=row_no,
                source_record_type="bank_transaction",
                source_unique_key=source_unique_key,
                data_fingerprint=data_fingerprint,
                decision=ImportDecision.ERROR,
                decision_reason="; ".join(errors),
                raw_payload=dict(raw_row),
            )

        linked_txn_id = None
        decision = ImportDecision.CREATED
        reason = "Ready to create new bank transaction."
        if source_unique_key and source_unique_key in self._transaction_unique_index:
            linked_txn_id = self._transaction_unique_index[source_unique_key]
            decision = ImportDecision.DUPLICATE_SKIPPED
            reason = "Official transaction serial already exists."
        elif data_fingerprint and data_fingerprint in self._transaction_fingerprint_index:
            linked_txn_id = self._transaction_fingerprint_index[data_fingerprint]
            decision = ImportDecision.SUSPECTED_DUPLICATE
            reason = "Fingerprint matched an existing transaction without an official unique key."

        return normalized, ImportedBatchRowResult(
            id=self._next_row_id(),
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
        )

    def _persist_created_row(
        self,
        batch_type: BatchType,
        row_result: ImportedBatchRowResult,
        normalized: dict[str, Any],
    ) -> None:
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            invoice = self._build_invoice_from_normalized(batch_type, row_result.batch_id, normalized)
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
        invoice = self._invoices_by_id[row_result.linked_object_id or ""]
        invoice.invoice_status_from_source = normalized.get("invoice_status_from_source")
        invoice.source_batch_id = row_result.batch_id

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
            account_detail_no=normalized.get("account_detail_no"),
            enterprise_serial_no=normalized.get("enterprise_serial_no"),
            voucher_kind=normalized.get("voucher_kind"),
            voucher_no=normalized.get("voucher_no"),
            project_id=normalized.get("project_id"),
            source_batch_id=batch_id,
        )

    def _register_invoice(self, invoice: Invoice) -> None:
        self._invoices_by_id[invoice.id] = invoice
        self._get_or_create_counterparty(invoice.counterparty.name, existing=invoice.counterparty)
        if invoice.source_unique_key:
            self._invoice_unique_index[invoice.source_unique_key] = invoice.id
        if invoice.data_fingerprint:
            self._invoice_fingerprint_index[invoice.data_fingerprint] = invoice.id

    def _register_transaction(self, transaction: BankTransaction) -> None:
        self._transactions_by_id[transaction.id] = transaction
        if transaction.source_unique_key:
            self._transaction_unique_index[transaction.source_unique_key] = transaction.id
        if transaction.data_fingerprint:
            self._transaction_fingerprint_index[transaction.data_fingerprint] = transaction.id

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
        digital_invoice_no = normalized.get("digital_invoice_no")
        if digital_invoice_no and digital_invoice_no.isdigit() and len(digital_invoice_no) == 20:
            return digital_invoice_no
        invoice_code = normalized.get("invoice_code")
        invoice_no = normalized.get("invoice_no")
        if invoice_code and invoice_no:
            return f"{invoice_code}:{invoice_no}"
        return None

    @staticmethod
    def _build_invoice_fingerprint(normalized_name: str, invoice_date: str, amount: Decimal) -> str:
        return f"invoice:{normalized_name}:{invoice_date}:{amount.quantize(CENT)}"

    def _build_transaction_unique_key(self, normalized: dict[str, Any]) -> str | None:
        for key in ("bank_serial_no", "voucher_no", "enterprise_serial_no"):
            value = normalized.get(key)
            if value:
                return value
        return None

    @staticmethod
    def _build_transaction_fingerprint(
        account_no: str,
        normalized_name: str,
        txn_date: str,
        direction: TransactionDirection,
        amount: Decimal,
    ) -> str:
        return f"bank:{account_no}:{normalized_name}:{txn_date}:{direction.value}:{amount.quantize(CENT)}"

    @staticmethod
    def _count_decisions(row_results: list[ImportedBatchRowResult], *decisions: ImportDecision) -> int:
        decision_set = set(decisions)
        return sum(1 for row in row_results if row.decision in decision_set)

    def _next_batch_id(self) -> str:
        while True:
            self._batch_counter += 1
            batch_id = f"batch_import_{self._batch_counter:04d}"
            if batch_id not in self._batches and not self._registry_has("import_batch_exists", batch_id):
                return batch_id

    def _next_row_id(self) -> str:
        self._row_counter += 1
        return f"batch_row_{self._row_counter:05d}"

    def _next_invoice_id(self) -> str:
        while True:
            self._invoice_counter += 1
            invoice_id = f"inv_imported_{self._invoice_counter:04d}"
            if invoice_id not in self._invoices_by_id and not self._registry_has("invoice_exists", invoice_id):
                return invoice_id

    def _next_transaction_id(self) -> str:
        while True:
            self._txn_counter += 1
            transaction_id = f"txn_imported_{self._txn_counter:04d}"
            if transaction_id not in self._transactions_by_id and not self._registry_has("transaction_exists", transaction_id):
                return transaction_id

    def _registry_has(self, method_name: str, identifier: str) -> bool:
        checker = getattr(self._id_registry, method_name, None)
        if not callable(checker):
            return False
        return bool(checker(identifier))

    @staticmethod
    def _parse_date(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = clean_string(value)
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return f"{value.quantize(CENT)}"

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return clean_string(value)


def clean_string(value: Any) -> str:
    return str(value).strip()


def normalize_name(value: str) -> str:
    collapsed = WHITESPACE_RE.sub(" ", clean_string(value)).lower()
    return collapsed
