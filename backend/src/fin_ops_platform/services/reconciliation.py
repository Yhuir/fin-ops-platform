from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from typing import Any

from fin_ops_platform.domain.enums import (
    DifferenceReason,
    InvoiceStatus,
    InvoiceType,
    ReconciliationCaseStatus,
    ReconciliationCaseType,
    TransactionDirection,
    TransactionStatus,
)
from fin_ops_platform.domain.models import (
    BankTransaction,
    ExceptionHandlingRecord,
    Invoice,
    MatchingResult,
    OfflineReconciliationRecord,
    OffsetNote,
    ReconciliationCase,
    ReconciliationLine,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
COMPANY_NAME = "杭州溯源科技有限公司"
COMPANY_TAX_NO = "91330106589876543T"
RECEIVABLE_EXCEPTION_OPTIONS = [
    {"code": "SO-A", "title": "客户欠款"},
    {"code": "SO-B", "title": "待开销项票"},
    {"code": "SO-C", "title": "甲方多付 / 预付"},
    {"code": "SO-D", "title": "一票多收"},
    {"code": "SO-E", "title": "别人借入"},
    {"code": "SO-F", "title": "别人还款"},
    {"code": "SO-G", "title": "非税收入"},
    {"code": "SO-H", "title": "内部往来 / 其他核查"},
]
PAYABLE_EXCEPTION_OPTIONS = [
    {"code": "PI-A", "title": "多票合并付款"},
    {"code": "PI-B", "title": "供应商漏开发票"},
    {"code": "PI-C", "title": "付款出错（多付）"},
    {"code": "PI-D", "title": "纯采购未开票"},
    {"code": "PI-E", "title": "借钱给别人"},
    {"code": "PI-F", "title": "偿还借款"},
    {"code": "PI-G", "title": "待付款（欠供应商）"},
    {"code": "PI-H", "title": "现金混付 / 分期付款"},
]


class ManualReconciliationService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        matching_service: MatchingEngineService,
        audit_service: AuditTrailService,
    ) -> None:
        self._import_service = import_service
        self._matching_service = matching_service
        self._audit_service = audit_service
        self._case_sequence = count(1)
        self._line_sequence = count(1)
        self._exception_sequence = count(1)
        self._offline_sequence = count(1)
        self._offset_sequence = count(1)
        self._cases: dict[str, ReconciliationCase] = {}
        self._exception_records: dict[str, ExceptionHandlingRecord] = {}
        self._offline_records: dict[str, OfflineReconciliationRecord] = {}
        self._offset_notes: dict[str, OffsetNote] = {}

    def confirm_manual_reconciliation(
        self,
        *,
        actor_id: str,
        invoice_ids: list[str],
        transaction_ids: list[str],
        oa_ids: list[str] | None = None,
        source_result_id: str | None = None,
        remark: str | None = None,
        amount: str | Decimal | None = None,
    ) -> ReconciliationCase:
        invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in invoice_ids]
        transactions = [self._import_service.get_transaction(transaction_id) for transaction_id in transaction_ids]
        if not invoices or not transactions:
            raise ValueError("invoice_ids and transaction_ids are required for manual reconciliation.")

        requested_amount = self._coerce_decimal(amount) if amount is not None else None
        biz_side = self._resolve_biz_side(invoices)
        invoice_sign = self._resolve_invoice_sign(invoices)
        self._validate_transaction_direction(transactions, biz_side=biz_side, invoice_sign=invoice_sign)
        invoice_total = sum((abs(invoice.outstanding_amount) for invoice in invoices), start=ZERO)
        transaction_total = sum((transaction.outstanding_amount for transaction in transactions), start=ZERO)
        applied_amount = requested_amount if requested_amount is not None else min(invoice_total, transaction_total)
        if applied_amount <= ZERO:
            raise ValueError("applied amount must be positive.")

        invoice_allocations = self._allocate_invoice_amounts(invoices, applied_amount)
        transaction_allocations = self._allocate_transaction_amounts(transactions, applied_amount)
        difference_amount = abs(invoice_total - transaction_total) if requested_amount is None else ZERO
        case = ReconciliationCase(
            id=self._next_case_id(),
            case_type=ReconciliationCaseType.MANUAL,
            biz_side=biz_side,
            counterparty_id=self._resolve_counterparty_id(invoices, transactions),
            total_amount=applied_amount,
            difference_amount=difference_amount,
            difference_note=remark if difference_amount > ZERO else None,
            created_by=actor_id,
            source_result_id=source_result_id,
            remark=remark,
            related_oa_ids=list(oa_ids or []),
            status=ReconciliationCaseStatus.FOLLOW_UP_REQUIRED if difference_amount > ZERO else ReconciliationCaseStatus.CONFIRMED,
            lines=[
                *self._make_lines(case_id=None, object_type="invoice", allocations=invoice_allocations, side_role="debit"),
                *self._make_lines(case_id=None, object_type="bank_txn", allocations=transaction_allocations, side_role="credit"),
            ],
        )
        self._bind_case_lines(case)
        self._apply_invoice_allocations(invoice_allocations)
        self._apply_transaction_allocations(transaction_allocations)
        self._cases[case.id] = case
        self._audit_service.record_action(
            actor_id=actor_id,
            action="manual_reconciliation_confirmed",
            entity_type="reconciliation_case",
            entity_id=case.id,
            before_amount=ZERO,
            after_amount=applied_amount,
            metadata={
                "invoice_ids": invoice_ids,
                "transaction_ids": transaction_ids,
                "oa_ids": list(oa_ids or []),
                "source_result_id": source_result_id,
                "remark": remark,
            },
        )
        return case

    def confirm_difference_reconciliation(
        self,
        *,
        actor_id: str,
        invoice_ids: list[str],
        transaction_ids: list[str],
        difference_reason: DifferenceReason | str,
        difference_note: str | None = None,
        oa_ids: list[str] | None = None,
        source_result_id: str | None = None,
    ) -> ReconciliationCase:
        invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in invoice_ids]
        transactions = [self._import_service.get_transaction(transaction_id) for transaction_id in transaction_ids]
        if not invoices or not transactions:
            raise ValueError("invoice_ids and transaction_ids are required for difference reconciliation.")

        biz_side = self._resolve_biz_side(invoices)
        invoice_sign = self._resolve_invoice_sign(invoices)
        self._validate_transaction_direction(transactions, biz_side=biz_side, invoice_sign=invoice_sign)
        invoice_total = sum((abs(invoice.outstanding_amount) for invoice in invoices), start=ZERO)
        transaction_total = sum((transaction.outstanding_amount for transaction in transactions), start=ZERO)
        difference_amount = abs(invoice_total - transaction_total)
        if difference_amount <= ZERO:
            raise ValueError("difference reconciliation requires a non-zero difference amount.")

        invoice_allocations = self._allocate_invoice_amounts(invoices, invoice_total)
        transaction_allocations = self._allocate_transaction_amounts(transactions, transaction_total)
        normalized_reason = DifferenceReason(difference_reason)
        case = ReconciliationCase(
            id=self._next_case_id(),
            case_type=ReconciliationCaseType.DIFFERENCE,
            biz_side=biz_side,
            counterparty_id=self._resolve_counterparty_id(invoices, transactions),
            total_amount=max(invoice_total, transaction_total),
            difference_amount=difference_amount,
            difference_reason=normalized_reason,
            difference_note=difference_note,
            created_by=actor_id,
            source_result_id=source_result_id,
            remark=difference_note,
            related_oa_ids=list(oa_ids or []),
            status=ReconciliationCaseStatus.CONFIRMED,
            lines=[
                *self._make_lines(case_id=None, object_type="invoice", allocations=invoice_allocations, side_role="debit"),
                *self._make_lines(case_id=None, object_type="bank_txn", allocations=transaction_allocations, side_role="credit"),
            ],
        )
        self._bind_case_lines(case)
        self._apply_invoice_allocations(invoice_allocations)
        self._apply_transaction_allocations(transaction_allocations)
        self._cases[case.id] = case
        self._audit_service.record_action(
            actor_id=actor_id,
            action="difference_reconciliation_confirmed",
            entity_type="reconciliation_case",
            entity_id=case.id,
            before_amount=ZERO,
            after_amount=case.total_amount,
            metadata={
                "invoice_ids": invoice_ids,
                "transaction_ids": transaction_ids,
                "difference_amount": f"{difference_amount.quantize(CENT)}",
                "difference_reason": normalized_reason.value,
                "difference_note": difference_note,
                "oa_ids": list(oa_ids or []),
                "source_result_id": source_result_id,
            },
        )
        return case

    def record_exception(
        self,
        *,
        actor_id: str,
        biz_side: str,
        exception_code: str,
        invoice_ids: list[str],
        transaction_ids: list[str],
        oa_ids: list[str] | None = None,
        resolution_action: str | None = None,
        note: str | None = None,
    ) -> tuple[ReconciliationCase, ExceptionHandlingRecord]:
        invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in invoice_ids]
        transactions = [self._import_service.get_transaction(transaction_id) for transaction_id in transaction_ids]
        if not invoices and not transactions:
            raise ValueError("at least one invoice or transaction is required for exception handling.")

        issue_amount = sum((invoice.outstanding_amount for invoice in invoices), start=ZERO) + sum(
            (transaction.outstanding_amount for transaction in transactions),
            start=ZERO,
        )
        case = ReconciliationCase(
            id=self._next_case_id(),
            case_type=ReconciliationCaseType.DIFFERENCE,
            biz_side=biz_side,
            counterparty_id=self._resolve_counterparty_id(invoices, transactions),
            total_amount=issue_amount,
            difference_amount=issue_amount,
            difference_reason=note,
            created_by=actor_id,
            exception_code=exception_code,
            resolution_type=resolution_action,
            remark=note,
            related_oa_ids=list(oa_ids or []),
            status=ReconciliationCaseStatus.FOLLOW_UP_REQUIRED,
            lines=[
                *self._make_zero_lines(case_id=None, object_type="invoice", object_ids=invoice_ids),
                *self._make_zero_lines(case_id=None, object_type="bank_txn", object_ids=transaction_ids),
            ],
        )
        self._bind_case_lines(case)
        self._cases[case.id] = case
        exception_record = ExceptionHandlingRecord(
            id=f"exc_{next(self._exception_sequence):04d}",
            reconciliation_case_id=case.id,
            biz_side=biz_side,
            exception_code=exception_code,
            exception_title=self._resolve_exception_title(biz_side, exception_code),
            source_invoice_ids=list(invoice_ids),
            source_bank_txn_ids=list(transaction_ids),
            resolution_action=resolution_action,
            follow_up_ledger_type=self._resolve_follow_up_ledger_type(resolution_action),
            note=note,
            created_by=actor_id,
        )
        self._exception_records[exception_record.id] = exception_record
        self._audit_service.record_action(
            actor_id=actor_id,
            action="manual_exception_recorded",
            entity_type="reconciliation_case",
            entity_id=case.id,
            before_amount=ZERO,
            after_amount=issue_amount,
            metadata={
                "exception_code": exception_code,
                "invoice_ids": invoice_ids,
                "transaction_ids": transaction_ids,
                "resolution_action": resolution_action,
                "oa_ids": list(oa_ids or []),
                "note": note,
            },
        )
        return case, exception_record

    def record_offline_reconciliation(
        self,
        *,
        actor_id: str,
        biz_side: str,
        invoice_ids: list[str],
        amount: str | Decimal,
        payment_method: str,
        occurred_on: str,
        transaction_ids: list[str] | None = None,
        oa_ids: list[str] | None = None,
        note: str | None = None,
    ) -> tuple[ReconciliationCase, OfflineReconciliationRecord]:
        invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in invoice_ids]
        transactions = [self._import_service.get_transaction(transaction_id) for transaction_id in transaction_ids or []]
        if not invoices and not transactions:
            raise ValueError("at least one invoice or transaction is required for offline reconciliation.")

        applied_amount = self._coerce_decimal(amount)
        if applied_amount <= ZERO:
            raise ValueError("offline reconciliation amount must be positive.")

        invoice_allocations = self._allocate_invoice_amounts(invoices, applied_amount) if invoices else []
        transaction_allocations = (
            self._allocate_transaction_amounts(transactions, applied_amount) if transactions and not invoices else []
        )
        case = ReconciliationCase(
            id=self._next_case_id(),
            case_type=ReconciliationCaseType.OFFLINE,
            biz_side=biz_side,
            counterparty_id=self._resolve_counterparty_id(invoices, transactions),
            total_amount=applied_amount,
            created_by=actor_id,
            remark=note,
            related_oa_ids=list(oa_ids or []),
            status=ReconciliationCaseStatus.CONFIRMED,
            lines=[
                *self._make_lines(case_id=None, object_type="invoice", allocations=invoice_allocations, side_role="debit"),
                *self._make_lines(case_id=None, object_type="bank_txn", allocations=transaction_allocations, side_role="credit"),
            ],
        )
        offline_record = OfflineReconciliationRecord(
            id=f"offline_{next(self._offline_sequence):04d}",
            reconciliation_case_id=case.id,
            payment_method=payment_method,
            amount=applied_amount,
            occurred_on=occurred_on,
            note=note,
            created_by=actor_id,
        )
        case.lines.append(
            ReconciliationLine(
                id=self._next_line_id(),
                reconciliation_case_id=case.id,
                object_type="offline_record",
                object_id=offline_record.id,
                applied_amount=applied_amount,
                side_role="credit" if biz_side == "receivable" else "debit",
            )
        )
        self._bind_case_lines(case)
        self._apply_invoice_allocations(invoice_allocations)
        self._apply_transaction_allocations(transaction_allocations)
        self._cases[case.id] = case
        self._offline_records[offline_record.id] = offline_record
        self._audit_service.record_action(
            actor_id=actor_id,
            action="offline_reconciliation_recorded",
            entity_type="reconciliation_case",
            entity_id=case.id,
            before_amount=ZERO,
            after_amount=applied_amount,
            metadata={
                "invoice_ids": invoice_ids,
                "transaction_ids": list(transaction_ids or []),
                "payment_method": payment_method,
                "occurred_on": occurred_on,
                "oa_ids": list(oa_ids or []),
                "note": note,
            },
        )
        return case, offline_record

    def record_offset_reconciliation(
        self,
        *,
        actor_id: str,
        receivable_invoice_ids: list[str],
        payable_invoice_ids: list[str],
        reason: str,
        note: str | None = None,
        amount: str | Decimal | None = None,
        oa_ids: list[str] | None = None,
    ) -> tuple[ReconciliationCase, OffsetNote]:
        receivable_invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in receivable_invoice_ids]
        payable_invoices = [self._import_service.get_invoice(invoice_id) for invoice_id in payable_invoice_ids]
        if not receivable_invoices or not payable_invoices:
            raise ValueError("receivable_invoice_ids and payable_invoice_ids are required for offset reconciliation.")
        if any(invoice.invoice_type != InvoiceType.OUTPUT for invoice in receivable_invoices):
            raise ValueError("receivable_invoice_ids must all be output invoices.")
        if any(invoice.invoice_type != InvoiceType.INPUT for invoice in payable_invoices):
            raise ValueError("payable_invoice_ids must all be input invoices.")

        counterparty_id = receivable_invoices[0].counterparty.id
        if any(invoice.counterparty.id != counterparty_id for invoice in [*receivable_invoices, *payable_invoices]):
            raise ValueError("offset reconciliation requires the same counterparty on both sides.")

        receivable_total = sum((abs(invoice.outstanding_amount) for invoice in receivable_invoices), start=ZERO)
        payable_total = sum((abs(invoice.outstanding_amount) for invoice in payable_invoices), start=ZERO)
        offset_amount = self._coerce_decimal(amount) if amount is not None else min(receivable_total, payable_total)
        if offset_amount <= ZERO:
            raise ValueError("offset amount must be positive.")

        receivable_allocations = self._allocate_invoice_amounts(receivable_invoices, offset_amount)
        payable_allocations = self._allocate_invoice_amounts(payable_invoices, offset_amount)
        offset_note = OffsetNote(
            id=f"offset_{next(self._offset_sequence):04d}",
            counterparty_id=counterparty_id,
            receivable_amount=receivable_total,
            payable_amount=payable_total,
            offset_amount=offset_amount,
            reason=reason,
            note=note,
            created_by=actor_id,
        )
        case = ReconciliationCase(
            id=self._next_case_id(),
            case_type=ReconciliationCaseType.OFFSET,
            biz_side="cross_offset",
            counterparty_id=counterparty_id,
            total_amount=offset_amount,
            created_by=actor_id,
            remark=note,
            resolution_type=reason,
            related_oa_ids=list(oa_ids or []),
            status=ReconciliationCaseStatus.CONFIRMED,
            lines=[
                *self._make_lines(case_id=None, object_type="invoice", allocations=receivable_allocations, side_role="credit"),
                *self._make_lines(case_id=None, object_type="invoice", allocations=payable_allocations, side_role="debit"),
                ReconciliationLine(
                    id=self._next_line_id(),
                    reconciliation_case_id="pending",
                    object_type="offset_note",
                    object_id=offset_note.id,
                    applied_amount=offset_amount,
                    side_role="note",
                ),
            ],
        )
        self._bind_case_lines(case)
        self._apply_invoice_allocations(receivable_allocations)
        self._apply_invoice_allocations(payable_allocations)
        self._cases[case.id] = case
        self._offset_notes[offset_note.id] = offset_note
        self._audit_service.record_action(
            actor_id=actor_id,
            action="offset_reconciliation_recorded",
            entity_type="reconciliation_case",
            entity_id=case.id,
            before_amount=ZERO,
            after_amount=offset_amount,
            metadata={
                "receivable_invoice_ids": receivable_invoice_ids,
                "payable_invoice_ids": payable_invoice_ids,
                "offset_note_id": offset_note.id,
                "reason": reason,
                "note": note,
                "oa_ids": list(oa_ids or []),
            },
        )
        return case, offset_note

    def build_workbench(self, *, month: str) -> dict[str, Any]:
        latest_run = self._matching_service.list_runs()[-1] if self._matching_service.list_runs() else None
        result_by_object_id = self._index_results(latest_run.results if latest_run else [])
        exception_case_by_object_id = self._index_follow_up_cases()
        paired_object_ids = self._paired_object_ids()

        all_invoices = [
            invoice for invoice in self._import_service.list_invoices() if self._match_month(invoice.invoice_date, month)
        ]
        all_transactions = [
            transaction
            for transaction in self._import_service.list_transactions()
            if self._match_month(transaction.txn_date, month)
        ]
        paired_invoice_rows = [
            self._build_invoice_row(invoice, case_id=self._paired_case_id_for_object(invoice.id), section="paired")
            for invoice in all_invoices
            if invoice.id in paired_object_ids
        ]
        paired_bank_rows = [
            self._build_bank_row(transaction, case_id=self._paired_case_id_for_object(transaction.id), section="paired")
            for transaction in all_transactions
            if transaction.id in paired_object_ids
        ]
        open_invoice_rows = [
            self._build_invoice_row(
                invoice,
                case_id=self._open_link_id(invoice.id, result_by_object_id),
                section="open",
                result=result_by_object_id.get(invoice.id),
                exception_case=exception_case_by_object_id.get(invoice.id),
            )
            for invoice in all_invoices
            if invoice.outstanding_amount != ZERO
        ]
        open_bank_rows = [
            self._build_bank_row(
                transaction,
                case_id=self._open_link_id(transaction.id, result_by_object_id),
                section="open",
                result=result_by_object_id.get(transaction.id),
                exception_case=exception_case_by_object_id.get(transaction.id),
            )
            for transaction in all_transactions
            if transaction.outstanding_amount > ZERO
        ]

        return {
            "month": month,
            "summary": {
                "bank": len(all_transactions),
                "invoice": len(all_invoices),
                "paired": len(paired_invoice_rows) + len(paired_bank_rows),
                "open": len(open_invoice_rows) + len(open_bank_rows),
                "exceptions": len(self._exception_records),
                "case_count": len(self._cases),
            },
            "paired": {
                "bank": paired_bank_rows,
                "invoice": paired_invoice_rows,
            },
            "open": {
                "bank": open_bank_rows,
                "invoice": open_invoice_rows,
            },
            "context_options": {
                "receivable_exceptions": RECEIVABLE_EXCEPTION_OPTIONS,
                "payable_exceptions": PAYABLE_EXCEPTION_OPTIONS,
            },
            "history": {
                "cases": [asdict(case) for case in self.list_cases()],
                "audit_logs": [asdict(entry) for entry in self._audit_service.list_entries()],
            },
        }

    def list_cases(self) -> list[ReconciliationCase]:
        return list(self._cases.values())

    def get_case(self, case_id: str) -> ReconciliationCase:
        return self._cases[case_id]

    def _build_invoice_row(
        self,
        invoice: Invoice,
        *,
        case_id: str | None,
        section: str,
        result: MatchingResult | None = None,
        exception_case: ReconciliationCase | None = None,
    ) -> dict[str, Any]:
        seller_name, buyer_name = self._resolve_invoice_parties(invoice)
        seller_tax_no, buyer_tax_no = self._resolve_invoice_tax_nos(invoice)
        relation = self._relation_for_object(invoice.id, section=section, result=result, exception_case=exception_case)
        return {
            "id": invoice.id,
            "type": "invoice",
            "caseId": case_id,
            "bizSide": self._resolve_biz_side([invoice]),
            "sellerTaxNo": seller_tax_no,
            "sellerName": seller_name,
            "buyerTaxNo": buyer_tax_no,
            "buyerName": buyer_name,
            "issueDate": invoice.invoice_date,
            "amount": invoice.amount,
            "taxRate": invoice.tax_rate or "—",
            "taxAmount": invoice.tax_amount,
            "totalWithTax": invoice.total_with_tax or invoice.amount,
            "invoiceType": "销项发票" if invoice.invoice_type == InvoiceType.OUTPUT else "进项发票",
            "relation": relation,
            "candidateInvoiceIds": result.invoice_ids if result else [],
            "candidateTransactionIds": result.transaction_ids if result else [],
            "candidateResultId": result.id if result else None,
            "status": invoice.status.value,
            "details": {
                "序号": invoice.id,
                "发票代码": invoice.invoice_code,
                "发票号码": invoice.invoice_no,
                "数电发票号码": invoice.digital_invoice_no,
                "税收分类编码": invoice.tax_classification_code,
                "特定业务类型": invoice.specific_business_type,
                "货物或应税劳务名称": invoice.taxable_item_name,
                "规格型号": invoice.specification_model,
                "单位": invoice.unit,
                "数量": self._format_decimal(invoice.quantity),
                "单价": self._format_decimal(invoice.unit_price),
                "发票来源": invoice.invoice_source,
                "发票票种": invoice.invoice_kind,
                "发票状态": invoice.invoice_status_from_source,
                "是否正数发票": invoice.is_positive_invoice,
                "发票风险等级": invoice.risk_level,
                "开票人": invoice.issuer,
                "备注": invoice.remark,
            },
        }

    def _build_bank_row(
        self,
        transaction: BankTransaction,
        *,
        case_id: str | None,
        section: str,
        result: MatchingResult | None = None,
        exception_case: ReconciliationCase | None = None,
    ) -> dict[str, Any]:
        relation = self._relation_for_object(transaction.id, section=section, result=result, exception_case=exception_case)
        return {
            "id": transaction.id,
            "type": "bank",
            "caseId": case_id,
            "bizSide": "receivable" if transaction.txn_direction == TransactionDirection.INFLOW else "payable",
            "tradeTime": transaction.trade_time or transaction.txn_date,
            "debit": transaction.amount if transaction.txn_direction == TransactionDirection.OUTFLOW else "",
            "credit": transaction.amount if transaction.txn_direction == TransactionDirection.INFLOW else "",
            "counterparty": transaction.counterparty_name_raw,
            "payAccount": self._recognize_bank_account(transaction.account_no),
            "invoiceRelation": relation,
            "payReceiveTime": transaction.pay_receive_time or transaction.trade_time or transaction.txn_date,
            "remark": transaction.remark or transaction.summary or "—",
            "repayDate": "—",
            "candidateInvoiceIds": result.invoice_ids if result else [],
            "candidateTransactionIds": result.transaction_ids if result else [],
            "candidateResultId": result.id if result else None,
            "status": transaction.status.value,
            "details": {
                "账号": transaction.account_no,
                "账户名称": transaction.account_name,
                "余额": self._format_decimal(transaction.balance),
                "币种": transaction.currency,
                "对方账号": transaction.counterparty_account_no,
                "对方开户机构": transaction.counterparty_bank_name,
                "记账日期": transaction.booked_date or transaction.txn_date,
                "摘要": transaction.summary,
                "备注": transaction.remark,
                "账户明细编号-交易流水号": transaction.account_detail_no or transaction.bank_serial_no,
                "企业流水号": transaction.enterprise_serial_no,
                "凭证种类": transaction.voucher_kind,
                "凭证号": transaction.voucher_no,
            },
        }

    def _paired_object_ids(self) -> set[str]:
        object_ids: set[str] = set()
        for case in self._cases.values():
            if case.status != ReconciliationCaseStatus.CONFIRMED:
                continue
            for line in case.lines:
                if line.object_type in {"invoice", "bank_txn", "offset_note"} and line.applied_amount != ZERO:
                    object_ids.add(line.object_id)
        return object_ids

    def _paired_case_id_for_object(self, object_id: str) -> str | None:
        for case in reversed(self.list_cases()):
            for line in case.lines:
                if line.object_id == object_id and line.applied_amount != ZERO:
                    return case.id
        return None

    def _index_follow_up_cases(self) -> dict[str, ReconciliationCase]:
        result: dict[str, ReconciliationCase] = {}
        for case in self._cases.values():
            if case.status != ReconciliationCaseStatus.FOLLOW_UP_REQUIRED:
                continue
            for line in case.lines:
                if line.object_type in {"invoice", "bank_txn"}:
                    result[line.object_id] = case
        return result

    @staticmethod
    def _index_results(results: list[MatchingResult]) -> dict[str, MatchingResult]:
        index: dict[str, MatchingResult] = {}
        for result in results:
            for invoice_id in result.invoice_ids:
                index[invoice_id] = result
            for transaction_id in result.transaction_ids:
                index[transaction_id] = result
        return index

    @staticmethod
    def _match_month(value: str | None, month: str) -> bool:
        return bool(value and value.startswith(month))

    @staticmethod
    def _coerce_decimal(value: str | Decimal) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(CENT)
        return Decimal(str(value)).quantize(CENT)

    def _allocate_invoice_amounts(self, items: list[Invoice], target_amount: Decimal) -> list[tuple[str, Decimal]]:
        remaining = target_amount
        allocations: list[tuple[str, Decimal]] = []
        for item in items:
            if remaining <= ZERO:
                break
            outstanding = item.outstanding_amount
            available = abs(outstanding)
            if available <= ZERO:
                continue
            applied = min(available, remaining)
            signed_applied = applied if outstanding >= ZERO else -applied
            allocations.append((item.id, signed_applied))
            remaining -= applied
        if remaining > ZERO:
            raise ValueError("selected objects do not have enough outstanding amount for the requested reconciliation.")
        return allocations

    def _allocate_transaction_amounts(self, items: list[BankTransaction], target_amount: Decimal) -> list[tuple[str, Decimal]]:
        remaining = target_amount
        allocations: list[tuple[str, Decimal]] = []
        for item in items:
            if remaining <= ZERO:
                break
            applied = min(item.outstanding_amount, remaining)
            if applied <= ZERO:
                continue
            allocations.append((item.id, applied))
            remaining -= applied
        if remaining > ZERO:
            raise ValueError("selected objects do not have enough outstanding amount for the requested reconciliation.")
        return allocations

    def _apply_invoice_allocations(self, allocations: list[tuple[str, Decimal]]) -> None:
        for invoice_id, applied in allocations:
            invoice = self._import_service.get_invoice(invoice_id)
            invoice.written_off_amount += applied
            invoice.status = (
                InvoiceStatus.RECONCILED if invoice.outstanding_amount == ZERO else InvoiceStatus.PARTIALLY_RECONCILED
            )

    def _apply_transaction_allocations(self, allocations: list[tuple[str, Decimal]]) -> None:
        for transaction_id, applied in allocations:
            transaction = self._import_service.get_transaction(transaction_id)
            transaction.written_off_amount += applied
            transaction.status = (
                TransactionStatus.RECONCILED
                if transaction.outstanding_amount == ZERO
                else TransactionStatus.PARTIALLY_RECONCILED
            )

    def _make_lines(
        self,
        *,
        case_id: str | None,
        object_type: str,
        allocations: list[tuple[str, Decimal]],
        side_role: str,
    ) -> list[ReconciliationLine]:
        return [
            ReconciliationLine(
                id=self._next_line_id(),
                reconciliation_case_id=case_id or "pending",
                object_type=object_type,
                object_id=object_id,
                applied_amount=applied_amount,
                side_role=side_role,
            )
            for object_id, applied_amount in allocations
        ]

    def _make_zero_lines(self, *, case_id: str | None, object_type: str, object_ids: list[str]) -> list[ReconciliationLine]:
        return [
            ReconciliationLine(
                id=self._next_line_id(),
                reconciliation_case_id=case_id or "pending",
                object_type=object_type,
                object_id=object_id,
                applied_amount=ZERO,
                side_role="note",
            )
            for object_id in object_ids
        ]

    @staticmethod
    def _bind_case_lines(case: ReconciliationCase) -> None:
        for line in case.lines:
            line.reconciliation_case_id = case.id

    @staticmethod
    def _resolve_biz_side(invoices: list[Invoice]) -> str:
        if invoices and invoices[0].invoice_type == InvoiceType.OUTPUT:
            return "receivable"
        return "payable"

    @staticmethod
    def _resolve_invoice_sign(invoices: list[Invoice]) -> int:
        signs = {1 if invoice.outstanding_amount >= ZERO else -1 for invoice in invoices if invoice.outstanding_amount != ZERO}
        if not signs:
            raise ValueError("selected invoices must have outstanding amount.")
        if len(signs) != 1:
            raise ValueError("selected invoices must have the same sign for reconciliation.")
        return signs.pop()

    @staticmethod
    def _validate_transaction_direction(
        transactions: list[BankTransaction],
        *,
        biz_side: str,
        invoice_sign: int,
    ) -> None:
        expected_sign = invoice_sign if biz_side == "receivable" else -invoice_sign
        actual_signs = {1 if transaction.txn_direction == TransactionDirection.INFLOW else -1 for transaction in transactions}
        if len(actual_signs) != 1 or actual_signs.pop() != expected_sign:
            raise ValueError("selected bank transactions do not match the invoice direction for this reconciliation.")

    @staticmethod
    def _resolve_counterparty_id(invoices: list[Invoice], transactions: list[BankTransaction]) -> str:
        if invoices:
            return invoices[0].counterparty.id
        if transactions and transactions[0].counterparty_id:
            return transactions[0].counterparty_id
        return "counterparty_unknown"

    @staticmethod
    def _resolve_invoice_parties(invoice: Invoice) -> tuple[str, str]:
        if invoice.invoice_type == InvoiceType.OUTPUT:
            return invoice.seller_name or COMPANY_NAME, invoice.buyer_name or invoice.counterparty.name
        return invoice.seller_name or invoice.counterparty.name, invoice.buyer_name or COMPANY_NAME

    @staticmethod
    def _resolve_invoice_tax_nos(invoice: Invoice) -> tuple[str | None, str | None]:
        if invoice.invoice_type == InvoiceType.OUTPUT:
            return invoice.seller_tax_no or COMPANY_TAX_NO, invoice.buyer_tax_no or invoice.counterparty.tax_no
        return invoice.seller_tax_no or invoice.counterparty.tax_no, invoice.buyer_tax_no or COMPANY_TAX_NO

    def _relation_for_object(
        self,
        object_id: str,
        *,
        section: str,
        result: MatchingResult | None,
        exception_case: ReconciliationCase | None,
    ) -> dict[str, str]:
        if section == "paired":
            case_id = self._paired_case_id_for_object(object_id)
            case = self._cases.get(case_id or "")
            if case and case.case_type == ReconciliationCaseType.OFFLINE:
                return {"text": "线下核销", "tone": "good"}
            return {"text": "已核销", "tone": "good"}
        if self._paired_case_id_for_object(object_id) is not None:
            return {"text": "部分核销待继续", "tone": "warn"}
        if exception_case is not None:
            return {"text": f"异常处理中（{exception_case.exception_code}）", "tone": "risk"}
        if result is None:
            return {"text": "待人工处理", "tone": "warn"}
        if result.result_type.value == "automatic_match":
            return {"text": "自动匹配候选", "tone": "good"}
        if result.result_type.value == "suggested_match":
            return {"text": "建议关联", "tone": "warn"}
        return {"text": "待人工处理", "tone": "warn"}

    @staticmethod
    def _open_link_id(object_id: str, result_by_object_id: dict[str, MatchingResult]) -> str | None:
        result = result_by_object_id.get(object_id)
        return result.id if result is not None else None

    @staticmethod
    def _resolve_exception_title(biz_side: str, exception_code: str) -> str:
        options = RECEIVABLE_EXCEPTION_OPTIONS if biz_side == "receivable" else PAYABLE_EXCEPTION_OPTIONS
        for item in options:
            if item["code"] == exception_code:
                return item["title"]
        return "待人工核查"

    @staticmethod
    def _resolve_follow_up_ledger_type(resolution_action: str | None) -> str | None:
        if resolution_action is None:
            return None
        if "invoice" in resolution_action:
            return "invoice_collection"
        if "payment" in resolution_action:
            return "payment_collection"
        if "refund" in resolution_action:
            return "refund"
        return None

    @staticmethod
    def _format_decimal(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value.quantize(CENT)}"

    def _recognize_bank_account(self, account_no: str) -> str:
        suffix = account_no[-4:] if len(account_no) >= 4 else account_no
        if account_no.startswith("6214"):
            return f"招行基本户 {suffix}"
        if account_no.startswith("6222"):
            return f"工行账户 {suffix}"
        if account_no.startswith("6228"):
            return f"中行账户 {suffix}"
        return f"银行账户 {suffix}"

    def _next_case_id(self) -> str:
        return f"rc_{next(self._case_sequence):04d}"

    def _next_line_id(self) -> str:
        return f"rc_line_{next(self._line_sequence):05d}"
