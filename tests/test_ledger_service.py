from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import (
    BatchType,
    LedgerStatus,
    LedgerType,
    ReminderStatus,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


class LedgerReminderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.matching_service = MatchingEngineService(self.import_service)
        self.audit_service = AuditTrailService()
        self.reconciliation_service = ManualReconciliationService(
            self.import_service,
            self.matching_service,
            self.audit_service,
        )
        self.ledger_service = LedgerReminderService(
            self.import_service,
            self.audit_service,
        )

    def test_partial_receivable_case_generates_payment_collection_ledger(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033101",
                    "invoice_no": "LEDGER-OUT-001",
                    "counterparty_name": "Ledger Client",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62140001",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Ledger Client",
                    "debit_amount": "",
                    "credit_amount": "60.00",
                    "bank_serial_no": "LEDGER-BANK-001",
                    "summary": "partial receipt",
                }
            ],
        )
        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            remark="partial receivable settlement",
        )

        ledgers = self.ledger_service.sync_from_case(case)

        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].ledger_type, LedgerType.PAYMENT_COLLECTION)
        self.assertEqual(ledgers[0].open_amount, Decimal("40.00"))
        self.assertEqual(ledgers[0].status, LedgerStatus.OPEN)

    def test_payable_overpayment_generates_invoice_collection_ledger(self) -> None:
        invoice_ids = self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "044101",
                    "invoice_no": "LEDGER-IN-001",
                    "counterparty_name": "Ledger Vendor",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Ledger Vendor",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "bank_serial_no": "LEDGER-BANK-002",
                    "summary": "supplier payment",
                }
            ],
        )
        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            remark="paid more than current invoice amount",
        )

        ledgers = self.ledger_service.sync_from_case(case)

        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].ledger_type, LedgerType.INVOICE_COLLECTION)
        self.assertEqual(ledgers[0].open_amount, Decimal("20.00"))

    def test_exception_codes_generate_expected_follow_up_ledger_types(self) -> None:
        receipt_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62140002",
                    "txn_date": "2026-03-28",
                    "counterparty_name": "Receipt Without Invoice",
                    "debit_amount": "",
                    "credit_amount": "88.00",
                    "bank_serial_no": "LEDGER-BANK-003",
                    "summary": "receipt pending invoice",
                }
            ],
        )
        refund_txn_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62220002",
                    "txn_date": "2026-03-28",
                    "counterparty_name": "Refund Vendor",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "LEDGER-BANK-004",
                    "summary": "wrong payment",
                }
            ],
        )

        receivable_case, receivable_exception = self.reconciliation_service.record_exception(
            actor_id="user_finance_01",
            biz_side="receivable",
            exception_code="SO-B",
            invoice_ids=[],
            transaction_ids=receipt_ids,
            resolution_action="create_follow_up_ledger",
            note="received money before issuing invoice",
        )
        payable_case, payable_exception = self.reconciliation_service.record_exception(
            actor_id="user_finance_01",
            biz_side="payable",
            exception_code="PI-C",
            invoice_ids=[],
            transaction_ids=refund_txn_ids,
            resolution_action="create_follow_up_ledger",
            note="payment needs refund",
        )

        receivable_ledgers = self.ledger_service.sync_from_case(receivable_case, exception_record=receivable_exception)
        payable_ledgers = self.ledger_service.sync_from_case(payable_case, exception_record=payable_exception)

        self.assertEqual(receivable_ledgers[0].ledger_type, LedgerType.OUTPUT_INVOICE_ISSUE)
        self.assertEqual(payable_ledgers[0].ledger_type, LedgerType.REFUND)

    def test_schedule_and_run_reminders_are_repeatable_without_duplicates(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033102",
                    "invoice_no": "LEDGER-OUT-002",
                    "counterparty_name": "Reminder Client",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62140003",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Reminder Client",
                    "debit_amount": "",
                    "credit_amount": "60.00",
                    "bank_serial_no": "LEDGER-BANK-005",
                    "summary": "partial receipt",
                }
            ],
        )
        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
        )
        self.ledger_service.sync_from_case(case)

        created_once = self.ledger_service.schedule_reminders(as_of="2026-03-26", days_ahead=7)
        created_twice = self.ledger_service.schedule_reminders(as_of="2026-03-26", days_ahead=7)
        due_before_run = self.ledger_service.list_reminders(as_of="2026-04-10", status=ReminderStatus.PENDING)
        sent = self.ledger_service.run_reminders(as_of="2026-04-10")

        self.assertEqual(len(created_once), 1)
        self.assertEqual(len(created_twice), 0)
        self.assertEqual(len(due_before_run), 1)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].status, ReminderStatus.SENT)

    def _confirm(self, batch_type: BatchType, rows: list[dict[str, str]]) -> list[str]:
        preview = self.import_service.preview_import(
            batch_type=batch_type,
            source_name=f"{batch_type.value}.json",
            imported_by="user_finance_01",
            rows=rows,
        )
        self.import_service.confirm_import(preview.id)
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            return [self.import_service.list_invoices()[-1].id]
        return [self.import_service.list_transactions()[-1].id]


if __name__ == "__main__":
    unittest.main()
