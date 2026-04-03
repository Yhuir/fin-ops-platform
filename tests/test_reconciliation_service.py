from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import (
    BatchType,
    DifferenceReason,
    InvoiceStatus,
    ReconciliationCaseStatus,
    ReconciliationCaseType,
    TransactionStatus,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


class ManualReconciliationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.matching_service = MatchingEngineService(self.import_service)
        self.audit_service = AuditTrailService()
        self.reconciliation_service = ManualReconciliationService(
            self.import_service,
            self.matching_service,
            self.audit_service,
        )

    def test_confirm_manual_reconciliation_creates_case_updates_objects_and_records_audit(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033001",
                    "invoice_no": "MANUAL-001",
                    "counterparty_name": "Manual Client",
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
                    "account_no": "62221111",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Manual Client",
                    "debit_amount": "",
                    "credit_amount": "100.00",
                    "bank_serial_no": "RC-001",
                    "summary": "manual receipt",
                }
            ],
        )
        run = self.matching_service.run(triggered_by="user_finance_01")

        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            oa_ids=["OA-202603-100"],
            source_result_id=run.results[0].id,
            remark="manual confirmation",
        )

        invoice = self.import_service.get_invoice(invoice_ids[0])
        transaction = self.import_service.get_transaction(transaction_ids[0])

        self.assertEqual(case.case_type, ReconciliationCaseType.MANUAL)
        self.assertEqual(case.status, ReconciliationCaseStatus.CONFIRMED)
        self.assertEqual(case.source_result_id, run.results[0].id)
        self.assertEqual(len(case.lines), 2)
        self.assertEqual(invoice.written_off_amount, Decimal("100.00"))
        self.assertEqual(transaction.written_off_amount, Decimal("100.00"))
        self.assertEqual(invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual(transaction.status, TransactionStatus.RECONCILED)
        self.assertEqual(self.audit_service.list_entries()[-1].action, "manual_reconciliation_confirmed")

    def test_record_exception_creates_follow_up_case_and_structured_exception_record(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033002",
                    "invoice_no": "EXC-001",
                    "counterparty_name": "Exception Client",
                    "amount": "88.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        case, exception_record = self.reconciliation_service.record_exception(
            actor_id="user_finance_01",
            biz_side="receivable",
            exception_code="SO-B",
            invoice_ids=invoice_ids,
            transaction_ids=[],
            oa_ids=["OA-202603-101"],
            resolution_action="create_follow_up_ledger",
            note="customer has not paid yet",
        )

        self.assertEqual(case.case_type, ReconciliationCaseType.DIFFERENCE)
        self.assertEqual(case.status, ReconciliationCaseStatus.FOLLOW_UP_REQUIRED)
        self.assertEqual(case.exception_code, "SO-B")
        self.assertEqual(case.related_oa_ids, ["OA-202603-101"])
        self.assertEqual(exception_record.exception_code, "SO-B")
        self.assertEqual(exception_record.source_invoice_ids, invoice_ids)
        self.assertEqual(self.audit_service.list_entries()[-1].action, "manual_exception_recorded")

    def test_record_offline_reconciliation_creates_case_and_offline_record(self) -> None:
        invoice_ids = self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "044001",
                    "invoice_no": "OFF-001",
                    "counterparty_name": "Offline Vendor",
                    "amount": "60.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        case, offline_record = self.reconciliation_service.record_offline_reconciliation(
            actor_id="user_finance_01",
            biz_side="payable",
            invoice_ids=invoice_ids,
            oa_ids=["OA-202603-102"],
            amount="60.00",
            payment_method="cash",
            occurred_on="2026-03-29",
            note="cash settlement",
        )

        invoice = self.import_service.get_invoice(invoice_ids[0])

        self.assertEqual(case.case_type, ReconciliationCaseType.OFFLINE)
        self.assertEqual(case.status, ReconciliationCaseStatus.CONFIRMED)
        self.assertEqual(invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual(invoice.written_off_amount, Decimal("60.00"))
        self.assertEqual(offline_record.payment_method, "cash")
        self.assertEqual(len(case.lines), 2)
        self.assertEqual(self.audit_service.list_entries()[-1].action, "offline_reconciliation_recorded")

    def test_confirm_difference_reconciliation_records_structured_difference_reason(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "077001",
                    "invoice_no": "DIFF-001",
                    "counterparty_name": "Difference Client",
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
                    "account_no": "62225555",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Difference Client",
                    "debit_amount": "",
                    "credit_amount": "99.50",
                    "bank_serial_no": "DIFF-BANK-001",
                    "summary": "receipt after bank fee",
                }
            ],
        )

        case = self.reconciliation_service.confirm_difference_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            difference_reason=DifferenceReason.FEE,
            difference_note="bank retained 0.50 service fee",
        )

        invoice = self.import_service.get_invoice(invoice_ids[0])
        transaction = self.import_service.get_transaction(transaction_ids[0])

        self.assertEqual(case.case_type, ReconciliationCaseType.DIFFERENCE)
        self.assertEqual(case.status, ReconciliationCaseStatus.CONFIRMED)
        self.assertEqual(case.difference_amount, Decimal("0.50"))
        self.assertEqual(case.difference_reason, DifferenceReason.FEE)
        self.assertEqual(case.difference_note, "bank retained 0.50 service fee")
        self.assertEqual(invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual(invoice.written_off_amount, Decimal("100.00"))
        self.assertEqual(transaction.status, TransactionStatus.RECONCILED)
        self.assertEqual(transaction.written_off_amount, Decimal("99.50"))
        self.assertEqual(self.audit_service.list_entries()[-1].action, "difference_reconciliation_confirmed")

    def test_confirm_manual_reconciliation_supports_negative_output_invoice_with_refund_outflow(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "077002",
                    "invoice_no": "RED-001",
                    "counterparty_name": "Refund Client",
                    "amount": "-100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "red",
                    "is_positive_invoice": "否",
                }
            ],
        )
        transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62226666",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Refund Client",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "bank_serial_no": "RED-BANK-001",
                    "summary": "customer refund",
                }
            ],
        )

        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            remark="red invoice refund",
        )

        invoice = self.import_service.get_invoice(invoice_ids[0])
        transaction = self.import_service.get_transaction(transaction_ids[0])

        self.assertEqual(case.status, ReconciliationCaseStatus.CONFIRMED)
        self.assertEqual(invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual(invoice.written_off_amount, Decimal("-100.00"))
        self.assertEqual(transaction.status, TransactionStatus.RECONCILED)
        self.assertEqual(transaction.written_off_amount, Decimal("100.00"))

    def test_record_offset_reconciliation_creates_offset_note_and_closes_cross_side_invoices(self) -> None:
        receivable_invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "077003",
                    "invoice_no": "OFFSET-OUT-001",
                    "counterparty_name": "Dual Role Counterparty",
                    "amount": "120.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        payable_invoice_ids = self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "077004",
                    "invoice_no": "OFFSET-IN-001",
                    "counterparty_name": "Dual Role Counterparty",
                    "amount": "120.00",
                    "invoice_date": "2026-03-27",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        case, offset_note = self.reconciliation_service.record_offset_reconciliation(
            actor_id="user_finance_01",
            receivable_invoice_ids=receivable_invoice_ids,
            payable_invoice_ids=payable_invoice_ids,
            reason="same_counterparty_setoff",
            note="march mutual debt offset",
        )

        receivable_invoice = self.import_service.get_invoice(receivable_invoice_ids[0])
        payable_invoice = self.import_service.get_invoice(payable_invoice_ids[0])

        self.assertEqual(case.case_type, ReconciliationCaseType.OFFSET)
        self.assertEqual(case.status, ReconciliationCaseStatus.CONFIRMED)
        self.assertEqual(offset_note.offset_amount, Decimal("120.00"))
        self.assertEqual(offset_note.reason, "same_counterparty_setoff")
        self.assertEqual(receivable_invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual(payable_invoice.status, InvoiceStatus.RECONCILED)
        self.assertEqual({line.object_type for line in case.lines}, {"invoice", "offset_note"})
        self.assertEqual(self.audit_service.list_entries()[-1].action, "offset_reconciliation_recorded")

    def test_build_workbench_keeps_negative_invoices_visible_for_reverse_flow(self) -> None:
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "077005",
                    "invoice_no": "RED-OPEN-001",
                    "counterparty_name": "Visible Refund Client",
                    "amount": "-55.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "red",
                }
            ],
        )

        workbench = self.reconciliation_service.build_workbench(month="2026-03")

        self.assertIn(invoice_ids[0], [item["id"] for item in workbench["open"]["invoice"]])

    def test_build_workbench_groups_paired_and_open_rows_from_live_services(self) -> None:
        paired_invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "055001",
                    "invoice_no": "WB-PAIR-001",
                    "counterparty_name": "Workbench Client",
                    "amount": "120.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        paired_transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62223333",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Workbench Client",
                    "debit_amount": "",
                    "credit_amount": "120.00",
                    "bank_serial_no": "WB-PAIR-001",
                    "summary": "workbench receipt",
                }
            ],
        )
        open_invoice_ids = self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "066001",
                    "invoice_no": "WB-OPEN-001",
                    "counterparty_name": "Open Vendor",
                    "amount": "90.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        open_transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62224444",
                    "txn_date": "2026-03-28",
                    "counterparty_name": "Unmatched Bank Counterparty",
                    "debit_amount": "45.00",
                    "credit_amount": "",
                    "bank_serial_no": "WB-OPEN-002",
                    "summary": "unmatched payment",
                }
            ],
        )
        run = self.matching_service.run(triggered_by="user_finance_01")
        exact_result = next(result for result in run.results if result.invoice_ids == paired_invoice_ids)
        self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=paired_invoice_ids,
            transaction_ids=paired_transaction_ids,
            source_result_id=exact_result.id,
            remark="paired through workbench",
        )

        workbench = self.reconciliation_service.build_workbench(month="2026-03")

        self.assertEqual(workbench["month"], "2026-03")
        self.assertEqual(len(workbench["paired"]["invoice"]), 1)
        self.assertEqual(len(workbench["paired"]["bank"]), 1)
        self.assertEqual(len(workbench["open"]["invoice"]), 1)
        self.assertEqual(len(workbench["open"]["bank"]), 1)
        self.assertEqual(workbench["open"]["invoice"][0]["id"], open_invoice_ids[0])
        self.assertEqual(workbench["open"]["bank"][0]["id"], open_transaction_ids[0])
        self.assertIn("SO-A", [item["code"] for item in workbench["context_options"]["receivable_exceptions"]])

    def _confirm(self, batch_type: BatchType, rows: list[dict[str, str]]) -> list[str]:
        preview = self.import_service.preview_import(
            batch_type=batch_type,
            source_name=f"{batch_type.value}.json",
            imported_by="user_finance_01",
            rows=rows,
        )
        self.import_service.confirm_import(preview.id)
        created_ids = [
            row.linked_object_id
            for row in preview.row_results
            if row.linked_object_id is not None
        ]
        if created_ids:
            return created_ids
        if batch_type in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            return [self.import_service.list_invoices()[-1].id]
        return [self.import_service.list_transactions()[-1].id]


if __name__ == "__main__":
    unittest.main()
