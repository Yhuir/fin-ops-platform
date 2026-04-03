from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import BatchType, ImportDecision, InvoiceStatus, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService


class ImportNormalizationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counterparty = Counterparty(
            id="cp_001",
            name="Acme Supplies",
            normalized_name="acme supplies",
            counterparty_type="vendor",
        )
        self.existing_invoice = Invoice(
            id="inv_existing_001",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="9001",
            counterparty=self.counterparty,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-03-21",
            status=InvoiceStatus.PENDING,
            source_unique_key="033001:9001",
            data_fingerprint="invoice-fp-existing",
            invoice_status_from_source="valid",
        )
        self.existing_invoice_without_unique = Invoice(
            id="inv_existing_002",
            invoice_type=InvoiceType.INPUT,
            invoice_no="N/A",
            counterparty=self.counterparty,
            amount=Decimal("66.00"),
            signed_amount=Decimal("66.00"),
            invoice_date="2026-03-22",
            source_unique_key=None,
            data_fingerprint="invoice:acme supplies:2026-03-22:66.00",
        )
        self.existing_transaction = BankTransaction(
            id="txn_existing_001",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme Supplies Ltd.",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            txn_date="2026-03-23",
            source_unique_key="SERIAL-001",
            data_fingerprint="bank:62220001:acme supplies ltd.:2026-03-23:outflow:88.00",
            bank_serial_no="SERIAL-001",
        )
        self.service = ImportNormalizationService(
            existing_invoices=[self.existing_invoice, self.existing_invoice_without_unique],
            existing_transactions=[self.existing_transaction],
        )

    def test_preview_output_invoice_classifies_rows_across_all_decision_types(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="output-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9002",
                    "counterparty_name": "  New Corp Ltd. ",
                    "amount": "120.00",
                    "invoice_date": "2026/03/24",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "cancelled",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "counterparty_name": "Acme Supplies",
                    "amount": "66.00",
                    "invoice_date": "2026-03-22",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9003",
                    "counterparty_name": "Bad Amount Inc",
                    "amount": "abc",
                    "invoice_date": "2026-03-25",
                },
            ],
        )

        decisions = [row.decision for row in preview.row_results]
        self.assertEqual(
            decisions,
            [
                ImportDecision.CREATED,
                ImportDecision.STATUS_UPDATED,
                ImportDecision.DUPLICATE_SKIPPED,
                ImportDecision.SUSPECTED_DUPLICATE,
                ImportDecision.ERROR,
            ],
        )
        self.assertEqual(preview.success_count, 2)
        self.assertEqual(preview.updated_count, 1)
        self.assertEqual(preview.duplicate_count, 1)
        self.assertEqual(preview.suspected_duplicate_count, 1)
        self.assertEqual(preview.error_count, 1)

    def test_preview_bank_transaction_normalizes_direction_and_marks_suspected_duplicates(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62229999",
                    "txn_date": "2026-03-24",
                    "counterparty_name": "Vendor A",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-NEW-001",
                    "summary": "purchase",
                },
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "",
                    "voucher_no": "",
                    "enterprise_serial_no": "",
                    "summary": "same as old but no official id",
                },
                {
                    "account_no": "62220001",
                    "txn_date": "bad-date",
                    "counterparty_name": "",
                    "debit_amount": "",
                    "credit_amount": "not-number",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)
        self.assertEqual(preview.normalized_rows[0]["txn_direction"], TransactionDirection.OUTFLOW.value)
        self.assertEqual(preview.normalized_rows[0]["signed_amount"], "-50.00")
        self.assertEqual(preview.row_results[1].decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(preview.row_results[2].decision, ImportDecision.ERROR)

    def test_confirm_import_persists_created_rows_and_updates_source_status(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="confirm-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9010",
                    "counterparty_name": "Created Corp",
                    "amount": "200.00",
                    "invoice_date": "2026-03-25",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "cancelled",
                },
            ],
        )

        confirmed = self.service.confirm_import(preview.id)

        self.assertEqual(confirmed.status.value, "completed")
        self.assertEqual(len(self.service.list_invoices()), 3)
        updated = self.service.get_invoice("inv_existing_001")
        self.assertEqual(updated.invoice_status_from_source, "cancelled")
        created = next(invoice for invoice in self.service.list_invoices() if invoice.invoice_no == "9010")
        self.assertEqual(created.counterparty.normalized_name, "created corp")


if __name__ == "__main__":
    unittest.main()
