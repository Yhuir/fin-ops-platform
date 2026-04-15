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

    def test_confirm_import_preserves_selected_bank_mapping_fields_on_created_transactions(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-25",
                    "trade_time": "2026-03-25 09:00:00",
                    "pay_receive_time": "2026-03-25 09:00:00",
                    "counterparty_name": "Vendor A",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-SELECTED-001",
                    "selected_bank_name": "建设银行",
                    "selected_bank_last4": "8826",
                }
            ],
        )

        self.service.confirm_import(preview.id)

        created = next(transaction for transaction in self.service.list_transactions() if transaction.bank_serial_no == "SERIAL-SELECTED-001")
        self.assertEqual(created.account_no, "62220001")
        self.assertEqual(created.imported_bank_name, "建设银行")
        self.assertEqual(created.imported_bank_last4, "8826")

    def test_confirm_import_skips_duplicate_invoice_rows_within_same_batch(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="duplicate-in-batch.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                },
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                },
            ],
        )

        confirmed = self.service.confirm_import(preview.id)

        matching = [invoice for invoice in self.service.list_invoices() if invoice.digital_invoice_no == "26537912210200143464"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(confirmed.duplicate_count, 1)
        self.assertEqual(confirmed.success_count, 1)
        self.assertEqual(preview.row_results[1].decision, ImportDecision.DUPLICATE_SKIPPED)

    def test_confirm_import_skips_duplicate_invoice_from_later_preview_batch(self) -> None:
        feb_preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="全量发票查询导出结果-2026年2月.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                }
            ],
        )
        mar_preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="全量发票查询导出结果-2026年3月.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                }
            ],
        )

        first_confirmed = self.service.confirm_import(feb_preview.id)
        second_confirmed = self.service.confirm_import(mar_preview.id)

        matching = [invoice for invoice in self.service.list_invoices() if invoice.digital_invoice_no == "26537912210200143464"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(first_confirmed.duplicate_count, 0)
        self.assertEqual(second_confirmed.duplicate_count, 1)
        self.assertEqual(second_confirmed.success_count, 0)
        self.assertEqual(mar_preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)


if __name__ == "__main__":
    unittest.main()
