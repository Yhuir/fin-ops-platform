from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import BatchType, InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService


class LiveWorkbenchServiceTests(unittest.TestCase):
    def test_workbench_hides_legacy_demo_bank_transactions(self) -> None:
        import_service = ImportNormalizationService()

        demo_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank_transaction.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Workbench API Client",
                    "credit_amount": "150.00",
                    "debit_amount": "",
                    "summary": "api receipt",
                }
            ],
        )
        import_service.confirm_import(demo_preview.id)

        real_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="historydetail14080.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220002",
                    "txn_date": "2026-03-28",
                    "trade_time": "2026-03-28 09:15",
                    "pay_receive_time": "2026-03-28 09:15",
                    "counterparty_name": "真实供应商",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-REAL-001",
                    "summary": "real payment",
                }
            ],
        )
        import_service.confirm_import(real_preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("2026-03")
        bank_rows = payload["open"]["bank"]

        self.assertEqual(len(bank_rows), 1)
        self.assertEqual(bank_rows[0]["counterparty_name"], "真实供应商")
        self.assertEqual(bank_rows[0]["trade_time"], "2026-03-28 09:15")

    def test_invoice_rows_fill_missing_party_fields_from_company_identity_and_counterparty(self) -> None:
        known_company_invoice = Invoice(
            id="inv_known_company",
            invoice_type=InvoiceType.INPUT,
            invoice_no="KNOWN-001",
            counterparty=Counterparty(
                id="cp_vendor",
                name="云南供应商有限公司",
                normalized_name="云南供应商有限公司",
                counterparty_type="vendor",
                tax_no="91530100VENDOR0001",
            ),
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-03-01",
            seller_tax_no="91530100VENDOR0001",
            seller_name="云南供应商有限公司",
            buyer_tax_no="915300007194052520",
            buyer_name="云南溯源科技有限公司",
        )
        sparse_output_invoice = Invoice(
            id="inv_sparse_output",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="OUT-001",
            counterparty=Counterparty(
                id="cp_client",
                name="云南客户有限公司",
                normalized_name="云南客户有限公司",
                counterparty_type="customer",
                tax_no="91530100CLIENT0001",
            ),
            amount=Decimal("150.00"),
            signed_amount=Decimal("150.00"),
            invoice_date="2026-03-26",
        )
        sparse_input_invoice = Invoice(
            id="inv_sparse_input",
            invoice_type=InvoiceType.INPUT,
            invoice_no="IN-001",
            counterparty=Counterparty(
                id="cp_service_vendor",
                name="云南服务商有限公司",
                normalized_name="云南服务商有限公司",
                counterparty_type="vendor",
                tax_no="91530100VENDOR0002",
            ),
            amount=Decimal("80.00"),
            signed_amount=Decimal("80.00"),
            invoice_date="2026-03-27",
        )

        import_service = ImportNormalizationService(
            existing_invoices=[known_company_invoice, sparse_output_invoice, sparse_input_invoice],
        )
        matching_service = MatchingEngineService(import_service)
        service = LiveWorkbenchService(import_service, matching_service)

        payload = service.get_workbench("2026-03")
        invoice_rows = {row["id"]: row for row in payload["open"]["invoice"]}

        output_row = invoice_rows["inv_sparse_output"]
        self.assertEqual(output_row["seller_tax_no"], "915300007194052520")
        self.assertEqual(output_row["seller_name"], "云南溯源科技有限公司")
        self.assertEqual(output_row["buyer_tax_no"], "91530100CLIENT0001")
        self.assertEqual(output_row["buyer_name"], "云南客户有限公司")

        input_row = invoice_rows["inv_sparse_input"]
        self.assertEqual(input_row["seller_tax_no"], "91530100VENDOR0002")
        self.assertEqual(input_row["seller_name"], "云南服务商有限公司")
        self.assertEqual(input_row["buyer_tax_no"], "915300007194052520")
        self.assertEqual(input_row["buyer_name"], "云南溯源科技有限公司")

        output_detail = service.get_row_detail("inv_sparse_output")
        self.assertEqual(output_detail["summary_fields"]["销方识别号"], "915300007194052520")
        self.assertEqual(output_detail["summary_fields"]["购方识别号"], "91530100CLIENT0001")
        self.assertEqual(output_detail["summary_fields"]["购买方名称"], "云南客户有限公司")
        self.assertEqual(output_detail["detail_fields"]["发票号码"], "OUT-001")
        self.assertIn("ignore", output_row["available_actions"])


if __name__ == "__main__":
    unittest.main()
